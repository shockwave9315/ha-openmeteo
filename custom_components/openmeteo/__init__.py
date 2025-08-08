"""The Open-Meteo integration with dynamic device tracking."""
from __future__ import annotations

import logging
import asyncio
from datetime import timedelta
from homeassistant.core import HomeAssistant, Event, callback
from homeassistant.core import State
from homeassistant.config_entries import ConfigEntry, ConfigEntryNotReady
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers import (
    entity_registry as er,
    device_registry as dr
)

from .const import (
    CONF_DAILY_VARIABLES,
    CONF_HOURLY_VARIABLES,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_SCAN_INTERVAL,
    CONF_TIME_ZONE,
    CONF_NAME,
    DEFAULT_DAILY_VARIABLES,
    DEFAULT_HOURLY_VARIABLES,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_NAME,
    DEFAULT_USE_DEVICE_NAMES,
    CONF_USE_DEVICE_NAMES,
    CONF_AREA_OVERRIDES,
    DOMAIN,
    URL,
    # NEW: networking options
    CONF_REQUEST_CONNECT_TIMEOUT,
    CONF_REQUEST_TOTAL_TIMEOUT,
    CONF_API_MAX_RETRIES,
    CONF_API_RETRY_BASE,
    DEFAULT_REQUEST_CONNECT_TIMEOUT,
    DEFAULT_REQUEST_TOTAL_TIMEOUT,
    DEFAULT_API_MAX_RETRIES,
    DEFAULT_API_RETRY_BASE,
)

# ... (tu cała reszta Twojego pliku bez zmian – klasy, setup, itd.)

class OpenMeteoCoordinator(DataUpdateCoordinator[dict]):
    # ... (konstruktor i inne metody bez zmian)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Open-Meteo API.
        
        Returns:
            dict: The weather data from the API
            
        Raises:
            UpdateFailed: If there's an error fetching the data or if coordinates are not available
        """
        # (tu Twoja logika budowania params itp. – BEZ ZMIAN do miejsca requestu)

        try:
            import aiohttp
            import async_timeout
            from datetime import datetime, timezone

            # Pełny URL do debug
            from urllib.parse import urlencode
            url = f"{URL}?{urlencode(params, doseq=True)}"
            _LOGGER.debug("Making API request to: %s", url)

            # >>>> ZMIANA: czytamy wartości z opcji i robimy retry <<<<
            opts = self.config_entry.options if hasattr(self, "config_entry") else {}
            connect_timeout = int(opts.get(CONF_REQUEST_CONNECT_TIMEOUT, DEFAULT_REQUEST_CONNECT_TIMEOUT))
            total_timeout = int(opts.get(CONF_REQUEST_TOTAL_TIMEOUT, DEFAULT_REQUEST_TOTAL_TIMEOUT))
            max_retries = int(opts.get(CONF_API_MAX_RETRIES, DEFAULT_API_MAX_RETRIES))
            retry_base = float(opts.get(CONF_API_RETRY_BASE, DEFAULT_API_RETRY_BASE))

            attempts = max_retries + 1
            backoff = retry_base

            for _try in range(attempts):
                try:
                    async with async_timeout.timeout(total_timeout):
                        session = async_get_clientsession(self.hass)
                        _LOGGER.debug("Request parameters: %s", params)
                        async with session.get(
                            URL,
                            params=params,
                            timeout=aiohttp.ClientTimeout(total=total_timeout, connect=connect_timeout),
                        ) as response:
                            if response.status != 200:
                                raise UpdateFailed(f"API error: {response.status}")

                            data = await response.json()
                            # Dodanie metadanych
                            data["latitude"] = self._latitude
                            data["longitude"] = self._longitude
                            data["timezone"] = self._timezone
                            data["_metadata"] = {
                                "last_update": datetime.now(timezone.utc).isoformat(),
                            }
                            return data
                except (asyncio.TimeoutError, aiohttp.ClientError) as err:
                    if _try < attempts - 1:
                        await asyncio.sleep(backoff)
                        backoff *= 2
                        continue
                    raise UpdateFailed("Timeout while connecting to Open-Meteo API") from err

        except Exception as err:
            _LOGGER.error("Update failed: %s", err, exc_info=True)
            raise UpdateFailed(f"Fetch error: {err}") from err
