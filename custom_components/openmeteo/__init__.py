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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
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
    CONF_TRACKED_ENTITY_ID,
    CONF_TRACKING_MODE,
    DEFAULT_DAILY_VARIABLES,
    DEFAULT_HOURLY_VARIABLES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    TRACKING_MODE_DEVICE,
    TRACKING_MODE_FIXED,
    URL,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["weather", "sensor"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Open-Meteo from a config entry."""
    coordinator = OpenMeteoDataUpdateCoordinator(hass, entry)
    await coordinator.async_initialize()

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    if coordinator.unsub_tracker:
        coordinator.unsub_tracker()

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


class OpenMeteoDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Open-Meteo data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the data update coordinator."""
        self.config_entry = entry
        self.hass = hass
        self.unsub_tracker = None
        self.latitude = self._get_config(CONF_LATITUDE, hass.config.latitude)
        self.longitude = self._get_config(CONF_LONGITUDE, hass.config.longitude)

        scan_interval = timedelta(
            minutes=self._get_config(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=scan_interval,
        )

    async def async_initialize(self) -> None:
        """Initialize the coordinator."""
        tracking_mode = self._get_config(CONF_TRACKING_MODE, TRACKING_MODE_FIXED)
        if tracking_mode == TRACKING_MODE_DEVICE:
            entity_id = self._get_config(CONF_TRACKED_ENTITY_ID)
            if entity_id:
                self.unsub_tracker = async_track_state_change_event(
                    self.hass, [entity_id], self._async_handle_location_update
                )
                # Set initial location from tracked entity
                await self._update_location_from_entity(entity_id)

    @callback
    async def _async_handle_location_update(self, event) -> None:
        """Handle location update from tracked entity."""
        new_state = event.data.get("new_state")
        if not new_state or not new_state.attributes:
            return

        self.latitude = new_state.attributes.get("latitude")
        self.longitude = new_state.attributes.get("longitude")
        await self.async_request_refresh()

    async def _update_location_from_entity(self, entity_id: str) -> None:
        """Update location from the tracked entity's current state."""
        state = self.hass.states.get(entity_id)
        if state and state.attributes:
            self.latitude = state.attributes.get("latitude", self.latitude)
            self.longitude = state.attributes.get("longitude", self.longitude)

    def _get_config(self, key: str, default: Any = None) -> Any:
        """Get configuration from options or data."""
        return self.config_entry.options.get(key, self.config_entry.data.get(key, default))

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Open-Meteo API."""
        timezone = self._get_config(CONF_TIME_ZONE, "auto")

        default_hourly = list(DEFAULT_HOURLY_VARIABLES)
        default_daily = list(DEFAULT_DAILY_VARIABLES)

        hourly_variables = self._get_config(CONF_HOURLY_VARIABLES, default_hourly)
        daily_variables = self._get_config(CONF_DAILY_VARIABLES, default_daily)

        params = {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "current_weather": "true",
            "hourly": ",".join(hourly_variables),
            "daily": ",".join(daily_variables),
            "timezone": timezone,
            "forecast_days": 16,
            "temperature_unit": "celsius",
            "windspeed_unit": "kmh",
            "precipitation_unit": "mm",
            "timeformat": "unixtime",
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
                        "timezone": timezone,
                    }

                    if "hourly" in data and "time" in data["hourly"]:
                        try:
                            user_tz = ZoneInfo(timezone if timezone != "auto" else "UTC")
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