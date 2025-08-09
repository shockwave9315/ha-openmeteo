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
from homeassistant.helpers.event import async_track_state_change_event
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
    """Set up Open-Meteo from a config entry."""
    coordinator = OpenMeteoDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(entry.entry_id)


class OpenMeteoDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Open-Meteo data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        self.entry = entry
        self._unsub_listener: Callable | None = None
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
        )

        if self.tracking_mode == TRACKING_MODE_DEVICE:
            self._unsub_listener = async_track_state_change_event(
                self.hass,
                self.tracked_entity_id,
                self._async_tracked_entity_state_change,
            )

    @property
    def tracking_mode(self) -> str:
        """Return the configured tracking mode."""
        return self.entry.options.get(CONF_TRACKING_MODE, self.entry.data.get(CONF_TRACKING_MODE, TRACKING_MODE_FIXED))

    @property
    def tracked_entity_id(self) -> str | None:
        """Return the configured tracked entity ID."""
        return self.entry.options.get(CONF_TRACKED_ENTITY_ID, self.entry.data.get(CONF_TRACKED_ENTITY_ID))
    
    @callback
    def _async_tracked_entity_state_change(self, event: Event) -> None:
        """Handle state changes of the tracked entity."""
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")
        if not new_state or not old_state:
            return
        
        old_coords = (old_state.attributes.get(CONF_LATITUDE), old_state.attributes.get(CONF_LONGITUDE))
        new_coords = (new_state.attributes.get(CONF_LATITUDE), new_state.attributes.get(CONF_LONGITUDE))
        
        if old_coords != new_coords:
            _LOGGER.debug("Tracked entity %s moved, refreshing data", new_state.entity_id)
            self.async_refresh()

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Open-Meteo API."""
        config_data = self.entry.data
        options = self.entry.options
        
        timezone_opt = options.get(CONF_TIME_ZONE, "auto")
        
        if self.tracking_mode == TRACKING_MODE_DEVICE:
            entity_state = self.hass.states.get(self.tracked_entity_id)
            if not entity_state:
                raise UpdateFailed(f"Tracked entity '{self.tracked_entity_id}' not found")
            latitude = entity_state.attributes.get(CONF_LATITUDE)
            longitude = entity_state.attributes.get(CONF_LONGITUDE)
            if latitude is None or longitude is None:
                raise UpdateFailed(f"Tracked entity '{self.tracked_entity_id}' has no location data")
        else:
            latitude = options.get(CONF_LATITUDE, config_data.get(CONF_LATITUDE))
            longitude = options.get(CONF_LONGITUDE, config_data.get(CONF_LONGITUDE))

        if latitude is None or longitude is None:
             raise UpdateFailed("Location data is missing.")

        url_params = {
            "latitude": latitude,
            "longitude": longitude,
            "current_weather": True,
            "daily": ",".join(options.get(CONF_DAILY_VARIABLES, DEFAULT_DAILY_VARIABLES)),
            "hourly": ",".join(options.get(CONF_HOURLY_VARIABLES, DEFAULT_HOURLY_VARIABLES)),
            "forecast_days": 16,
            "forecast_hours": 168,
            "timezone": timezone_opt,
        }

        session = async_get_clientsession(self.hass)
        try:
            async with async_timeout.timeout(10):
                resp = await session.get(URL, params=url_params)
                if resp.status != 200:
                    text = await resp.text()
                    _LOGGER.error("Open-Meteo HTTP %s: %s", resp.status, text[:200])
                    raise UpdateFailed(f"API returned {resp.status}")
                api_data: dict[str, Any] = await resp.json()

        except (asyncio.TimeoutError, aiohttp.ClientError) as e:
            raise UpdateFailed(f"Open-Meteo network error: {e}") from e
        except Exception as e:
            _LOGGER.exception("Unexpected error")
            raise UpdateFailed(f"Unexpected error: {e}") from e

        # Dopasuj hourly data do strefy czasowej użytkownika
        hourly = api_data.get("hourly", {})
        times = hourly.get("time", [])
        if times:
            ha_tz = self.hass.config.time_zone or "UTC"
            user_tz = ZoneInfo(timezone_opt) if timezone_opt != "auto" else ZoneInfo(ha_tz)
            
            # Weryfikacja i parsowanie czasu
            try:
                parsed = [dt_util.parse_datetime(t) for t in times]
                if None in parsed:
                    _LOGGER.warning("Could not parse all time values from API: %s", times)
                    # Użyj tylko parsowalnych dat
                    valid_times = [t for t in parsed if t is not None]
                    if not valid_times:
                        _LOGGER.warning("No valid time values from API. Cannot process hourly data.")
                        hourly.clear()
                        api_data["hourly"] = hourly
                    else:
                        first_future = next((i for i, t in enumerate(valid_times) if t >= dt_util.now(user_tz)), 0)
                        # Aktualizacja hourly
                        for key, arr in list(hourly.items()):
                            if key == "time":
                                continue
                            if isinstance(arr, list) and len(arr) == len(times):
                                hourly[key] = [arr[j] for j, t in enumerate(parsed) if t is not None][first_future:]
                        hourly["time"] = [t.isoformat() for t in valid_times[first_future:]]

                else:
                    # Normalny przepływ
                    parsed_aware = [dt.astimezone(user_tz) for dt in parsed]
                    now = dt_util.now(user_tz)
                    first_future = next((i for i, t in enumerate(parsed_aware) if t >= now), 0)
                    
                    for key, arr in list(hourly.items()):
                        if key == "time":
                            continue
                        if isinstance(arr, list) and len(arr) == len(times):
                            hourly[key] = arr[first_future:]
                    hourly["time"] = [t.isoformat() for t in parsed_aware[first_future:]]
            
            except Exception as e:
                _LOGGER.error("Error processing hourly data: %s", str(e), exc_info=True)
                # Oczyść dane hourly, aby nie powodować dalszych błędów
                hourly.clear()
                api_data["hourly"] = hourly

        api_data["location"] = {
            "latitude": latitude,
            "longitude": longitude,
            "timezone": timezone_opt,
        }

        return api_data