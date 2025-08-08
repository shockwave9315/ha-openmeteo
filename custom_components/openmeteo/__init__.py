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
    # Inicjalizacja koordynatora
    coordinator = OpenMeteoDataUpdateCoordinator(hass, entry)
    
    # Pobierz dane po raz pierwszy
    await coordinator.async_config_entry_first_refresh()
    
    # Zapisz koordynator w danych HASS
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Załaduj platformy (weather i sensor)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Dodaj opcję aktualizacji konfiguracji
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Odładujemy wszystkie platformy
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unload_ok:
        # Usuń dane związane z tą konfiguracją
        hass.data[DOMAIN].pop(entry.entry_id, None)
        
        # Jeśli to była ostatnia konfiguracja, usuń domenę
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
        
        # Pobierz interwał z konfiguracji lub użyj domyślnego
        scan_interval_seconds = entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        
        # Upewnij się, że to int
        if not isinstance(scan_interval_seconds, int):
            scan_interval_seconds = int(scan_interval_seconds)
        
        # Konwertuj na timedelta tylko dla update_interval
        update_interval = timedelta(seconds=scan_interval_seconds)
        
        super().__init__(
            hass,
            _LOGGER,
            name="OpenMeteo",
            update_interval=update_interval,
        )
        
        # Zapisz oryginalną wartość (sekundy) jako atrybut
        self.scan_interval_seconds = scan_interval_seconds

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Open-Meteo API."""
        # Pobierz dane konfiguracyjne
        latitude = self.entry.data[CONF_LATITUDE]
        longitude = self.entry.data[CONF_LONGITUDE]
        timezone = self.entry.data.get(CONF_TIME_ZONE, "auto")
        
        # Utwórz kopie domyślnych list, aby nie modyfikować oryginalnych
        default_hourly = list(DEFAULT_HOURLY_VARIABLES)
        default_daily = list(DEFAULT_DAILY_VARIABLES)
        
        # Dodaj brakujące parametry, jeśli ich nie ma
        if "pressure_msl" not in default_hourly:
            default_hourly.append("pressure_msl")
        if "surface_pressure" not in default_hourly:
            default_hourly.append("surface_pressure")
        if "visibility" not in default_hourly:
            default_hourly.append("visibility")
        
        # Pobierz wybrane zmienne z opcji lub użyj domyślnych
        daily_vars = self.entry.options.get(
            CONF_DAILY_VARIABLES,
            self.entry.data.get(CONF_DAILY_VARIABLES, default_daily)
        )
        hourly_vars = self.entry.options.get(
            CONF_HOURLY_VARIABLES,
            self.entry.data.get(CONF_HOURLY_VARIABLES, default_hourly)
        )

        # Parametry zapytania
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "timezone": timezone,
            "current_weather": "true",
            "hourly": ",".join(sorted(set(hourly_vars))),
            "daily": ",".join(sorted(set(daily_vars))),
            "temperature_unit": "celsius",
            "windspeed_unit": "kmh",
            "precipitation_unit": "mm",
        }

        # Inicjalizacja sesji HTTP
        session = async_get_clientsession(self.hass)
        
        try:
            async with async_timeout.timeout(10):
                async with session.get(URL, params=params) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        _LOGGER.error(
                            "Error %s from Open-Meteo API: %s", 
                            response.status,
                            error_text[:200]  # Ogranicz długość logowanego błędu
                        )
                        raise UpdateFailed(f"Error {response.status} from Open-Meteo API")
                    
                    data = await response.json()
                    
                    # Dodaj dodatkowe informacje o lokalizacji
                    data["location"] = {
                        "latitude": latitude,
                        "longitude": longitude,
                        "timezone": timezone,
                    }

                    # Przycięcie danych godzinowych do bieżącej godziny
                    if "hourly" in data and "time" in data["hourly"]:
                        from datetime import datetime, timezone as tz
                        from zoneinfo import ZoneInfo

from datetime import datetime, timezone as tz

def _om_parse_time_local_safe(time_str, user_tz):
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

                        
                        try:
                            # Pobierz bieżący czas w strefie czasowej użytkownika
                            user_tz = ZoneInfo(timezone if timezone != "auto" else "UTC")
                            now = datetime.now(tz.utc).astimezone(user_tz)
                            
                            # Znajdź indeks pierwszej godziny w przyszłości
                            times = data["hourly"]["time"]
                            future_indices = []
                            
                            for i, time_str in enumerate(times):
                                try:
                                    # Konwersja czasu z odpowiednią strefą czasową
                                    dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                                    dt = dt.replace(tzinfo=tz.utc).astimezone(user_tz)
                                    if dt >= now:
                                        future_indices.append(i)
                                except (ValueError, TypeError) as e:
                                    _LOGGER.debug("Error parsing time %s: %s", time_str, e)
                                    continue
                            
                            if future_indices:
                                first_future = future_indices[0]
                                # Przytnij dane godzinowe
                                for key in list(data["hourly"].keys()):
                                    if isinstance(data["hourly"][key], list) and len(data["hourly"][key]) == len(times):
                                        data["hourly"][key] = data["hourly"][key][first_future:]
                            
                        except Exception as e:
                            _LOGGER.error("Error processing hourly data: %s", str(e), exc_info=True)
                            # Kontynuuj bez przycinania w przypadku błędu
                    
                    return data
                    
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout while connecting to Open-Meteo API")
            raise UpdateFailed("Timeout while connecting to Open-Meteo API")
        except aiohttp.ClientError as err:
            _LOGGER.error("Error connecting to Open-Meteo API: %s", err)
            raise UpdateFailed(f"Error connecting to Open-Meteo API: {err}")
        except Exception as err:
            _LOGGER.error("Unexpected error from Open-Meteo API: %s", err, exc_info=True)
            raise UpdateFailed(f"Unexpected error from Open-Meteo API: {err}")