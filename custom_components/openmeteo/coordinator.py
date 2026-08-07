"""Open-Meteo v2 data coordinator."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, State, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import OpenMeteoApiError, OpenMeteoClient
from .const import (
    CONF_AREA_NAME_OVERRIDE,
    CONF_ENTITY_ID,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_MIN_TRACK_INTERVAL,
    CONF_MODE,
    CONF_REVERSE_GEOCODE_COOLDOWN_MIN,
    CONF_TRACKED_ENTITY_ID,
    CONF_UPDATE_INTERVAL,
    CONF_UPDATE_INTERVAL_MIN,
    DEFAULT_MIN_TRACK_INTERVAL,
    DEFAULT_REVERSE_GEOCODE_COOLDOWN_MIN,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MODE_STATIC,
    MODE_TRACK,
)
from .location import async_reverse_geocode, coordinate_label, distance_km

_LOGGER = logging.getLogger(__name__)

# Ignore GPS jitter below this distance. Large jumps bypass the small-movement
# throttle so a motorway trip does not keep weather pinned to the previous city.
MIN_POSITION_CHANGE_KM = 0.05
IMMEDIATE_TRACK_DISTANCE_KM = 10.0


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return dt_util.parse_datetime(value)
    return None


class OpenMeteoDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinate location tracking, API updates and presentation state."""

    provider = "open_meteo"

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        store: Store[dict[str, Any]],
        restored: Mapping[str, Any] | None = None,
    ) -> None:
        self.entry = entry
        self._store = store
        self._client = OpenMeteoClient(hass)

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}-{entry.entry_id}",
            config_entry=entry,
            update_interval=self._weather_update_interval(),
        )

        restored = dict(restored or {})
        self._accepted_lat = self._safe_float(restored.get("latitude"))
        self._accepted_lon = self._safe_float(restored.get("longitude"))
        self._accepted_at = _parse_datetime(restored.get("accepted_at"))
        self.location_name = (
            str(restored["location_name"]) if restored.get("location_name") else None
        )
        self._last_geocode_at = _parse_datetime(restored.get("geocoded_at"))

        self._tracker_unsub: Callable[[], None] | None = None
        self._delayed_refresh_unsub: Callable[[], None] | None = None

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _merged_config(self) -> dict[str, Any]:
        return {**dict(self.entry.data or {}), **dict(self.entry.options or {})}

    @property
    def presentation_name(self) -> str:
        """Return the mutable UI name without changing source/location identity."""
        override = str(self._merged_config().get(CONF_AREA_NAME_OVERRIDE) or "").strip()
        return override or self.location_name or self.entry.title or "Open-Meteo"

    def _mode(self) -> str:
        merged = self._merged_config()
        mode = merged.get(CONF_MODE)
        if mode in (MODE_STATIC, MODE_TRACK):
            return mode
        return (
            MODE_TRACK
            if merged.get(CONF_ENTITY_ID) or merged.get(CONF_TRACKED_ENTITY_ID)
            else MODE_STATIC
        )

    def _tracker_entity_id(self) -> str | None:
        merged = self._merged_config()
        value = merged.get(CONF_ENTITY_ID) or merged.get(CONF_TRACKED_ENTITY_ID)
        return str(value) if value else None

    def _weather_update_interval(self) -> timedelta:
        merged = self._merged_config()
        raw_minutes = merged.get(CONF_UPDATE_INTERVAL_MIN)
        if raw_minutes is not None:
            try:
                return timedelta(minutes=max(1, int(raw_minutes)))
            except (TypeError, ValueError):
                pass
        try:
            seconds = max(
                60, int(merged.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
            )
        except (TypeError, ValueError):
            seconds = DEFAULT_UPDATE_INTERVAL
        return timedelta(seconds=seconds)

    def _tracking_interval(self) -> timedelta:
        merged = self._merged_config()
        try:
            minutes = max(
                1, int(merged.get(CONF_MIN_TRACK_INTERVAL, DEFAULT_MIN_TRACK_INTERVAL))
            )
        except (TypeError, ValueError):
            minutes = DEFAULT_MIN_TRACK_INTERVAL
        return timedelta(minutes=minutes)

    @staticmethod
    def _coordinates_from_state(state: State | None) -> tuple[float, float] | None:
        if state is None:
            return None
        try:
            latitude = float(state.attributes["latitude"])
            longitude = float(state.attributes["longitude"])
        except (KeyError, TypeError, ValueError):
            return None
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            return None
        return latitude, longitude

    def _movement_from_accepted(self, latitude: float, longitude: float) -> float | None:
        if self._accepted_lat is None or self._accepted_lon is None:
            return None
        return distance_km(
            self._accepted_lat,
            self._accepted_lon,
            latitude,
            longitude,
        )

    def _elapsed_since_accept(self, now: datetime) -> timedelta:
        return (
            now - self._accepted_at
            if self._accepted_at is not None
            else timedelta.max
        )

    @callback
    def _schedule_coordinator_refresh(self, reason: str) -> None:
        """Schedule a coordinator refresh tied to this config-entry lifecycle."""
        self.entry.async_create_task(
            self.hass,
            self.async_request_refresh(),
            name=f"{DOMAIN} {reason} refresh",
            eager_start=True,
        )

    def _schedule_delayed_refresh(self, delay_seconds: float) -> None:
        if self._delayed_refresh_unsub is not None:
            return

        @callback
        def _run(_now: datetime) -> None:
            self._delayed_refresh_unsub = None
            self._schedule_coordinator_refresh("delayed tracker")

        self._delayed_refresh_unsub = async_call_later(
            self.hass, max(1.0, delay_seconds), _run
        )

    def _cancel_delayed_refresh(self) -> None:
        if self._delayed_refresh_unsub is not None:
            self._delayed_refresh_unsub()
            self._delayed_refresh_unsub = None

    def _tracker_change_requires_refresh(
        self, coordinates: tuple[float, float], now: datetime
    ) -> bool:
        """Filter tracker chatter before it can trigger weather API traffic."""
        latitude, longitude = coordinates
        movement = self._movement_from_accepted(latitude, longitude)
        if movement is None:
            return True
        if movement < MIN_POSITION_CHANGE_KM:
            return False
        if movement >= IMMEDIATE_TRACK_DISTANCE_KM:
            self._cancel_delayed_refresh()
            return True

        throttle = self._tracking_interval()
        elapsed = self._elapsed_since_accept(now)
        if elapsed >= throttle:
            self._cancel_delayed_refresh()
            return True

        self._schedule_delayed_refresh((throttle - elapsed).total_seconds())
        return False

    async def async_start_tracking(self) -> None:
        """Subscribe to location changes for tracked entries."""
        if self._tracker_unsub is not None:
            self._tracker_unsub()
            self._tracker_unsub = None

        if self._mode() != MODE_TRACK:
            return
        entity_id = self._tracker_entity_id()
        if not entity_id:
            return

        @callback
        def _on_tracker_change(event: Event) -> None:
            new_state = event.data.get("new_state")
            coordinates = self._coordinates_from_state(
                new_state if isinstance(new_state, State) else None
            )
            if coordinates is None:
                return
            if self._tracker_change_requires_refresh(coordinates, dt_util.utcnow()):
                self._schedule_coordinator_refresh("tracker event")

        self._tracker_unsub = async_track_state_change_event(
            self.hass, [entity_id], _on_tracker_change
        )

    async def async_shutdown(self) -> None:
        """Release our resources and then shut down DataUpdateCoordinator itself."""
        if self._tracker_unsub is not None:
            self._tracker_unsub()
            self._tracker_unsub = None
        self._cancel_delayed_refresh()
        await self._store.async_save(self._runtime_snapshot())
        await super().async_shutdown()

    def _runtime_snapshot(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if self._accepted_lat is not None:
            result["latitude"] = self._accepted_lat
        if self._accepted_lon is not None:
            result["longitude"] = self._accepted_lon
        if self._accepted_at is not None:
            result["accepted_at"] = self._accepted_at.isoformat()
        if self.location_name:
            result["location_name"] = self.location_name
        if self._last_geocode_at is not None:
            result["geocoded_at"] = self._last_geocode_at.isoformat()
        return result

    def _accept_coordinates(self, latitude: float, longitude: float, now: datetime) -> None:
        self._accepted_lat = latitude
        self._accepted_lon = longitude
        self._accepted_at = now
        self._cancel_delayed_refresh()

    async def _resolve_tracking_coordinates(
        self, now: datetime
    ) -> tuple[float, float, bool, float]:
        entity_id = self._tracker_entity_id()
        state = self.hass.states.get(entity_id) if entity_id else None
        candidate = self._coordinates_from_state(state)

        if candidate is None:
            if self._accepted_lat is not None and self._accepted_lon is not None:
                return self._accepted_lat, self._accepted_lon, False, 0.0

            merged = self._merged_config()
            latitude = self._safe_float(merged.get(CONF_LATITUDE))
            longitude = self._safe_float(merged.get(CONF_LONGITUDE))
            if latitude is None:
                latitude = float(self.hass.config.latitude)
            if longitude is None:
                longitude = float(self.hass.config.longitude)
            self._accept_coordinates(latitude, longitude, now)
            return latitude, longitude, True, 0.0

        latitude, longitude = candidate
        movement = self._movement_from_accepted(latitude, longitude)
        if movement is None:
            self._accept_coordinates(latitude, longitude, now)
            return latitude, longitude, True, 0.0
        if movement < MIN_POSITION_CHANGE_KM:
            return self._accepted_lat, self._accepted_lon, False, movement  # type: ignore[return-value]

        throttle = self._tracking_interval()
        elapsed = self._elapsed_since_accept(now)
        if movement >= IMMEDIATE_TRACK_DISTANCE_KM or elapsed >= throttle:
            self._accept_coordinates(latitude, longitude, now)
            return latitude, longitude, True, movement

        self._schedule_delayed_refresh((throttle - elapsed).total_seconds())
        return self._accepted_lat, self._accepted_lon, False, movement  # type: ignore[return-value]

    async def _resolve_static_coordinates(
        self, now: datetime
    ) -> tuple[float, float, bool, float]:
        merged = self._merged_config()
        latitude = self._safe_float(merged.get(CONF_LATITUDE))
        longitude = self._safe_float(merged.get(CONF_LONGITUDE))
        if latitude is None:
            latitude = float(self.hass.config.latitude)
        if longitude is None:
            longitude = float(self.hass.config.longitude)

        movement = self._movement_from_accepted(latitude, longitude)
        if movement is None or movement >= MIN_POSITION_CHANGE_KM:
            self._accept_coordinates(latitude, longitude, now)
            return latitude, longitude, True, movement or 0.0
        return self._accepted_lat, self._accepted_lon, False, movement  # type: ignore[return-value]

    async def _resolve_location_name(
        self,
        latitude: float,
        longitude: float,
        *,
        now: datetime,
        coordinates_changed: bool,
        movement_km: float,
    ) -> tuple[str, bool]:
        """Resolve the real current place; presentation override is handled separately."""
        if not coordinates_changed and self.location_name:
            return self.location_name, False

        merged = self._merged_config()
        try:
            cooldown_minutes = max(
                1,
                int(
                    merged.get(
                        CONF_REVERSE_GEOCODE_COOLDOWN_MIN,
                        DEFAULT_REVERSE_GEOCODE_COOLDOWN_MIN,
                    )
                ),
            )
        except (TypeError, ValueError):
            cooldown_minutes = DEFAULT_REVERSE_GEOCODE_COOLDOWN_MIN

        should_geocode = not self.location_name or self._last_geocode_at is None
        if self._last_geocode_at is not None:
            should_geocode = now - self._last_geocode_at >= timedelta(
                minutes=cooldown_minutes
            )
        if movement_km >= IMMEDIATE_TRACK_DISTANCE_KM:
            should_geocode = True

        if should_geocode:
            name = await async_reverse_geocode(self.hass, latitude, longitude)
            self._last_geocode_at = now
            if name:
                return name, name != self.location_name

        if self.location_name:
            return self.location_name, False
        fallback = coordinate_label(latitude, longitude)
        return fallback, fallback != self.location_name

    async def _sync_presentation(self, presentation_name: str) -> None:
        """Update visible names without touching registry identity or location state."""
        if presentation_name and self.entry.title != presentation_name:
            self.hass.config_entries.async_update_entry(
                self.entry, title=presentation_name
            )

        registry = dr.async_get(self.hass)
        device = registry.async_get_device_by_identifier(
            (DOMAIN, self.entry.entry_id), self.entry.entry_id
        )
        if (
            device is not None
            and not device.name_by_user
            and device.name != presentation_name
        ):
            registry.async_update_device(device.id, name=presentation_name)

    async def _async_update_data(self) -> dict[str, Any]:
        now = dt_util.utcnow()

        if self._mode() == MODE_TRACK:
            latitude, longitude, coordinates_changed, movement = (
                await self._resolve_tracking_coordinates(now)
            )
        else:
            latitude, longitude, coordinates_changed, movement = (
                await self._resolve_static_coordinates(now)
            )

        location_name, name_changed = await self._resolve_location_name(
            latitude,
            longitude,
            now=now,
            coordinates_changed=coordinates_changed,
            movement_km=movement,
        )
        self.location_name = location_name
        presentation_name = self.presentation_name

        try:
            payload = await self._client.async_weather(latitude, longitude)
        except OpenMeteoApiError as err:
            raise UpdateFailed(f"Weather update failed: {err}") from err

        try:
            air_quality = await self._client.async_air_quality(latitude, longitude)
        except OpenMeteoApiError as err:
            _LOGGER.debug("Air-quality update skipped: %s", err)
        else:
            if isinstance(air_quality.get("hourly"), Mapping):
                payload["aq"] = air_quality

        payload["location"] = {
            "latitude": latitude,
            "longitude": longitude,
        }
        payload["location_name"] = location_name
        payload["presentation_name"] = presentation_name
        payload["last_location_update"] = (
            self._accepted_at.isoformat() if self._accepted_at is not None else None
        )
        payload["mode"] = self._mode()

        if coordinates_changed or name_changed:
            await self._store.async_save(self._runtime_snapshot())

        # Also repair a stale title after restart even when the restored place name
        # did not change during this particular refresh.
        if self.entry.title != presentation_name:
            await self._sync_presentation(presentation_name)

        return payload
