"""Open-Meteo v2 data coordinator."""
from __future__ import annotations

import asyncio
import logging
import math
import random
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from typing import Any

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

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
    HTTP_USER_AGENT,
    MODE_STATIC,
    MODE_TRACK,
    URL,
)

_LOGGER = logging.getLogger(__name__)

AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
OPEN_METEO_REVERSE_URL = "https://geocoding-api.open-meteo.com/v1/reverse"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"

IMMEDIATE_TRACK_DISTANCE_KM = 10.0
MIN_POSITION_CHANGE_KM = 0.05

CURRENT_FIELDS = (
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "is_day",
    "precipitation",
    "rain",
    "snowfall",
    "weather_code",
    "cloud_cover",
    "pressure_msl",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
)

HOURLY_FIELDS = (
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "dew_point_2m",
    "precipitation",
    "rain",
    "snowfall",
    "precipitation_probability",
    "weather_code",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "pressure_msl",
    "visibility",
    "cloud_cover",
    "is_day",
    "uv_index",
)

DAILY_FIELDS = (
    "temperature_2m_max",
    "temperature_2m_min",
    "apparent_temperature_max",
    "apparent_temperature_min",
    "weather_code",
    "precipitation_sum",
    "precipitation_probability_max",
    "wind_speed_10m_max",
    "wind_direction_10m_dominant",
    "sunrise",
    "sunset",
    "uv_index_max",
)

AQ_FIELDS = (
    "pm2_5",
    "pm10",
    "carbon_monoxide",
    "nitrogen_dioxide",
    "sulphur_dioxide",
    "ozone",
    "us_aqi",
    "european_aqi",
)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return dt_util.parse_datetime(value)
    return None


async def async_reverse_geocode(
    hass: HomeAssistant, latitude: float, longitude: float
) -> str | None:
    """Resolve coordinates to a short city/place label."""
    session = async_get_clientsession(hass)
    language_full = (hass.config.language or "en").strip() or "en"
    language = language_full.split("-", 1)[0]
    headers = {"User-Agent": HTTP_USER_AGENT}

    try:
        async with session.get(
            OPEN_METEO_REVERSE_URL,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "count": 1,
                "language": language,
                "format": "json",
            },
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as response:
            if response.status == 200:
                payload = await response.json()
                results = payload.get("results") or []
                if results:
                    item = results[0]
                    name = item.get("name") or item.get("admin2") or item.get("admin1")
                    if name:
                        country = (item.get("country_code") or "").upper()
                        return f"{name}, {country}" if country else str(name)
    except (aiohttp.ClientError, asyncio.TimeoutError, TypeError, ValueError):
        pass

    try:
        async with session.get(
            NOMINATIM_REVERSE_URL,
            params={
                "format": "jsonv2",
                "lat": str(latitude),
                "lon": str(longitude),
                "zoom": "10",
                "accept-language": language_full,
            },
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as response:
            if response.status != 200:
                return None
            payload = await response.json()
            address = payload.get("address") or {}
            name = (
                address.get("city")
                or address.get("town")
                or address.get("village")
                or address.get("municipality")
                or payload.get("name")
            )
            if not name:
                return None
            country = (address.get("country_code") or "").upper()
            return f"{name}, {country}" if country else str(name)
    except (aiohttp.ClientError, asyncio.TimeoutError, TypeError, ValueError):
        return None


class OpenMeteoDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch weather data while keeping source identity separate from location."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        store: Store[dict[str, Any]],
        restored: Mapping[str, Any] | None = None,
    ) -> None:
        self.entry = entry
        self._store = store
        self.provider = "open_meteo"

        merged = self._merged_config()
        raw_minutes = merged.get(CONF_UPDATE_INTERVAL_MIN)
        if raw_minutes is not None:
            try:
                update_seconds = max(60, int(raw_minutes) * 60)
            except (TypeError, ValueError):
                update_seconds = DEFAULT_UPDATE_INTERVAL
        else:
            try:
                update_seconds = max(
                    60, int(merged.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL))
                )
            except (TypeError, ValueError):
                update_seconds = DEFAULT_UPDATE_INTERVAL

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}-{entry.entry_id}",
            config_entry=entry,
            update_interval=timedelta(seconds=update_seconds),
        )

        restored = dict(restored or {})
        self._accepted_lat = self._safe_float(restored.get("latitude"))
        self._accepted_lon = self._safe_float(restored.get("longitude"))
        self._accepted_at = _parse_datetime(restored.get("accepted_at"))
        self.location_name = (
            str(restored["location_name"])
            if restored.get("location_name")
            else None
        )
        self._last_geocode_at = _parse_datetime(restored.get("geocoded_at"))
        self._last_geocode_coords: tuple[float, float] | None = None
        geocode_lat = self._safe_float(restored.get("geocode_latitude"))
        geocode_lon = self._safe_float(restored.get("geocode_longitude"))
        if geocode_lat is not None and geocode_lon is not None:
            self._last_geocode_coords = (geocode_lat, geocode_lon)

        self._tracker_unsub: Callable[[], None] | None = None
        self._delayed_refresh_unsub: Callable[[], None] | None = None
        self._suppress_next_reload = False

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _merged_config(self) -> dict[str, Any]:
        return {**dict(self.entry.data or {}), **dict(self.entry.options or {})}

    def _mode(self) -> str:
        merged = self._merged_config()
        mode = merged.get(CONF_MODE)
        if mode in (MODE_STATIC, MODE_TRACK):
            return mode
        if merged.get(CONF_ENTITY_ID) or merged.get(CONF_TRACKED_ENTITY_ID):
            return MODE_TRACK
        return MODE_STATIC

    def _tracker_entity_id(self) -> str | None:
        merged = self._merged_config()
        value = merged.get(CONF_ENTITY_ID) or merged.get(CONF_TRACKED_ENTITY_ID)
        return str(value) if value else None

    async def async_start_tracking(self) -> None:
        """Subscribe to tracker changes so location changes are event driven."""
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
            self.async_request_refresh()

        self._tracker_unsub = async_track_state_change_event(
            self.hass, [entity_id], _on_tracker_change
        )

    async def async_shutdown(self) -> None:
        if self._tracker_unsub is not None:
            self._tracker_unsub()
            self._tracker_unsub = None
        if self._delayed_refresh_unsub is not None:
            self._delayed_refresh_unsub()
            self._delayed_refresh_unsub = None
        await self._store.async_save(self._runtime_snapshot())

    def consume_internal_update(self) -> bool:
        """Consume one config-entry update initiated only for presentation."""
        if not self._suppress_next_reload:
            return False
        self._suppress_next_reload = False
        return True

    def _runtime_snapshot(self) -> dict[str, Any]:
        snapshot: dict[str, Any] = {}
        if self._accepted_lat is not None:
            snapshot["latitude"] = self._accepted_lat
        if self._accepted_lon is not None:
            snapshot["longitude"] = self._accepted_lon
        if self._accepted_at is not None:
            snapshot["accepted_at"] = self._accepted_at.isoformat()
        if self.location_name:
            snapshot["location_name"] = self.location_name
        if self._last_geocode_at is not None:
            snapshot["geocoded_at"] = self._last_geocode_at.isoformat()
        if self._last_geocode_coords is not None:
            snapshot["geocode_latitude"] = self._last_geocode_coords[0]
            snapshot["geocode_longitude"] = self._last_geocode_coords[1]
        return snapshot

    def _schedule_delayed_refresh(self, delay_seconds: float) -> None:
        if self._delayed_refresh_unsub is not None:
            return

        @callback
        def _run(_now: datetime) -> None:
            self._delayed_refresh_unsub = None
            self.async_request_refresh()

        self._delayed_refresh_unsub = async_call_later(
            self.hass, max(1.0, delay_seconds), _run
        )

    def _accept_coordinates(self, lat: float, lon: float, now: datetime) -> None:
        self._accepted_lat = lat
        self._accepted_lon = lon
        self._accepted_at = now
        if self._delayed_refresh_unsub is not None:
            self._delayed_refresh_unsub()
            self._delayed_refresh_unsub = None

    async def _resolve_tracking_coordinates(
        self, now: datetime
    ) -> tuple[float, float, bool, float]:
        merged = self._merged_config()
        entity_id = self._tracker_entity_id()
        state = self.hass.states.get(entity_id) if entity_id else None

        candidate_lat: float | None = None
        candidate_lon: float | None = None
        if state is not None:
            candidate_lat = self._safe_float(state.attributes.get("latitude"))
            candidate_lon = self._safe_float(state.attributes.get("longitude"))

        if candidate_lat is None or candidate_lon is None:
            if self._accepted_lat is not None and self._accepted_lon is not None:
                return self._accepted_lat, self._accepted_lon, False, 0.0
            lat = self._safe_float(merged.get(CONF_LATITUDE))
            lon = self._safe_float(merged.get(CONF_LONGITUDE))
            if lat is None:
                lat = float(self.hass.config.latitude)
            if lon is None:
                lon = float(self.hass.config.longitude)
            self._accept_coordinates(lat, lon, now)
            return lat, lon, True, 0.0

        if self._accepted_lat is None or self._accepted_lon is None:
            self._accept_coordinates(candidate_lat, candidate_lon, now)
            return candidate_lat, candidate_lon, True, 0.0

        distance = _haversine_km(
            self._accepted_lat,
            self._accepted_lon,
            candidate_lat,
            candidate_lon,
        )
        if distance < MIN_POSITION_CHANGE_KM:
            return self._accepted_lat, self._accepted_lon, False, distance

        try:
            min_track_minutes = max(
                1, int(merged.get(CONF_MIN_TRACK_INTERVAL, DEFAULT_MIN_TRACK_INTERVAL))
            )
        except (TypeError, ValueError):
            min_track_minutes = DEFAULT_MIN_TRACK_INTERVAL

        elapsed = (
            now - self._accepted_at
            if self._accepted_at is not None
            else timedelta.max
        )
        throttle = timedelta(minutes=min_track_minutes)

        if distance >= IMMEDIATE_TRACK_DISTANCE_KM or elapsed >= throttle:
            self._accept_coordinates(candidate_lat, candidate_lon, now)
            return candidate_lat, candidate_lon, True, distance

        self._schedule_delayed_refresh((throttle - elapsed).total_seconds())
        return self._accepted_lat, self._accepted_lon, False, distance

    async def _resolve_static_coordinates(
        self, now: datetime
    ) -> tuple[float, float, bool, float]:
        merged = self._merged_config()
        lat = self._safe_float(merged.get(CONF_LATITUDE))
        lon = self._safe_float(merged.get(CONF_LONGITUDE))
        if lat is None:
            lat = float(self.hass.config.latitude)
        if lon is None:
            lon = float(self.hass.config.longitude)

        if self._accepted_lat is None or self._accepted_lon is None:
            self._accept_coordinates(lat, lon, now)
            return lat, lon, True, 0.0

        distance = _haversine_km(self._accepted_lat, self._accepted_lon, lat, lon)
        if distance >= MIN_POSITION_CHANGE_KM:
            self._accept_coordinates(lat, lon, now)
            return lat, lon, True, distance
        return self._accepted_lat, self._accepted_lon, False, distance

    async def _resolve_location_name(
        self,
        lat: float,
        lon: float,
        *,
        now: datetime,
        coordinates_changed: bool,
        movement_km: float,
    ) -> tuple[str, bool]:
        merged = self._merged_config()
        override = str(merged.get(CONF_AREA_NAME_OVERRIDE) or "").strip()
        if override:
            changed = override != self.location_name
            return override, changed

        if not coordinates_changed and self.location_name:
            return self.location_name, False

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

        can_geocode = self._last_geocode_at is None
        if self._last_geocode_at is not None:
            can_geocode = now - self._last_geocode_at >= timedelta(
                minutes=cooldown_minutes
            )
        if movement_km >= IMMEDIATE_TRACK_DISTANCE_KM:
            can_geocode = True
        if not self.location_name:
            can_geocode = True

        if can_geocode:
            name = await async_reverse_geocode(self.hass, lat, lon)
            self._last_geocode_at = now
            self._last_geocode_coords = (lat, lon)
            if name:
                changed = name != self.location_name
                return name, changed

        if self.location_name:
            return self.location_name, False
        fallback = f"{lat:.4f}, {lon:.4f}"
        return fallback, fallback != self.location_name

    async def _sync_presentation(self, location_name: str) -> None:
        """Update UI labels without changing any entity identity."""
        if location_name and self.entry.title != location_name:
            self._suppress_next_reload = True
            self.hass.config_entries.async_update_entry(
                self.entry, title=location_name
            )

        device_registry = dr.async_get(self.hass)
        device = device_registry.async_get_device_by_identifier(
            (DOMAIN, self.entry.entry_id), self.entry.entry_id
        )
        if (
            device is not None
            and not device.name_by_user
            and device.name != location_name
        ):
            device_registry.async_update_device(device.id, name=location_name)

    async def _request_json(
        self,
        url: str,
        params: Mapping[str, Any],
        *,
        timeout_seconds: int,
        retries: int = 3,
    ) -> dict[str, Any]:
        session = async_get_clientsession(self.hass)
        headers = {"User-Agent": HTTP_USER_AGENT}
        last_error: Exception | None = None

        for attempt in range(retries):
            try:
                async with session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=timeout_seconds),
                ) as response:
                    if response.status >= 400:
                        body = await response.text()
                        raise UpdateFailed(
                            f"Open-Meteo HTTP {response.status}: {body[:160]}"
                        )
                    payload = await response.json()
                    if not isinstance(payload, dict):
                        raise UpdateFailed("Open-Meteo returned a non-object response")
                    return payload
            except UpdateFailed:
                raise
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                last_error = err
                if attempt + 1 >= retries:
                    break
                await asyncio.sleep((1.5**attempt) + random.random() / 2)

        raise UpdateFailed(f"Open-Meteo network error: {last_error}")

    async def _fetch_weather_data(self, lat: float, lon: float) -> dict[str, Any]:
        payload = await self._request_json(
            URL,
            {
                "latitude": lat,
                "longitude": lon,
                "current": ",".join(CURRENT_FIELDS),
                "hourly": ",".join(HOURLY_FIELDS),
                "daily": ",".join(DAILY_FIELDS),
                "temperature_unit": "celsius",
                "wind_speed_unit": "kmh",
                "precipitation_unit": "mm",
                "timezone": "auto",
                "timeformat": "iso8601",
            },
            timeout_seconds=20,
        )

        current = payload.get("current") or {}
        if isinstance(current, dict):
            payload["current_weather"] = {
                "temperature": current.get("temperature_2m"),
                "windspeed": current.get("wind_speed_10m"),
                "winddirection": current.get("wind_direction_10m"),
                "weathercode": current.get("weather_code"),
                "is_day": current.get("is_day"),
            }
        return payload

    async def _fetch_air_quality(self, lat: float, lon: float) -> dict[str, Any] | None:
        try:
            return await self._request_json(
                AIR_QUALITY_URL,
                {
                    "latitude": lat,
                    "longitude": lon,
                    "hourly": ",".join(AQ_FIELDS),
                    "timezone": "auto",
                },
                timeout_seconds=20,
                retries=2,
            )
        except UpdateFailed as err:
            _LOGGER.debug("Air-quality update skipped: %s", err)
            return None

    async def _async_update_data(self) -> dict[str, Any]:
        now = dt_util.utcnow()
        if self._mode() == MODE_TRACK:
            lat, lon, coordinates_changed, movement_km = (
                await self._resolve_tracking_coordinates(now)
            )
        else:
            lat, lon, coordinates_changed, movement_km = (
                await self._resolve_static_coordinates(now)
            )

        old_location_name = self.location_name
        location_name, name_changed = await self._resolve_location_name(
            lat,
            lon,
            now=now,
            coordinates_changed=coordinates_changed,
            movement_km=movement_km,
        )
        self.location_name = location_name

        payload = await self._fetch_weather_data(lat, lon)
        aq = await self._fetch_air_quality(lat, lon)
        if aq and isinstance(aq.get("hourly"), dict):
            payload["aq"] = aq

        payload["location"] = {"latitude": lat, "longitude": lon}
        payload["location_name"] = location_name
        payload["last_location_update"] = (
            self._accepted_at.isoformat() if self._accepted_at else None
        )
        payload["mode"] = self._mode()

        if coordinates_changed or name_changed:
            await self._store.async_save(self._runtime_snapshot())

        if name_changed or old_location_name != location_name:
            await self._sync_presentation(location_name)

        return payload
