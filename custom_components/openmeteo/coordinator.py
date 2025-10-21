"""Data update coordinator for Open-Meteo."""
from __future__ import annotations

import asyncio
import inspect
import logging
import random
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_AREA_NAME_OVERRIDE,
    CONF_ENTITY_ID,
    CONF_TRACKED_ENTITY_ID,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_UPDATE_INTERVAL,
    CONF_MIN_TRACK_INTERVAL,
    CONF_REVERSE_GEOCODE_COOLDOWN_MIN,
    CONF_OPTIONS_SAVE_COOLDOWN_MIN,
    DEFAULT_MIN_TRACK_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_API_PROVIDER,
    DEFAULT_HOURLY_VARIABLES,
    DEFAULT_DAILY_VARIABLES,
    CONF_MODE,
    CONF_TRACKING_MODE,
    MODE_STATIC,
    MODE_TRACK,
    URL,
    DEFAULT_REVERSE_GEOCODE_COOLDOWN_MIN,
    DEFAULT_OPTIONS_SAVE_COOLDOWN_MIN,
    HTTP_USER_AGENT,
)

# logger
_LOGGER = logging.getLogger(__name__)

# test hook – allow CI to patch this symbol
from homeassistant.helpers.aiohttp_client import async_get_clientsession as _ha_async_get_clientsession  # noqa: E402
async_get_clientsession = _ha_async_get_clientsession  # exported symbol for tests

# --- persist last known place across restarts ---
OPT_LAST_LAT = "last_lat"
OPT_LAST_LON = "last_lon"
OPT_LAST_LOCATION_NAME = "last_location_name"
# ------------------------------------------------


async def async_reverse_geocode(hass: HomeAssistant, lat: float, lon: float) -> str | None:
    """Reverse-geocode to a short place name.
    1) Open-Meteo geocoding → 2) Nominatim fallback.
    Module-level to allow tests to patch this symbol.
    """
    session = async_get_clientsession(hass)
    hass_lang = (getattr(hass.config, "language", None) or "").strip()
    if hass_lang:
        lang_param = hass_lang.split("-", 1)[0]
        accept_language = hass_lang
    else:
        lang_param = "en"
        accept_language = "en"

    headers = {"User-Agent": HTTP_USER_AGENT}

    # 1) Open-Meteo
    try:
        url = "https://geocoding-api.open-meteo.com/v1/reverse"
        params = {
            "latitude": lat,
            "longitude": lon,
            "count": 1,
            "language": lang_param,
            "format": "json",
        }
        async with session.get(
            url, params=params, headers=headers, timeout=10
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"open-meteo geocoding http {resp.status}")
            js = await resp.json()
        results = js.get("results") or []
        if results:
            r = results[0]
            name = r.get("name") or r.get("admin2") or r.get("admin1")
            if name:
                cc = r.get("country_code")
                return f"{name}, {cc}" if cc else name
    except Exception:
        # fallback poniżej
        pass

    # 2) Nominatim fallback
    try:
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {
            "format": "jsonv2",
            "lat": str(lat),
            "lon": str(lon),
            "zoom": "10",
            "accept-language": accept_language,
        }
        async with session.get(
            url, params=params, headers=headers, timeout=10
        ) as resp:
            if resp.status != 200:
                return None
            js = await resp.json()
        address = js.get("address") or {}
        name = address.get("city") or address.get("town") or address.get("village") or js.get("name")
        if name:
            cc = (address.get("country_code") or "").upper()
            return f"{name}, {cc}" if cc else name
    except Exception:
        pass

    return None


_COORDINATOR_ACCEPTS_CONFIG_ENTRY = "config_entry" in inspect.signature(
    DataUpdateCoordinator.__init__
).parameters


class OpenMeteoDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching Open-Meteo data and tracking coordinates."""

    EPS = 1e-4
    # Defaults are overridden per-entry from options
    REVERSE_GEOCODE_COOLDOWN = timedelta(minutes=10)
    OPTIONS_SAVE_COOLDOWN = timedelta(seconds=60)

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator with Home Assistant and config entry.

        Args:
            hass: Home Assistant instance
            entry: ConfigEntry containing integration configuration
        """
        self.entry = entry

        # Determine polling interval (seconds): prefer minutes-based setting
        raw_min = entry.options.get("update_interval_min", entry.data.get("update_interval_min"))
        if raw_min is not None:
            try:
                interval = int(raw_min) * 60
            except (TypeError, ValueError):
                interval = DEFAULT_UPDATE_INTERVAL
        else:
            # fallback to legacy seconds
            raw_sec = entry.options.get(
                CONF_UPDATE_INTERVAL,
                entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
            )
            try:
                interval = int(raw_sec)
            except (TypeError, ValueError):
                interval = DEFAULT_UPDATE_INTERVAL
        if interval < 60:
            interval = 60

        super_kwargs: dict[str, Any] = {
            "hass": hass,
            "logger": _LOGGER,
            "name": "Open-Meteo",
            "update_method": self._async_update_data,
            "update_interval": timedelta(seconds=interval),
        }
        if _COORDINATOR_ACCEPTS_CONFIG_ENTRY:
            super_kwargs["config_entry"] = entry

        super().__init__(**super_kwargs)

        self._cached: tuple[float, float] | None = None
        self._accepted_lat: float | None = None
        self._accepted_lon: float | None = None
        self._accepted_at: datetime | None = None
        self.location_name: str | None = entry.options.get(
            CONF_AREA_NAME_OVERRIDE, entry.data.get(CONF_AREA_NAME_OVERRIDE)
        )
        self.provider: str = entry.options.get("api_provider", DEFAULT_API_PROVIDER)
        self._warned_missing = False
        self._last_data: dict[str, Any] | None = None
        self._last_geocode_at: datetime | None = None
        self._last_options_save_at: datetime | None = None
        self._suppress_next_reload = False
        # Cooldowns from options (fall back to defaults)
        try:
            rg_min = int(entry.options.get(
                CONF_REVERSE_GEOCODE_COOLDOWN_MIN,
                entry.data.get(CONF_REVERSE_GEOCODE_COOLDOWN_MIN, DEFAULT_REVERSE_GEOCODE_COOLDOWN_MIN),
            ))
        except (TypeError, ValueError):
            rg_min = DEFAULT_REVERSE_GEOCODE_COOLDOWN_MIN
        # Options save cooldown: prefer minutes key, fall back to legacy seconds
        opt_seconds: int
        try:
            opt_min = entry.options.get(
                CONF_OPTIONS_SAVE_COOLDOWN_MIN,
                entry.data.get(CONF_OPTIONS_SAVE_COOLDOWN_MIN, None),
            )
            if opt_min is not None:
                opt_seconds = int(opt_min) * 60
            else:
                # legacy seconds
                legacy_sec = entry.options.get(
                    "options_save_cooldown_sec",
                    entry.data.get("options_save_cooldown_sec", DEFAULT_OPTIONS_SAVE_COOLDOWN_MIN * 60),
                )
                opt_seconds = int(legacy_sec)
        except (TypeError, ValueError):
            opt_seconds = DEFAULT_OPTIONS_SAVE_COOLDOWN_MIN * 60

        self._rg_cooldown_td = timedelta(minutes=max(1, rg_min))
        self._opt_save_cooldown_td = timedelta(seconds=max(60, opt_seconds))

        # Back-compat dla __init__.py (track entity)
        self._tracked_entity_id: Optional[str] = None
        self._unsub_tracked: Optional[Callable[[], None]] = None

        # Load last known coords/name from entry options/data (persist across restarts)
        try:
            persisted: dict[str, Any] | None = None
            if OPT_LAST_LAT in entry.options and OPT_LAST_LON in entry.options:
                persisted = entry.options
            elif OPT_LAST_LAT in entry.data and OPT_LAST_LON in entry.data:
                persisted = entry.data

            if persisted is not None:
                self._cached = (
                    float(persisted[OPT_LAST_LAT]),
                    float(persisted[OPT_LAST_LON]),
                )
                self._accepted_lat, self._accepted_lon = self._cached
                self._accepted_at = dt_util.utcnow()
                if not self.location_name:
                    self.location_name = (
                        entry.options.get(OPT_LAST_LOCATION_NAME)
                        or entry.data.get(OPT_LAST_LOCATION_NAME)
                    )
        except Exception:
            # don't block startup on bad persisted values
            pass

    @property
    def last_location_update(self) -> datetime | None:
        """Return timestamp when coordinates were last accepted."""
        return self._accepted_at

    def _current_mode(self) -> str:
        data = {**self.entry.data, **self.entry.options}
        mode = data.get(CONF_MODE) or data.get(CONF_TRACKING_MODE)
        if not mode:
            if data.get(CONF_ENTITY_ID) or data.get(CONF_TRACKED_ENTITY_ID):
                return MODE_TRACK
            return MODE_STATIC
        if mode in (MODE_STATIC, MODE_TRACK):
            return mode
        if mode == "device":
            return MODE_TRACK
        return MODE_STATIC

    # Legacy helper (not used by update; kept for BC)
    async def _reverse_geocode(self, lat: float, lon: float) -> str | None:
        try:
            return await async_reverse_geocode(self.hass, float(lat), float(lon))
        except Exception:
            return None

    def _coords_fallback(self, lat: float, lon: float) -> str:
        """Generate a fallback location name from coordinates."""
        return f"{lat:.2f},{lon:.2f}"

    async def _update_coordinates_from_tracker(
        self, data: dict[str, Any], now: datetime, min_track: int
    ) -> tuple[float | None, float | None, bool]:
        """Update coordinates from tracked entity (MODE_TRACK).

        Args:
            data: Merged config data and options
            now: Current UTC time
            min_track: Minimum tracking interval in minutes

        Returns:
            Tuple of (latitude, longitude, coords_changed)
        """
        ent_id = data.get(CONF_ENTITY_ID) or data.get(CONF_TRACKED_ENTITY_ID)
        state = self.hass.states.get(ent_id) if ent_id else None
        coords_changed = False
        lat = lon = None

        if state and "latitude" in state.attributes and "longitude" in state.attributes:
            try:
                lat = float(state.attributes["latitude"])
                lon = float(state.attributes["longitude"])
                if (
                    self._cached is None
                    or (
                        abs(lat - self._cached[0]) > self.EPS
                        or abs(lon - self._cached[1]) > self.EPS
                    )
                    and (
                        self._accepted_at is None
                        or now - self._accepted_at >= timedelta(minutes=min_track)
                    )
                ):
                    self._cached = (lat, lon)
                    self._accepted_lat = lat
                    self._accepted_lon = lon
                    self._accepted_at = now
                    coords_changed = True
                self._warned_missing = False
            except (TypeError, ValueError) as ex:
                _LOGGER.debug("Failed to parse GPS coordinates from %s: %s", ent_id, ex)
        else:
            # Tracker not ready - use persisted/cached coords
            using_persisted = OPT_LAST_LAT in data and OPT_LAST_LON in data

            if not self._warned_missing:
                if using_persisted or self._cached is not None:
                    _LOGGER.debug(
                        "Tracked entity %s not ready; using last known coordinates",
                        ent_id,
                    )
                else:
                    _LOGGER.warning(
                        "Tracked entity %s missing or lacks GPS attributes; using configured coordinates",
                        ent_id,
                    )
                self._warned_missing = True

            if self._cached is None:
                lat = float(
                    data.get(OPT_LAST_LAT, data.get(CONF_LATITUDE, self.hass.config.latitude))
                )
                lon = float(
                    data.get(OPT_LAST_LON, data.get(CONF_LONGITUDE, self.hass.config.longitude))
                )
                self._cached = (lat, lon)
                self._accepted_lat = lat
                self._accepted_lon = lon
                self._accepted_at = now if self._accepted_at is None else self._accepted_at
                coords_changed = True

        return lat, lon, coords_changed

    async def _update_coordinates_static(
        self, data: dict[str, Any], now: datetime
    ) -> tuple[float, float, bool]:
        """Update coordinates for static mode (MODE_STATIC).

        Args:
            data: Merged config data and options
            now: Current UTC time

        Returns:
            Tuple of (latitude, longitude, coords_changed)
        """
        lat = float(data.get(CONF_LATITUDE, self.hass.config.latitude))
        lon = float(data.get(CONF_LONGITUDE, self.hass.config.longitude))
        coords_changed = False

        if (
            self._cached is None
            or abs(lat - self._cached[0]) > self.EPS
            or abs(lon - self._cached[1]) > self.EPS
        ):
            self._cached = (lat, lon)
            self._accepted_lat = lat
            self._accepted_lon = lon
            self._accepted_at = now if self._accepted_at is None else self._accepted_at
            coords_changed = True
        elif self._accepted_at is None:
            self._accepted_at = now

        return lat, lon, coords_changed

    async def _update_location_name(
        self,
        lat: float,
        lon: float,
        data: dict[str, Any],
        now: datetime,
        prev_name: str | None,
        coords_changed: bool,
    ) -> str:
        """Update location name via reverse geocoding (with cooldown).

        Args:
            lat: Latitude
            lon: Longitude
            data: Merged config data and options
            now: Current UTC time
            prev_name: Previous location name
            coords_changed: Whether coordinates have changed

        Returns:
            Updated location name
        """
        fallback_label = self._coords_fallback(lat, lon)
        needs_loc_refresh = coords_changed or not prev_name or prev_name == fallback_label

        if not needs_loc_refresh:
            return prev_name if prev_name else fallback_label

        # Check for user override first
        if data.get(CONF_AREA_NAME_OVERRIDE):
            return data.get(CONF_AREA_NAME_OVERRIDE)

        # Apply cooldown to avoid excessive reverse-geocoding
        allow_geocode = (
            self._last_geocode_at is None
            or now - self._last_geocode_at >= self._rg_cooldown_td
        )
        if allow_geocode:
            name = await async_reverse_geocode(self.hass, lat, lon)
            self._last_geocode_at = now
            return name or fallback_label

        # Cooldown active - use fallback
        remaining = (self._last_geocode_at + self._rg_cooldown_td - now).total_seconds()
        _LOGGER.debug(
            "Reverse geocode skipped due to cooldown (%.0fs remaining); using fallback %s",
            remaining,
            fallback_label,
        )
        return fallback_label

    def _should_update_entry_title(
        self, new_title: str, fallback: str | None, data: dict[str, Any]
    ) -> bool:
        """Determine whether the config entry title should be updated."""

        if not new_title:
            return False

        current = (self.entry.title or "").strip()
        if new_title == current:
            return False

        # User-provided override always wins.
        if data.get(CONF_AREA_NAME_OVERRIDE):
            return True

        if not current:
            return True

        normalized = current.lower()
        if normalized.startswith("open-meteo"):
            return True

        if fallback and normalized == fallback.lower():
            return True

        return False

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch weather data from API.

        This is the main coordinator update method that:
        1. Updates GPS coordinates (tracking or static mode)
        2. Updates location name via reverse geocoding (with cooldown)
        3. Fetches weather and air quality data
        4. Persists location data to config entry

        Returns:
            Dictionary with weather, air quality, and location metadata

        Raises:
            UpdateFailed: If no valid coordinates or API fetch fails
        """
        data = {**self.entry.data, **self.entry.options}
        mode = self._current_mode()
        min_track = int(data.get(CONF_MIN_TRACK_INTERVAL, DEFAULT_MIN_TRACK_INTERVAL))
        now = dt_util.utcnow()

        prev_name = self.data.get("location_name") if self.data else None
        prev_loc_ts = self.data.get("last_location_update") if self.data else None

        # Step 1: Update coordinates based on mode
        if mode == MODE_TRACK:
            lat, lon, coords_changed = await self._update_coordinates_from_tracker(
                data, now, min_track
            )
        else:
            lat, lon, coords_changed = await self._update_coordinates_static(data, now)

        # Ensure we have valid coordinates
        if lat is None or lon is None:
            if self._cached is not None:
                lat, lon = self._cached
            else:
                lat = float(data.get(OPT_LAST_LAT, data.get(CONF_LATITUDE, self.hass.config.latitude)))
                lon = float(data.get(OPT_LAST_LON, data.get(CONF_LONGITUDE, self.hass.config.longitude)))

        # Step 2: Update location name
        loc_name = await self._update_location_name(
            lat, lon, data, now, prev_name, coords_changed
        )
        last_loc_ts = now.isoformat() if coords_changed else prev_loc_ts
        self.location_name = loc_name

        # Step 3: Update config entry title if needed
        fallback_label = self._coords_fallback(lat, lon)
        if loc_name and self._should_update_entry_title(loc_name, fallback_label, data):
            try:
                self.async_update_entry_no_reload(title=loc_name)
            except (ValueError, KeyError) as ex:
                _LOGGER.debug("Failed to update entry title: %s", ex)

        if not self._cached:
            raise UpdateFailed("No valid coordinates available")
        latitude, longitude = self._cached

        # Fetch weather data
        try:
            weather_data = await self._fetch_weather_data(latitude, longitude)
            self._last_data = weather_data
            
            # Add location metadata
            self._last_data["location"] = {"latitude": latitude, "longitude": longitude}
            self._last_data["location_name"] = loc_name
            self._last_data["last_location_update"] = last_loc_ts
            
            # Try to fetch air quality data (best-effort, non-critical)
            try:
                aq_data = await self._fetch_air_quality(latitude, longitude)
                if aq_data and 'hourly' in aq_data:
                    self._last_data["aq"] = aq_data
                    _LOGGER.debug("Successfully fetched air quality data")
                else:
                    _LOGGER.warning("No air quality data in API response")
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                _LOGGER.warning("Network error fetching air quality data: %s", err)
            except (KeyError, ValueError, TypeError) as err:
                _LOGGER.warning("Invalid air quality data format: %s", err)

            # Step 4: Persist last accepted coords / location name (with cooldown)
            try:
                opts = dict(self.entry.options)
                data_map = dict(self.entry.data)
                need_save_opts = False
                need_save_data = False
                if self._accepted_lat is not None and self._accepted_lon is not None:
                    if (
                        opts.get(OPT_LAST_LAT) != self._accepted_lat
                        or opts.get(OPT_LAST_LON) != self._accepted_lon
                    ):
                        opts[OPT_LAST_LAT] = self._accepted_lat
                        opts[OPT_LAST_LON] = self._accepted_lon
                        need_save_opts = True
                    if (
                        data_map.get(OPT_LAST_LAT) != self._accepted_lat
                        or data_map.get(OPT_LAST_LON) != self._accepted_lon
                    ):
                        data_map[OPT_LAST_LAT] = self._accepted_lat
                        data_map[OPT_LAST_LON] = self._accepted_lon
                        need_save_data = True
                if self.location_name:
                    if opts.get(OPT_LAST_LOCATION_NAME) != self.location_name:
                        opts[OPT_LAST_LOCATION_NAME] = self.location_name
                        need_save_opts = True
                    if data_map.get(OPT_LAST_LOCATION_NAME) != self.location_name:
                        data_map[OPT_LAST_LOCATION_NAME] = self.location_name
                        need_save_data = True
                if need_save_opts or need_save_data:
                    # Save immediately if coords changed; otherwise respect cooldown
                    if coords_changed or self._last_options_save_at is None or (
                        now - self._last_options_save_at >= self._opt_save_cooldown_td
                    ):
                        self.async_update_entry_no_reload(
                            options=opts if need_save_opts else None,
                            data=data_map if need_save_data else None,
                        )
                        self._last_options_save_at = now
                    else:
                        _LOGGER.debug("Options save skipped due to cooldown")
            except (ValueError, KeyError, AttributeError) as ex:
                _LOGGER.debug("Failed to persist location data to config entry: %s", ex)

            return self._last_data
        except UpdateFailed:
            if self._last_data is not None:
                return self._last_data
            raise

    def consume_suppress_reload(self) -> bool:
        """Return True exactly once if the next reload should be suppressed."""
        if self._suppress_next_reload:
            self._suppress_next_reload = False
            return True
        return False

    def async_update_entry_no_reload(
        self,
        *,
        data: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
        title: str | None = None,
    ) -> None:
        """Update the config entry without triggering an automatic reload."""
        self._suppress_next_reload = True
        try:
            self.hass.config_entries.async_update_entry(
                self.entry, data=data, options=options, title=title
            )
        except Exception:
            self._suppress_next_reload = False
            raise

    # Back-compat: wołane z __init__.py (track encji)
    async def _resubscribe_tracked_entity(self, entity_id: Optional[str]) -> None:
        """(Back-compat) Subskrybuj zmiany stanu encji z lokalizacją."""
        # Anuluj poprzednią subskrypcję
        if self._unsub_tracked:
            try:
                self._unsub_tracked()
            except Exception:
                pass
            self._unsub_tracked = None

        self._tracked_entity_id = entity_id
        if not entity_id:
            return

        from homeassistant.helpers.event import async_track_state_change_event

        def _on_state_change(event):
            self.async_request_refresh()

        self._unsub_tracked = async_track_state_change_event(
            self.hass, [entity_id], _on_state_change
        )

    async def _fetch_weather_data(self, latitude: float, longitude: float) -> dict[str, Any]:
        """Fetch weather data from Open-Meteo API with retry logic.

        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate

        Returns:
            Dictionary with weather data from API

        Raises:
            UpdateFailed: If API returns error or network failures after retries
        """
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current_weather": "true",
            "hourly": ",".join(DEFAULT_HOURLY_VARIABLES),
            "daily": ",".join(DEFAULT_DAILY_VARIABLES),
            "temperature_unit": "celsius",
            "windspeed_unit": "kmh",
            "precipitation_unit": "mm",
            "timezone": "auto",
            "timeformat": "iso8601",
        }
        params["current"] = ",".join([
            "temperature_2m",
            "relative_humidity_2m",
            "dewpoint_2m",
            "pressure_msl",
            "wind_speed_10m",
            "wind_direction_10m",
            "wind_gusts_10m",
            "weathercode",
            "cloud_cover",
            "precipitation",
            "visibility",
        ])

        session = async_get_clientsession(self.hass)
        headers = {"User-Agent": HTTP_USER_AGENT}

        # Retry up to 3 times with exponential backoff
        MAX_RETRIES = 3
        for attempt in range(MAX_RETRIES):
            try:
                async with session.get(
                    URL,
                    params=params,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=20),  # 20s total timeout per request
                ) as resp:
                    if resp.status >= 400:
                        text = await resp.text()
                        raise UpdateFailed(f"API error {resp.status}: {text[:100]}")
                    return await resp.json()
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                if attempt == MAX_RETRIES - 1:  # Last attempt
                    raise UpdateFailed(f"Network error: {err}")
                # Exponential backoff: 1.5^0 + jitter, 1.5^1 + jitter, 1.5^2 + jitter
                # = ~1s, ~1.5s, ~2.25s with random jitter to avoid thundering herd
                backoff = 1.5 ** attempt + random.random() / 2
                await asyncio.sleep(backoff)

        raise UpdateFailed("Failed to fetch weather data after multiple attempts")

    async def _fetch_air_quality(self, lat: float, lon: float) -> dict[str, Any] | None:
        """Fetch air quality data from Open-Meteo Air Quality API (best-effort).

        Args:
            lat: Latitude coordinate
            lon: Longitude coordinate

        Returns:
            Dictionary with air quality data, or None if unavailable/error

        Note:
            This is a best-effort fetch. Failures are logged but don't raise exceptions.
        """
        params = {
            "latitude": lat,
            "longitude": lon,
            "timezone": "auto",
            "hourly": [
                "pm2_5",
                "pm10",
                "carbon_monoxide",
                "nitrogen_dioxide",
                "sulphur_dioxide",
                "ozone",
                "us_aqi",
                "european_aqi"
            ],
        }

        session = async_get_clientsession(self.hass)
        headers = {"User-Agent": HTTP_USER_AGENT}

        try:
            async with session.get(
                "https://air-quality-api.open-meteo.com/v1/air-quality",
                params=params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),  # 30s timeout for AQ API
            ) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    _LOGGER.warning("Air Quality API error %d: %s", resp.status, text[:100])
                    return None
                return await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.warning("Network error fetching air quality data: %s", err)
            return None