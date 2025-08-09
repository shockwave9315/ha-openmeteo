"""The Open-Meteo integration."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import timedelta, datetime
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp
import async_timeout
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback, Event
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_state_change_event, async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_DAILY_VARIABLES,
    CONF_HOURLY_VARIABLES,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_SCAN_INTERVAL,
    CONF_TIME_ZONE,
    CONF_TRACKED_ENTITY_ID,
    CONF_TRACKING_MODE,
    DEFAULT_DAILY_VARIABLES,
    DEFAULT_HOURLY_VARIABLES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    URL,
    TRACKING_MODE_DEVICE,
    TRACKING_MODE_FIXED,
)

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["weather", "sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = OpenMeteoDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator = hass.data[DOMAIN].get(entry.entry_id)
        if coordinator:
            if coordinator._unsub_device_listener:
                coordinator._unsub_device_listener()
            # Anuluj oczekujące debounce przy unload
            if coordinator._debounce_refresh:
                coordinator._debounce_refresh()
                coordinator._debounce_refresh = None
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
    return unload_ok


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


class OpenMeteoDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Manage fetching data from Open-Meteo."""
    
    # Epsilon for location change detection, 1e-4 is approximately 11 meters.
    EPS = 1e-4

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._debounce_refresh: Callable | None = None

        scan_interval = entry.options.get(
            CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        try:
            scan_interval = int(scan_interval)
        except (TypeError, ValueError):
            scan_interval = DEFAULT_SCAN_INTERVAL
        
        scan_interval = max(30, min(scan_interval, 6 * 3600))
        
        super().__init__(hass, _LOGGER, name="Open-Meteo", update_interval=timedelta(seconds=scan_interval))

        self._last_device_coords: tuple[float, float] | None = None
        self._listening_entity_id: str | None = None
        self._unsub_device_listener: Callable[[], None] | None = None

    def _ensure_device_listener(self, ent_id: str) -> None:
        if not ent_id:
            return
        
        if self._listening_entity_id and self._listening_entity_id != ent_id:
            self._last_device_coords = None
        
        if self._listening_entity_id == ent_id and self._unsub_device_listener:
            return
        if self._unsub_device_listener:
            self._unsub_device_listener()
            self._unsub_device_listener = None

        @callback
        def _state_changed_event(event: Event):
            new_state = event.data.get("new_state")
            if new_state and ("latitude" in new_state.attributes) and ("longitude" in new_state.attributes):
                try:
                    lat = float(new_state.attributes["latitude"])
                    lon = float(new_state.attributes["longitude"])
                    if self._last_device_coords is None or (
                        abs(lat - self._last_device_coords[0]) > self.EPS
                        or abs(lon - self._last_device_coords[1]) > self.EPS
                    ):
                        self._last_device_coords = (lat, lon)
                        if self._debounce_refresh:
                            self._debounce_refresh()
                        self._debounce_refresh = async_call_later(
                            self.hass, 1.0, lambda _: self.hass.async_create_task(self.async_request_refresh())
                        )
                except (TypeError, ValueError):
                    pass
            else:
                if self._last_device_coords:
                    if self._debounce_refresh:
                        self._debounce_refresh()
                    self._debounce_refresh = async_call_later(
                        self.hass, 1.0, lambda _: self.hass.async_create_task(self.async_request_refresh())
                    )

        self._unsub_device_listener = async_track_state_change_event(self.hass, ent_id, _state_changed_event)
        self._listening_entity_id = ent_id

    def _parse_time_local(self, ts: str, user_tz: ZoneInfo) -> datetime:
        s = ts.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
        except Exception:
            if "." in s:
                s = s.split(".", 1)[0]
                dt = datetime.fromisoformat(s)
            else:
                raise
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=user_tz)
        return dt.astimezone(user_tz)

    async def _async_update_data(self) -> dict[str, Any]:
        opts = self.entry.options
        conf_data = self.entry.data

        mode = opts.get(CONF_TRACKING_MODE, conf_data.get(CONF_TRACKING_MODE, TRACKING_MODE_FIXED))
        tracked = opts.get(CONF_TRACKED_ENTITY_ID, conf_data.get(CONF_TRACKED_ENTITY_ID))
        timezone_opt = opts.get(CONF_TIME_ZONE, conf_data.get(CONF_TIME_ZONE, "auto"))

        if mode != TRACKING_MODE_DEVICE and self._unsub_device_listener:
            _LOGGER.debug("Unsubscribing from device tracker as tracking mode is not 'device'.")
            self._unsub_device_listener()
            self._unsub_device_listener = None
            self._listening_entity_id = None
            # Anuluj debounce przy zmianie trybu, żeby nie odświeżał po przełączeniu
            if self._debounce_refresh:
                self._debounce_refresh()
                self._debounce_refresh = None
        
        latitude = self.hass.config.latitude
        longitude = self.hass.config.longitude

        if mode == TRACKING_MODE_DEVICE and tracked:
            self._ensure_device_listener(tracked)
            st = self.hass.states.get(tracked)
            
            if st and ("latitude" in st.attributes) and ("longitude" in st.attributes):
                try:
                    latitude = float(st.attributes["latitude"])
                    longitude = float(st.attributes["longitude"])
                    self._last_device_coords = (latitude, longitude)
                except (TypeError, ValueError):
                    if self._last_device_coords:
                        latitude, longitude = self._last_device_coords
                        _LOGGER.debug("Invalid coordinates in %s - using last known.", tracked)
                    else:
                        _LOGGER.debug("Invalid coordinates in %s and no last known. Using Home Assistant's coordinates temporarily.", tracked)
            else:
                if self._last_device_coords:
                    latitude, longitude = self._last_device_coords
                    _LOGGER.debug("Missing coordinates in %s - using last known.", tracked)
                else:
                    _LOGGER.debug("Missing coordinates in %s and no last known. Using Home Assistant's coordinates temporarily.", tracked)
        elif mode == TRACKING_MODE_FIXED:
            latitude = opts.get(CONF_LATITUDE, conf_data.get(CONF_LATITUDE, self.hass.config.latitude))
            longitude = opts.get(CONF_LONGITUDE, conf_data.get(CONF_LONGITUDE, self.hass.config.longitude))
        
        if latitude is None or longitude is None:
            raise UpdateFailed("Could not get a valid location to fetch weather data.")

        default_hourly = list(DEFAULT_HOURLY_VARIABLES)
        for add in ("pressure_msl", "surface_pressure", "visibility", "dewpoint_2m", "is_day"):
            if add not in default_hourly:
                default_hourly.append(add)
        default_daily = list(DEFAULT_DAILY_VARIABLES)

        daily_vars = opts.get(CONF_DAILY_VARIABLES, conf_data.get(CONF_DAILY_VARIABLES, default_daily))
        hourly_vars = opts.get(CONF_HOURLY_VARIABLES, conf_data.get(CONF_HOURLY_VARIABLES, default_hourly))

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "timezone": timezone_opt,
            "current_weather": "true",
            "hourly": ",".join(sorted(set(hourly_vars))),
            "daily": ",".join(sorted(set(daily_vars))),
            "temperature_unit": "celsius",
            "windspeed_unit": "kmh",
            "precipitation_unit": "mm",
        }

        session = async_get_clientsession(self.hass)

        try:
            async with async_timeout.timeout(30):
                async with session.get(URL, params=params) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        _LOGGER.error("Open-Meteo HTTP %s: %s", resp.status, text[:200])
                        raise UpdateFailed(f"API returned {resp.status}")
                    api_data: dict[str, Any] = await resp.json()

            api_data["location"] = {
                "latitude": latitude,
                "longitude": longitude,
                "timezone": timezone_opt,
            }

            hourly = api_data.get("hourly", {})
            times = hourly.get("time", [])
            if times:
                ha_tz = self.hass.config.time_zone or "UTC"
                try:
                    user_tz = ZoneInfo(timezone_opt) if timezone_opt != "auto" else ZoneInfo(ha_tz)
                except Exception:
                    _LOGGER.warning("Invalid timezone '%s', falling back to HA timezone.", timezone_opt)
                    user_tz = ZoneInfo(ha_tz)

                parsed = [self._parse_time_local(t, user_tz) for t in times]
                now = dt_util.now(user_tz)
                first_future = next((i for i, t in enumerate(parsed) if t >= now), 0)

                for key, arr in list(hourly.items()):
                    if key == "time":
                        continue
                    if isinstance(arr, list) and len(arr) == len(times):
                        hourly[key] = arr[first_future:]
                hourly["time"] = [t.isoformat() for t in parsed[first_future:]]

            return api_data

        except (asyncio.TimeoutError, aiohttp.ClientError) as e:
            raise UpdateFailed(f"Open-Meteo network error: {e}") from e
        except Exception as e:
            _LOGGER.exception("Unexpected error")
            raise UpdateFailed(f"Unexpected error: {e}") from e