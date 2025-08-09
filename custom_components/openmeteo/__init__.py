"""The Open-Meteo integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import aiohttp
import async_timeout
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    API_URL,
    DEFAULT_HOURLY_VARIABLES,
    DEFAULT_DAILY_VARIABLES,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_TIME_ZONE,
    CONF_SCAN_INTERVAL,
    CONF_DAILY_VARIABLES,
    CONF_HOURLY_VARIABLES,
    DEFAULT_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Open-Meteo from a config entry."""
    session = async_get_clientsession(hass)
    coordinator = OpenMeteoDataUpdateCoordinator(hass, entry)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await coordinator.async_config_entry_first_refresh()
    hass.config_entries.async_setup_platforms(entry, ["weather", "sensor"])
    return True


class OpenMeteoDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the Open-Meteo API."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        self.hass = hass
        self.entry = entry
        self._data: dict[str, Any] = {}
        
        # Pobierz interwał z konfiguracji lub użyj domyślnego
        scan_interval_seconds = entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        
        # Upewnij się, że to int
        try:
            scan_interval_seconds = int(scan_interval_seconds)
        except (TypeError, ValueError):
            scan_interval_seconds = DEFAULT_SCAN_INTERVAL

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval_seconds),
        )

    @property
    def data(self) -> dict[str, Any]:
        """Return the stored data."""
        return self._data

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Open-Meteo."""
        latitude = self.entry.data[CONF_LATITUDE]
        longitude = self.entry.data[CONF_LONGITUDE]
        timezone = self.entry.data.get(CONF_TIME_ZONE, "auto")

        default_hourly = list(DEFAULT_HOURLY_VARIABLES)
        default_daily = list(DEFAULT_DAILY_VARIABLES)

        if "pressure_msl" not in default_hourly:
            default_hourly.append("pressure_msl")
        if "surface_pressure" not in default_hourly:
            default_hourly.append("surface_pressure")
        if "visibility" not in default_hourly:
            default_hourly.append("visibility")

        daily_vars = self.entry.options.get(
            CONF_DAILY_VARIABLES, self.entry.data.get(CONF_DAILY_VARIABLES, default_daily)
        )
        hourly_vars = self.entry.options.get(
            CONF_HOURLY_VARIABLES, self.entry.data.get(CONF_HOURLY_VARIABLES, default_hourly)
        )

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current_weather": "true",
            "hourly": ",".join(hourly_vars),
            "daily": ",".join(daily_vars),
            "timezone": timezone,
            "windspeed_unit": "kmh",
            "precipitation_unit": "mm",
        }

        async with async_timeout.timeout(30):
            async with async_get_clientsession(self.hass).get(API_URL, params=params) as resp:
                if resp.status != 200:
                    raise UpdateFailed(f"API returned {resp.status}")
                data = await resp.json()

        # Uporządkuj czasy do strefy usera i przytnij przeszłość
        if "hourly" in data and "time" in data["hourly"]:
            try:
                # <<< POPRAWKA: 'auto' = strefa HA, nie UTC >>>
                ha_tz = self.hass.config.time_zone or "UTC"
                user_tz = ZoneInfo(timezone) if timezone != "auto" else ZoneInfo(ha_tz)
                now = dt_util.now(user_tz)
                times = data["hourly"]["time"]
                
                def parse_time(time_str: str) -> datetime:
                    # Normalize common Z format
                    ts = time_str
                    try:
                        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                    except Exception:
                        # Try stripping milliseconds if malformed
                        if '.' in ts:
                            ts2 = ts.split('.', 1)[0]
                            dt = datetime.fromisoformat(ts2.replace('Z', '+00:00'))
                        else:
                            raise
                    if dt.tzinfo is None:
                        # Open-Meteo sometimes returns local time without offset when timezone parameter is used.
                        dt = dt.replace(tzinfo=user_tz)
                    return dt.astimezone(user_tz)

                parsed_times = [parse_time(t) for t in times]
                future_idx = next((i for i, t in enumerate(parsed_times) if t >= now), 0)

                # Przytnij listy hourly do przyszłości
                for key, arr in list(data["hourly"].items()):
                    if isinstance(arr, list) and len(arr) == len(times):
                        data["hourly"][key] = arr[future_idx:]
                data["hourly"]["time"] = [t.isoformat() for t in parsed_times[future_idx:]]
            except Exception as err:
                _LOGGER.debug("Hour slicing failed: %s", err)

        self._data = data
        return data
