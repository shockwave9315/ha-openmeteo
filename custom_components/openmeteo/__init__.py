"""The Open-Meteo integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any
from datetime import datetime
from zoneinfo import ZoneInfo

import aiohttp
import async_timeout
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_DAILY_VARIABLES,
    CONF_HOURLY_VARIABLES,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_SCAN_INTERVAL,
    CONF_TIME_ZONE,
    DEFAULT_DAILY_VARIABLES,
    DEFAULT_HOURLY_VARIABLES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    URL,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["weather", "sensor"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Open-Meteo from a config entry."""
    coordinator = OpenMeteoDataUpdateCoordinator(hass, entry)
    
    await coordinator.async_config_entry_first_refresh()
    
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
    
    return unload_ok

async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options."""
    await hass.config_entries.async_reload(entry.entry_id)

class OpenMeteoDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the Open-Meteo API."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        self.hass = hass
        self.entry = entry
        self._data: dict[str, Any] = {}
        
        scan_interval_seconds = entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        
        if not isinstance(scan_interval_seconds, int):
            scan_interval_seconds = int(scan_interval_seconds)
        
        update_interval = timedelta(seconds=scan_interval_seconds)
        
        super().__init__(
            hass,
            _LOGGER,
            name="Open-Meteo",
            update_interval=update_interval,
        )
        
        self.scan_interval_seconds = scan_interval_seconds

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Open-Meteo API."""
        
        latitude_from_config = self.entry.data.get(CONF_LATITUDE)
        
        # Nowa, POPRAWIONA logika do pobierania lokalizacji
        if latitude_from_config and latitude_from_config.startswith('device_tracker.'):
            device_tracker_state = self.hass.states.get(latitude_from_config)
            if device_tracker_state and 'latitude' in device_tracker_state.attributes:
                latitude = device_tracker_state.attributes['latitude']
                longitude = device_tracker_state.attributes['longitude']
            else:
                _LOGGER.warning(f"Nie udało się pobrać lokalizacji z encji '{latitude_from_config}'. Używam domyślnych koordynatów Home Assistant.")
                latitude = self.hass.config.latitude
                longitude = self.hass.config.longitude
        else:
            # Użyj stałych koordynatów z konfiguracji, jeśli nie ma device_tracker
            latitude = self.hass.config.latitude
            longitude = self.hass.config.longitude
            
            # W tym miejscu musimy obsłużyć przypadek, gdy w self.entry.data nie ma kluczy 'latitude' i 'longitude',
            # co powodowało błąd 'KeyError'.
            if CONF_LATITUDE in self.entry.data:
                latitude = self.entry.data[CONF_LATITUDE]
            if CONF_LONGITUDE in self.entry.data:
                longitude = self.entry.data[CONF_LONGITUDE]

        timezone_conf = self.entry.data.get(CONF_TIME_ZONE, "auto")

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
            "timezone": timezone_conf,
            "current_weather": "true",
            "hourly": ",".join(sorted(set(hourly_vars))),
            "daily": ",".join(sorted(set(daily_vars))),
            "temperature_unit": "celsius",
            "windspeed_unit": "kmh",
            "precipitation_unit": "mm",
        }

        session = async_get_clientsession(self.hass)

        try:
            async with async_timeout.timeout(10):
                async with session.get(URL, params=params) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        _LOGGER.error(
                            "Error %s from Open-Meteo API: %s",
                            response.status,
                            error_text[:200],
                        )
                        raise UpdateFailed(f"Error {response.status} from Open-Meteo API")

                    data = await response.json()

                    data["location"] = {
                        "latitude": latitude,
                        "longitude": longitude,
                        "timezone": timezone_conf,
                    }

                    if "hourly" in data and "time" in data["hourly"]:
                        try:
                            user_tz = ZoneInfo(timezone_conf) if timezone_conf != "auto" else dt_util.get_default_time_zone()
                            now = dt_util.now(user_tz)
                            times = data["hourly"]["time"]
                            future_indices = []

                            for i, time_str in enumerate(times):
                                try:
                                    dt = self._om_parse_time_local_safe(time_str, user_tz)
                                    if dt >= now:
                                        future_indices.append(i)
                                except (ValueError, TypeError) as e:
                                    _LOGGER.debug("Error parsing time %s: %s", time_str, e)
                                    continue

                            if future_indices:
                                first_future = future_indices[0]
                                for key in list(data["hourly"].keys()):
                                    if isinstance(data["hourly"][key], list) and len(data["hourly"][key]) == len(times):
                                        data["hourly"][key] = data["hourly"][key][first_future:]

                        except Exception as e:
                            _LOGGER.error("Error processing hourly data: %s", str(e), exc_info=True)

                    return data

        except asyncio.TimeoutError as err:
            _LOGGER.error("Timeout while connecting to Open-Meteo API")
            raise UpdateFailed("Timeout while connecting to Open-Meteo API") from err
        except aiohttp.ClientError as err:
            _LOGGER.error("Error connecting to Open-Meteo API: %s", err)
            raise UpdateFailed(f"Error connecting to Open-Meteo API: {err}") from err
        except Exception as err:
            _LOGGER.error("Unexpected error from Open-Meteo API: %s", err, exc_info=True)
            raise UpdateFailed(f"Unexpected error from Open-Meteo API: {err}") from err

    def _om_parse_time_local_safe(self, time_str, user_tz):
        """Parse Open-Meteo time that may be UTC (with Z) or local w/o offset; return aware datetime in user tz."""
        ts = time_str
        try:
            dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
        except Exception:
            if '.' in ts:
                ts2 = ts.split('.', 1)[0]
                dt = datetime.fromisoformat(ts2.replace('Z', '+00:00'))
            else:
                raise
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=user_tz)
        return dt.astimezone(user_tz)