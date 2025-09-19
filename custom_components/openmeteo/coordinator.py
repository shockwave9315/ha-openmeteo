"""Data update coordinator for Open-Meteo."""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

import aiohttp
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
    CONF_OPTIONS_SAVE_COOLDOWN_SEC,
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
    DEFAULT_OPTIONS_SAVE_COOLDOWN_SEC,
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

    # 1) Open-Meteo
    try:
        url = "https://geocoding-api.open-meteo.com/v1/reverse"
        params = {"latitude": lat, "longitude": lon, "count": 1, "language": "pl", "format": "json"}
        async with session.get(url, params=params, timeout=10) as resp:
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
            "accept-language": "pl",
        }
        headers = {"User-Agent": "HomeAssistant-OpenMeteo/1.0 (+https://www.home-assistant.io)"}
        async with session.get(url, params=params, headers=headers, timeout=10) as resp:
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


class OpenMeteoDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching Open-Meteo data and tracking coordinates."""

    EPS = 1e-4
    # Defaults are overridden per-entry from options
    REVERSE_GEOCODE_COOLDOWN = timedelta(minutes=10)
    OPTIONS_SAVE_COOLDOWN = timedelta(seconds=60)

    def __init__(self, hass: HomeAssistant, entry) -> None:
        self.entry = entry

        interval = entry.options.get(
            CONF_UPDATE_INTERVAL,
            entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        )
        try:
            interval = int(interval)
        except (TypeError, ValueError):
            interval = DEFAULT_UPDATE_INTERVAL
        if interval < 60:
            interval = 60

        super().__init__(
            hass,
            _LOGGER,
            name="Open-Meteo",
            update_method=self._async_update_data,
            update_interval=timedelta(seconds=interval),
        )

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
        # Cooldowns from options (fall back to defaults)
        try:
            rg_min = int(entry.options.get(
                CONF_REVERSE_GEOCODE_COOLDOWN_MIN,
                entry.data.get(CONF_REVERSE_GEOCODE_COOLDOWN_MIN, DEFAULT_REVERSE_GEOCODE_COOLDOWN_MIN),
            ))
        except (TypeError, ValueError):
            rg_min = DEFAULT_REVERSE_GEOCODE_COOLDOWN_MIN
        try:
            opt_sec = int(entry.options.get(
                CONF_OPTIONS_SAVE_COOLDOWN_SEC,
                entry.data.get(CONF_OPTIONS_SAVE_COOLDOWN_SEC, DEFAULT_OPTIONS_SAVE_COOLDOWN_SEC),
            ))
        except (TypeError, ValueError):
            opt_sec = DEFAULT_OPTIONS_SAVE_COOLDOWN_SEC
        self._rg_cooldown_td = timedelta(minutes=max(1, rg_min))
        self._opt_save_cooldown_td = timedelta(seconds=max(10, opt_sec))

        # Back-compat dla __init__.py (track entity)
        self._tracked_entity_id: Optional[str] = None
        self._unsub_tracked: Optional[Callable[[], None]] = None

        # Load last known coords/name from entry.options (persist across restarts)
        try:
            if OPT_LAST_LAT in entry.options and OPT_LAST_LON in entry.options:
                self._cached = (
                    float(entry.options[OPT_LAST_LAT]),
                    float(entry.options[OPT_LAST_LON]),
                )
                self._accepted_lat, self._accepted_lon = self._cached
                self._accepted_at = dt_util.utcnow()
                if not self.location_name:
                    self.location_name = entry.options.get(OPT_LAST_LOCATION_NAME)
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
        url = (
            "https://geocoding-api.open-meteo.com/v1/reverse"
            f"?latitude={lat:.5f}&longitude={lon:.5f}&language=pl&format=json"
        )
        try:
            session = _ha_async_get_clientsession(self.hass)
            async with session.get(url, timeout=10) as resp:
                if resp.status != 200:
                    return None
                js = await resp.json()
                results = js.get("results") or []
                if not results:
                    return None
                r = results[0]
                name = r.get("name") or r.get("admin2") or r.get("admin1")
                country = r.get("country_code")
                if name and country:
                    return f"{name}, {country}"
                return name

        except Exception:
            return None

    def _coords_fallback(self, lat: float, lon: float) -> str:
        return f"{lat:.2f},{lon:.2f}"

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
        data = {**self.entry.data, **self.entry.options}
        mode = self._current_mode()
        min_track = int(data.get(CONF_MIN_TRACK_INTERVAL, DEFAULT_MIN_TRACK_INTERVAL))
        now = dt_util.utcnow()

        prev_name = self.data.get("location_name") if self.data else None
        prev_loc_ts = self.data.get("last_location_update") if self.data else None
        coords_changed = False

        if mode == MODE_TRACK:
            ent_id = data.get(CONF_ENTITY_ID) or data.get(CONF_TRACKED_ENTITY_ID)
            state = self.hass.states.get(ent_id) if ent_id else None

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
                except (TypeError, ValueError):
                    pass
            else:
                # Tracker jeszcze nie gotowy — użyj zapamiętanych koordów; w ostateczności konfig.
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

        else:
            lat = float(data.get(CONF_LATITUDE, self.hass.config.latitude))
            lon = float(data.get(CONF_LONGITUDE, self.hass.config.longitude))
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

        # Location name
        loc_name = prev_name
        last_loc_ts = prev_loc_ts
        # Ensure we have lat/lon for naming even if tracker state not yet provided
        try:
            _ = lat; _ = lon
        except NameError:
            if self._cached is not None:
                lat, lon = self._cached
            else:
                lat = float(data.get(OPT_LAST_LAT, data.get(CONF_LATITUDE, self.hass.config.latitude)))
                lon = float(data.get(OPT_LAST_LON, data.get(CONF_LONGITUDE, self.hass.config.longitude)))
        fallback_label = self._coords_fallback(lat, lon)
        needs_loc_refresh = coords_changed or not prev_name or prev_name == fallback_label
        if needs_loc_refresh:
            if data.get(CONF_AREA_NAME_OVERRIDE):
                loc_name = data.get(CONF_AREA_NAME_OVERRIDE)
            else:
                # Apply cooldown to avoid excessive reverse-geocoding
                allow_geocode = (
                    self._last_geocode_at is None
                    or now - self._last_geocode_at >= self._rg_cooldown_td
                )
                if allow_geocode:
                    name = await async_reverse_geocode(self.hass, lat, lon)
                    self._last_geocode_at = now
                    loc_name = name or fallback_label
                else:
                    _LOGGER.debug(
                        "Reverse geocode skipped due to cooldown; using fallback %s", fallback_label
                    )
                    loc_name = fallback_label
            last_loc_ts = now.isoformat()
            self.location_name = loc_name

        elif self.location_name:
            loc_name = self.location_name

        if loc_name and self._should_update_entry_title(loc_name, fallback_label, data):
            try:
                self.hass.config_entries.async_update_entry(self.entry, title=loc_name)
            except Exception:
                pass

        if not self._cached:
            raise UpdateFailed("No valid coordinates available")
        latitude, longitude = self._cached

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
        params["current"] = ",".join(
            [
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
            ]
        )

        session = async_get_clientsession(self.hass)
        headers = {
            "User-Agent": "HomeAssistant-OpenMeteo/1.0 (+https://www.home-assistant.io)"
        }
        try:
            for attempt in range(3):
                try:
                    async with session.get(
                        URL,
                        params=params,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=20),
                    ) as resp:
                        if resp.status >= 400:
                            text = await resp.text()
                            raise UpdateFailed(f"API error {resp.status}: {text[:100]}")
                        api_data = await resp.json()
                        self._last_data = api_data
                        break
                except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                    if attempt == 2:
                        raise UpdateFailed(f"Network error: {err}")
                    await asyncio.sleep(1.5 ** attempt + random.random() / 2)
            if self._last_data is None:
                raise UpdateFailed("No data received")
            self._last_data["location"] = {"latitude": latitude, "longitude": longitude}
            self._last_data["location_name"] = loc_name
            self._last_data["last_location_update"] = last_loc_ts

            # persist last accepted coords / location name in entry.options
            try:
                opts = dict(self.entry.options)
                need_save = False
                if self._accepted_lat is not None and self._accepted_lon is not None:
                    if opts.get(OPT_LAST_LAT) != self._accepted_lat or opts.get(OPT_LAST_LON) != self._accepted_lon:
                        opts[OPT_LAST_LAT] = self._accepted_lat
                        opts[OPT_LAST_LON] = self._accepted_lon
                        need_save = True
                if self.location_name and opts.get(OPT_LAST_LOCATION_NAME) != self.location_name:
                    opts[OPT_LAST_LOCATION_NAME] = self.location_name
                    need_save = True
                if need_save:
                    # Debounce options persistence to reduce churn
                    if (
                        self._last_options_save_at is None
                        or now - self._last_options_save_at >= self._opt_save_cooldown_td
                    ):
                        self.hass.config_entries.async_update_entry(self.entry, options=opts)
                        self._last_options_save_at = now
                    else:
                        _LOGGER.debug("Options save skipped due to cooldown")
            except Exception:
                pass

            return self._last_data
        except UpdateFailed:
            if self._last_data is not None:
                return self._last_data
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