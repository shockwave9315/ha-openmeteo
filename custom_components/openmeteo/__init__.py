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
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_TIME_ZONE,
    CONF_SCAN_INTERVAL,
    CONF_DAILY_VARIABLES,
    CONF_HOURLY_VARIABLES,
    DEFAULT_DAILY_VARIABLES,
    DEFAULT_HOURLY_VARIABLES,
    DEFAULT_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["weather", "sensor"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Open-Meteo from a config entry."""
    coordinator = OpenMeteoDataUpdateCoordinator(hass, entry)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Pierwszy refresh
    await coordinator.async_config_entry_first_refresh()

    # Ładujemy platformy
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reaguj na zmianę opcji
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
    return unload_ok

async def async_update_options(hass: HomeAssistant, entry: ConfigEntry):
    await hass.config_entries.async_reload(entry.entry_id)

class OpenMeteoDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching Open-Meteo data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL))
        self.hass = hass
        self.entry = entry

        # scan_interval z opcji / danych
        scan_interval = entry.options.get(
            CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        try:
            scan_interval = int(scan_interval)
        except (TypeError, ValueError):
            scan_interval = DEFAULT_SCAN_INTERVAL
        self.update_interval = timedelta(seconds=scan_interval)

    # helper: bezpieczne parsowanie czasu i lokalizacja do user_tz
    def _om_parse_time_local_safe(self, time_str: str, user_tz: ZoneInfo) -> datetime:
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

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the Open-Meteo API."""
        latitude = self.entry.data.get(CONF_LATITUDE)
        longitude = self.entry.data.get(CONF_LONGITUDE)
        timezone_opt = self.entry.data.get(CONF_TIME_ZONE, "auto")

        hourly_vars = self.entry.options.get(
            CONF_HOURLY_VARIABLES, self.entry.data.get(CONF_HOURLY_VARIABLES, DEFAULT_HOURLY_VARIABLES)
        )
        daily_vars = self.entry.options.get(
            CONF_DAILY_VARIABLES, self.entry.data.get(CONF_DAILY_VARIABLES, DEFAULT_DAILY_VARIABLES)
        )

        # Upewnij się, że są potrzebne pola dla sensorów
        if "pressure_msl" not in hourly_vars:
            hourly_vars.append("pressure_msl")
        if "surface_pressure" not in hourly_vars:
            hourly_vars.append("surface_pressure")
        if "visibility" not in hourly_vars:
            hourly_vars.append("visibility")

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current_weather": "true",
            "hourly": ",".join(hourly_vars),
            "daily": ",".join(daily_vars),
            "timezone": timezone_opt,
            "windspeed_unit": "kmh",
            "precipitation_unit": "mm",
        }

        session = async_get_clientsession(self.hass)

        try:
            async with async_timeout.timeout(30):
                async with session.get(API_URL, params=params) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        _LOGGER.error(
                            "Error %s from Open-Meteo API: %s",
                            response.status,
                            error_text[:200],
                        )
                        raise UpdateFailed(f"Error {response.status} from Open-Meteo API")

                    data: dict[str, Any] = await response.json()

                    data["location"] = {
                        "latitude": latitude,
                        "longitude": longitude,
                        "timezone": timezone_opt,
                    }

                    # Przycięcie hourly do przyszłości w strefie użytkownika
                    if "hourly" in data and "time" in data["hourly"]:
                        try:
                            # 'auto' = strefa HA (nie UTC)
                            ha_tz = self.hass.config.time_zone or "UTC"
                            user_tz = ZoneInfo(timezone_opt) if timezone_opt != "auto" else ZoneInfo(ha_tz)

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

        except (asyncio.TimeoutError, aiohttp.ClientError) as e:
            _LOGGER.error("Error fetching data from Open-Meteo: %s", str(e))
            raise UpdateFailed(f"Error communicating with Open-Meteo API: {e}") from e
        except Exception as e:
            _LOGGER.exception("Unexpected error while updating Open-Meteo data: %s", str(e))
            raise UpdateFailed(f"Unexpected error: {e}") from e
