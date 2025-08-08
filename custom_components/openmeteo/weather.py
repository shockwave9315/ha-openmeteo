"""Support for Open-Meteo weather service with device tracking."""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from homeassistant.components.weather import (
    ATTR_FORECAST_CONDITION,
    ATTR_FORECAST_PRECIPITATION,
    ATTR_FORECAST_PRECIPITATION_PROBABILITY,
    ATTR_FORECAST_TEMP,
    ATTR_FORECAST_TEMP_LOW,
    ATTR_FORECAST_TIME,
    ATTR_FORECAST_WIND_BEARING,
    ATTR_FORECAST_WIND_SPEED,
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfLength,
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from . import OpenMeteoDataUpdateCoordinator, OpenMeteoInstance
from .const import CONDITION_MAP, DOMAIN, SIGNAL_UPDATE_ENTITIES, HOURLY_FORECAST_HORIZON

_LOGGER = logging.getLogger(__name__)

def stable_hash(input_str: str, length: int = 6) -> str:
    """Return a short, stable hash of a string."""
    return hashlib.sha1(input_str.encode()).hexdigest()[:length]

async def async_setup_entry(hass, config_entry, async_add_entities) -> None:
    """Create weather entities for main instance and per-device instances."""
    entry_data = hass.data.get(DOMAIN, {}).get(config_entry.entry_id, {})
    main_instance = entry_data.get("main_instance")
    device_instances = entry_data.get("device_instances", {}) or {}

    entities = []
    if main_instance is not None:
        entities.append(OpenMeteoWeather(main_instance.coordinator, config_entry))
    for device_id, instance in device_instances.items():
        try:
            entities.append(OpenMeteoWeather(instance.coordinator, config_entry, device_id=device_id))
        except Exception as err:
            _LOGGER.error("Cannot create device weather for %s: %s", device_id, err)

    if entities:
        async_add_entities(entities, True)
    else:
        _LOGGER.warning("No weather entities created (no main_instance and no devices).")

# Register the update listener (only for main instance!)
    if not device_id:
        config_entry.async_on_unload(
            async_dispatcher_connect(
                hass,
                SIGNAL_UPDATE_ENTITIES,
                _async_update_entities,
            )
        )
        
        # Initial update only if no device_id
        _async_update_entities(entry_id)

class OpenMeteoWeather(WeatherEntity):
    """Implementation of an Open-Meteo weather entity with device tracking support."""

    _attr_attribution = "Weather data provided by Open-Meteo"
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_precipitation_unit = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_native_visibility_unit = UnitOfLength.KILOMETERS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_DAILY | WeatherEntityFeature.FORECAST_HOURLY
    )

    def __init__(
        self, 
        coordinator: OpenMeteoDataUpdateCoordinator, 
        config_entry: ConfigEntry, 
        device_id: str | None = None,
        friendly_name: str | None = None
    ) -> None:
        """Initialize the Open-Meteo weather.
        
        Args:
            coordinator: Coordinator for weather data updates
            config_entry: Configuration entry for this integration
            device_id: Optional device ID if this is a device-specific instance
            
        Raises:
            ValueError: If required parameters are missing or invalid
        """
        try:
            # Validate input parameters
            if not coordinator or not config_entry:
                error_msg = f"Missing required parameters: coordinator={coordinator is not None}, config_entry={config_entry is not None}"
                _LOGGER.error(error_msg)
                raise ValueError(error_msg)
                
            if not hasattr(coordinator, 'hass') or not isinstance(coordinator.hass, HomeAssistant):
                _LOGGER.error("Invalid or missing HomeAssistant instance in coordinator")
                raise ValueError("Invalid coordinator: missing or invalid HomeAssistant instance")
                
            self.coordinator = coordinator
            self._device_id = device_id
            self._config_entry = config_entry
            self.hass = coordinator.hass  # Ensure hass is set early for logging
            self.entity_id = None
            
            # Initialize required attributes to avoid attribute errors
            self._attr_name = None
            self._attr_unique_id = None
            self._attr_entity_registry_visible_default = True
            self._attr_device_info = None
            
            # Set up unique ID and name based on whether this is a device instance or not
            if device_id:
                # This is a device instance - include both entry_id and device_id in the unique_id
                if not friendly_name and hasattr(config_entry, 'data') and config_entry.data:
                    friendly_name = config_entry.data.get("friendly_name")
                    if not friendly_name:
                        _LOGGER.debug("No friendly_name found in config entry for device %s", device_id)
                
                if friendly_name:
                    self._attr_name = f"{friendly_name} Weather"
                    _LOGGER.debug("Using friendly name for device %s: %s", device_id, friendly_name)
                else:
                    # Fallback to a generated name if friendly_name is not available
                    device_name = device_id.split('.')[-1].replace('_', ' ').title()
                    self._attr_name = f"{device_name} Weather"
                    _LOGGER.debug("Using generated name for device %s: %s", device_id, self._attr_name)
                
                # Let the unique_id property handle the unique ID generation
                self._attr_entity_registry_visible_default = True
            else:
                # This is the main instance
                self._attr_name = config_entry.data.get("name", "Open-Meteo Weather")
                
                # Safely check for device instances
                device_instances = {}
                try:
                    if (DOMAIN in self.hass.data and 
                            config_entry.entry_id in self.hass.data[DOMAIN] and 
                            "device_instances" in self.hass.data[DOMAIN][config_entry.entry_id]):
                        device_instances = self.hass.data[DOMAIN][config_entry.entry_id]["device_instances"]
                except Exception as err:
                    _LOGGER.warning("Error checking for device instances: %s", str(err))
                    
                self._attr_entity_registry_visible_default = True
            
            # Device info will be handled by the device_info property
            self._attr_device_info = None
            
            # Safely get device-specific data
            try:
                self._device_entity_id = config_entry.data.get("device_entity_id")
                self._device_name = config_entry.data.get("device_name")
                self._area_overrides = config_entry.data.get("area_overrides", {})
                self._device_id = device_id
                
                # Store suggested area for device_info property
                self._suggested_area = f"Lokalizacja {device_id[-4:] if device_id else 'unkn'}"
            except Exception as dev_err:
                _LOGGER.error("Error setting up device info: %s", str(dev_err))
                # Ensure required attributes are set even if there's an error
                self._device_entity_id = None
                self._device_name = None
                self._area_overrides = {}
                self._device_id = device_id
                self._suggested_area = "Unknown Location"
                    
            _LOGGER.debug("Initialized %s weather entity", "device" if device_id else "main")
            
        except Exception as init_err:
            _LOGGER.error("Failed to initialize OpenMeteoWeather: %s", str(init_err), exc_info=True)
            raise
        
        self._attr_should_poll = False

    @property
    def unique_id(self) -> str:
        """Return unique ID combining entry ID and device ID."""
        try:
            entry_id = self._config_entry.entry_id
            if self._device_id:
                suffix = stable_hash(self._device_id)
                return f"{entry_id}-dev{suffix}-weather"
            return f"{entry_id}-main-weather"
        except Exception as e:
            _LOGGER.error("Error generating unique_id: %s", e, exc_info=True)
            return f"{getattr(self._config_entry, 'entry_id', 'error')}-fallback-weather"
            
    @property
    def device_info(self) -> Optional[DeviceInfo]:
        """Return device registry information.
        
        For device tracker entities, return a DeviceInfo object with suggested_area.
        For main instance, return None as it's managed in __init__.py
        """
        try:
            if self._device_id:
                # For device trackers, return DeviceInfo with suggested_area
                return DeviceInfo(
                    identifiers={(DOMAIN, f"{self._config_entry.entry_id}-{self._device_id}")},
                    name=self._friendly_name or f"Open-Meteo {self._device_id}",
                    manufacturer="Open-Meteo",
                    suggested_area=self._friendly_name or "Open-Meteo"
                )
            # Main instance device is managed in __init__.py
            return None
        except Exception as e:
            _LOGGER.warning("Error generating device_info: %s", e, exc_info=True)
            return None

    @property
    def available(self) -> bool:
        """Return if weather data is available."""
        try:
            # Sprawdź czy mamy koordynator
            if not hasattr(self, 'coordinator') or not self.coordinator:
                _LOGGER.debug("Weather entity %s: Brak koordynatora", self.entity_id)
                return False
                
            # Sprawdź czy to instancja urządzenia, która została usunięta
            if self._device_id and hasattr(self, 'hass') and hasattr(self.hass, 'data'):
                try:
                    entry_id = getattr(self, '_config_entry', None)
                    entry_id = getattr(entry_id, 'entry_id', None) if entry_id else None
                    
                    if (entry_id and 
                        DOMAIN in self.hass.data and 
                        isinstance(self.hass.data[DOMAIN], dict) and
                        entry_id in self.hass.data[DOMAIN] and 
                        isinstance(self.hass.data[DOMAIN][entry_id], dict) and
                        self._device_id not in self.hass.data[DOMAIN][entry_id].get("device_instances", {})):
                        _LOGGER.debug("Weather entity %s: Instancja urządzenia %s została usunięta", 
                                    self.entity_id, self._device_id)
                        return False
                except Exception as e:
                    _LOGGER.warning("Błąd podczas sprawdzania dostępności encji %s: %s", 
                                 self.entity_id, str(e), exc_info=True)
            
            # Sprawdź czy mamy aktualne dane
            if not hasattr(self.coordinator, 'last_update_success'):
                _LOGGER.debug("Weather entity %s: Brak atrybutu last_update_success w koordynatorze", 
                            self.entity_id)
                return False
                
            return bool(self.coordinator.last_update_success)
            
        except Exception as e:
            _LOGGER.error("Krytyczny błąd w metodzie available dla encji %s: %s", 
                         getattr(self, 'entity_id', 'nieznana'), str(e), exc_info=True)
            return False

    @property
    def condition(self) -> str | None:
        """
        Return the current weather condition.
        
        Returns:
            str | None: Warunek pogodowy zrozumiały dla interfejsu Home Assistant lub None w przypadku błędu
            
        Note:
            Metoda wykorzystuje dane z API Open-Meteo i mapuje je na warunki zrozumiałe dla Home Assistant.
            W przypadku braku danych lub błędów zwraca None i loguje odpowiednie komunikaty.
        """
        try:
            entity_id = getattr(self, 'entity_id', 'nieznana')
            
            # Sprawdź dostępność i poprawność danych
            if not self.available:
                _LOGGER.debug("Weather entity %s: Encja niedostępna w metodzie condition", 
                            entity_id)
                return None
                
            # Sprawdź czy koordynator i jego dane istnieją
            if not hasattr(self, 'coordinator') or not hasattr(self.coordinator, 'data'):
                _LOGGER.debug("Weather entity %s: Brak danych koordynatora w metodzie condition", 
                            entity_id)
                return None
                
            # Sprawdź czy dane koordynatora mają oczekiwany format
            if not isinstance(self.coordinator.data, dict):
                _LOGGER.warning("Weather entity %s: Nieprawidłowy format danych koordynatora: %s", 
                             entity_id, type(self.coordinator.data).__name__)
                return None
                
            if "current_weather" not in self.coordinator.data:
                _LOGGER.debug("Weather entity %s: Brak sekcji 'current_weather' w danych koordynatora", 
                            entity_id)
                return None
            
            # Pobierz dane o aktualnej pogodzie
            current_weather = self.coordinator.data.get("current_weather", {})
            if not isinstance(current_weather, dict):
                _LOGGER.warning("Weather entity %s: Nieprawidłowy format danych current_weather: %s", 
                             entity_id, type(current_weather).__name__)
                return None
            
            # Pobierz informację czy jest dzień (domyślnie zakładamy, że jest dzień)
            try:
                is_day = bool(int(current_weather.get("is_day", 1)))
            except (ValueError, TypeError) as e:
                _LOGGER.warning("Weather entity %s: Nieprawidłowa wartość is_day: %s. Używam domyślnej wartości True", 
                             entity_id, str(current_weather.get("is_day")))
                is_day = True
            
            # Pobierz kod pogodowy
            weather_code = current_weather.get("weathercode")
            
            if weather_code is None:
                _LOGGER.debug("Weather entity %s: Brak kodu pogodowego w danych. Dostępne klucze: %s", 
                            entity_id, ", ".join(map(str, current_weather.keys())))
                return None
                
            # Pobierz warunki pogodowe z uwzględnieniem pory dnia
            condition = self._get_condition(weather_code, is_day)
            
            _LOGGER.debug("Weather entity %s: Dla kodu %d i is_day=%s zwrócono warunek: %s", 
                         entity_id, weather_code, is_day, condition)
            
            return condition
            
        except Exception as e:
            _LOGGER.error("Krytyczny błąd w metodzie condition dla encji %s: %s\nSzczegóły: %s", 
                         getattr(self, 'entity_id', 'nieznana'), 
                         str(e), 
                         f"data={getattr(self, 'coordinator', {}).__dict__ if hasattr(self, 'coordinator') else 'brak koordynatora'}",
                         exc_info=True)
            return None

    @property
    def native_temperature(self) -> float | None:
        """
        Return the current temperature in the native unit of measurement.
        
        Returns:
            float | None: Temperatura w stopniach Celsjusza lub None w przypadku błędu
            
        Note:
            Metoda pobiera dane o temperaturze z API Open-Meteo i konwertuje je na float.
            W przypadku braku danych lub błędów zwraca None i loguje odpowiednie komunikaty.
        """
        try:
            entity_id = getattr(self, 'entity_id', 'nieznana')
            
            # Sprawdź dostępność i poprawność danych
            if not self.available:
                _LOGGER.debug("Weather entity %s: Encja niedostępna w metodzie native_temperature", 
                            entity_id)
                return None
                
            # Sprawdź czy koordynator i jego dane istnieją
            if not hasattr(self, 'coordinator') or not hasattr(self.coordinator, 'data'):
                _LOGGER.debug("Weather entity %s: Brak danych koordynatora w metodzie native_temperature", 
                            entity_id)
                return None
                
            # Sprawdź czy dane koordynatora mają oczekiwany format
            if not isinstance(self.coordinator.data, dict):
                _LOGGER.warning("Weather entity %s: Nieprawidłowy format danych koordynatora w native_temperature: %s", 
                             entity_id, type(self.coordinator.data).__name__)
                return None
                
            if "current_weather" not in self.coordinator.data:
                _LOGGER.debug("Weather entity %s: Brak sekcji 'current_weather' w danych koordynatora", 
                            entity_id)
                return None
            
            # Pobierz dane o aktualnej pogodzie
            current_weather = self.coordinator.data.get("current_weather", {})
            if not isinstance(current_weather, dict):
                _LOGGER.warning("Weather entity %s: Nieprawidłowy format danych current_weather w native_temperature: %s", 
                             entity_id, type(current_weather).__name__)
                return None
                
            # Pobierz temperaturę
            temp = current_weather.get("temperature")
            if temp is None:
                _LOGGER.debug("Weather entity %s: Brak danych o temperaturze. Dostępne klucze: %s", 
                            entity_id, ", ".join(map(str, current_weather.keys())))
                return None
                
            # Spróbuj przekonwertować na float
            try:
                temp_float = float(temp)
                _LOGGER.debug("Weather entity %s: Pobrano temperaturę: %.1f°C", 
                             entity_id, temp_float)
                return temp_float
                
            except (TypeError, ValueError) as e:
                _LOGGER.warning("Weather entity %s: Nie można przekonwertować temperatury '%s' na float: %s", 
                             entity_id, str(temp), str(e))
                return None
                
        except Exception as e:
            _LOGGER.error("Krytyczny błąd w metodzie native_temperature dla encji %s: %s\nSzczegóły: %s", 
                         getattr(self, 'entity_id', 'nieznana'), 
                         str(e), 
                         f"data={getattr(self, 'coordinator', {}).__dict__ if hasattr(self, 'coordinator') else 'brak koordynatora'}",
                         exc_info=True)
            return None

    @property
    def native_pressure(self) -> float | None:
        """
        Return the current atmospheric pressure in the native unit of measurement.
        
        Returns:
            float | None: Ciśnienie atmosferyczne w hektopaskalach (hPa) lub None w przypadku błędu
            
        Note:
            Metoda pobiera dane o ciśnieniu z API Open-Meteo i konwertuje je na float.
            W przypadku braku danych lub błędów zwraca None i loguje odpowiednie komunikaty.
            Wartość jest pobierana z klucza 'surface_pressure' w danych bieżącej pogody.
        """
        try:
            entity_id = getattr(self, 'entity_id', 'nieznana')
            
            # Sprawdź dostępność i poprawność danych
            if not self.available:
                _LOGGER.debug("Weather entity %s: Encja niedostępna w metodzie native_pressure", 
                            entity_id)
                return None
                
            # Sprawdź czy koordynator i jego dane istnieją
            if not hasattr(self, 'coordinator') or not hasattr(self.coordinator, 'data'):
                _LOGGER.debug("Weather entity %s: Brak danych koordynatora w metodzie native_pressure", 
                            entity_id)
                return None
                
            # Sprawdź czy dane koordynatora mają oczekiwany format
            if not isinstance(self.coordinator.data, dict):
                _LOGGER.warning("Weather entity %s: Nieprawidłowy format danych koordynatora w native_pressure: %s", 
                             entity_id, type(self.coordinator.data).__name__)
                return None
                
            if "current_weather" not in self.coordinator.data:
                _LOGGER.debug("Weather entity %s: Brak sekcji 'current_weather' w danych koordynatora", 
                            entity_id)
                return None
            
            # Pobierz dane o aktualnej pogodzie
            current_weather = self.coordinator.data.get("current_weather", {})
            if not isinstance(current_weather, dict):
                _LOGGER.warning("Weather entity %s: Nieprawidłowy format danych current_weather w native_pressure: %s", 
                             entity_id, type(current_weather).__name__)
                return None
                
            # Pobierz ciśnienie z powierzchni (surface_pressure) lub ciśnienie na poziomie morza (pressure_msl)
            pressure = current_weather.get("surface_pressure")
            
            # Jeśli nie ma surface_pressure, spróbuj pobrać pressure_msl
            if pressure is None:
                pressure = current_weather.get("pressure_msl")
                if pressure is not None:
                    _LOGGER.debug("Weather entity %s: Używam pressure_msl zamiast surface_pressure", entity_id)
            
            if pressure is None:
                _LOGGER.debug("Weather entity %s: Brak danych o ciśnieniu. Dostępne klucze: %s", 
                            entity_id, ", ".join(map(str, current_weather.keys())))
                return None
                
            # Spróbuj przekonwertować na float
            try:
                pressure_float = float(pressure)
                _LOGGER.debug("Weather entity %s: Pobrano ciśnienie: %.1f hPa", 
                             entity_id, pressure_float)
                return pressure_float
                
            except (TypeError, ValueError) as e:
                _LOGGER.warning("Weather entity %s: Nie można przekonwertować ciśnienia '%s' na float: %s", 
                             entity_id, str(pressure), str(e))
                return None
                
        except Exception as e:
            _LOGGER.error("Krytyczny błąd w metodzie native_pressure dla encji %s: %s\nSzczegóły: %s", 
                         getattr(self, 'entity_id', 'nieznana'), 
                         str(e), 
                         f"data={getattr(self, 'coordinator', {}).__dict__ if hasattr(self, 'coordinator') else 'brak koordynatora'}",
                         exc_info=True)
            return None

    @property
    def humidity(self) -> float | None:
        """
        Return the current relative humidity.
        
        Returns:
            float | None: Wilgotność względna w procentach (0-100) lub None w przypadku błędu
            
        Note:
            Metoda pobiera dane o wilgotności z sekcji 'hourly' danych pogodowych.
            W przypadku braku danych lub błędów zwraca None i loguje odpowiednie komunikaty.
            Wartość jest pobierana z klucza 'relativehumidity_2m' w danych godzinnych.
        """
        try:
            entity_id = getattr(self, 'entity_id', 'nieznana')
            
            # Sprawdź dostępność i poprawność danych
            if not self.available:
                _LOGGER.debug("Weather entity %s: Encja niedostępna w metodzie humidity", 
                            entity_id)
                return None
                
            # Sprawdź czy koordynator i jego dane istnieją
            if not hasattr(self, 'coordinator') or not hasattr(self.coordinator, 'data'):
                _LOGGER.debug("Weather entity %s: Brak danych koordynatora w metodzie humidity", 
                            entity_id)
                return None
                
            # Sprawdź czy dane koordynatora mają oczekiwany format
            if not isinstance(self.coordinator.data, dict):
                _LOGGER.warning("Weather entity %s: Nieprawidłowy format danych koordynatora w humidity: %s", 
                             entity_id, type(self.coordinator.data).__name__)
                return None
                
            if "hourly" not in self.coordinator.data:
                _LOGGER.debug("Weather entity %s: Brak sekcji 'hourly' w danych koordynatora", 
                            entity_id)
                return None
            
            # Pobierz dane godzinne
            hourly_data = self.coordinator.data.get("hourly", {})
            if not isinstance(hourly_data, dict):
                _LOGGER.warning("Weather entity %s: Nieprawidłowy format danych godzinnych w humidity: %s", 
                             entity_id, type(hourly_data).__name__)
                return None
                
            # Pobierz dane o wilgotności
            humidities = hourly_data.get("relativehumidity_2m", [])
            
            # Sprawdź czy mamy jakieś dane o wilgotności
            if not humidities or not isinstance(humidities, (list, tuple)):
                _LOGGER.debug("Weather entity %s: Brak danych o wilgotności w sekcji hourly.relativehumidity_2m. Dostępne klucze: %s", 
                            entity_id, ", ".join(map(str, hourly_data.keys())) if _LOGGER.isEnabledFor(logging.DEBUG) else "hidden")
                return None
                
            # Sprawdź czy lista wilgotności nie jest pusta
            if len(humidities) == 0:
                _LOGGER.debug("Weather entity %s: Pusta lista wilgotności w hourly.relativehumidity_2m", 
                            entity_id)
                return None
                
            # Pobierz pierwszą dostępną wartość wilgotności (najnowszą)
            humidity = humidities[0] if len(humidities) > 0 else None
            
            if humidity is None:
                _LOGGER.debug("Weather entity %s: Brak wartości wilgotności (None) w pierwszym elemencie listy", 
                            entity_id)
                return None
                
            # Spróbuj przekonwertować na float
            try:
                humidity_float = float(humidity)
                
                # Sprawdź czy wilgotność mieści się w rozsądnym zakresie (0-100%)
                if not (0 <= humidity_float <= 100):
                    _LOGGER.warning("Weather entity %s: Wilgotność %.1f%% jest poza zakresem 0-100%%. Przycinam do najbliższej wartości granicznej.", 
                                 entity_id, humidity_float)
                    humidity_float = max(0.0, min(100.0, humidity_float))
                
                _LOGGER.debug("Weather entity %s: Pobrano wilgotność: %.1f%%", 
                             entity_id, humidity_float)
                return humidity_float
                
            except (TypeError, ValueError) as e:
                _LOGGER.warning("Weather entity %s: Nie można przekonwertować wartości wilgotności '%s' na float: %s", 
                             entity_id, str(humidity), str(e))
                return None
                
        except Exception as e:
            _LOGGER.error("Krytyczny błąd w metodzie humidity dla encji %s: %s\nSzczegóły: %s", 
                         getattr(self, 'entity_id', 'nieznana'), 
                         str(e), 
                         f"data={getattr(self, 'coordinator', {}).__dict__ if hasattr(self, 'coordinator') else 'brak koordynatora'}",
                         exc_info=True)
            return None

    @property
    def native_wind_speed(self) -> float | None:
        """
        Return the current wind speed in the native unit of measurement (km/h).
        
        Returns:
            float | None: Prędkość wiatru w km/h lub None w przypadku błędu
            
        Note:
            Metoda pobiera dane o prędkości wiatru z sekcji 'current_weather' danych pogodowych.
            W przypadku braku danych lub błędów zwraca None i loguje odpowiednie komunikaty.
            Wartość jest pobierana z klucza 'windspeed' w danych bieżącej pogody.
        """
        entity_id = getattr(self, 'entity_id', 'nieznana')
        
        try:
            # Sprawdź dostępność i poprawność danych
            if not self.available:
                _LOGGER.debug("Weather entity %s: Encja niedostępna w metodzie native_wind_speed", 
                            entity_id)
                return None
                
            # Sprawdź czy koordynator i jego dane istnieją
            if not hasattr(self, 'coordinator') or not hasattr(self.coordinator, 'data'):
                _LOGGER.warning("Weather entity %s: Brak danych koordynatora w metodzie native_wind_speed", 
                             entity_id)
                return None
                
            # Sprawdź czy dane koordynatora mają oczekiwany format
            if not isinstance(self.coordinator.data, dict):
                _LOGGER.warning("Weather entity %s: Nieprawidłowy format danych koordynatora w native_wind_speed: %s", 
                             entity_id, type(self.coordinator.data).__name__)
                return None
                
            if not self.coordinator.data or "current_weather" not in self.coordinator.data:
                _LOGGER.debug("Weather entity %s: Brak sekcji 'current_weather' w danych koordynatora", 
                            entity_id)
                return None
            
            # Pobierz dane o aktualnej pogodzie
            current_weather = self.coordinator.data.get("current_weather", {})
            if not current_weather or not isinstance(current_weather, dict):
                _LOGGER.debug("Weather entity %s: Brak lub nieprawidłowy format danych current_weather w native_wind_speed: %s", 
                           entity_id, type(current_weather).__name__)
                return None
                
            # Pobierz prędkość wiatru (klucz 'windspeed' wg dokumentacji Open-Meteo)
            wind_speed = current_weather.get("windspeed")
            
            # Sprawdź czy mamy jakąkolwiek wartość prędkości wiatru
            if wind_speed is None:
                _LOGGER.debug("Weather entity %s: Brak danych o prędkości wiatru. Dostępne klucze: %s", 
                            entity_id, ", ".join(map(str, current_weather.keys())))
                return None
                
            # Spróbuj przekonwertować na float
            try:
                wind_speed_float = float(wind_speed)
                
                # Sprawdź czy prędkość wiatru jest nieujemna i w rozsądnym zakresie (0-300 km/h)
                if wind_speed_float < 0:
                    _LOGGER.warning("Weather entity %s: Ujemna wartość prędkości wiatru: %.1f km/h. Ustawiam na 0.", 
                                 entity_id, wind_speed_float)
                    wind_speed_float = 0.0
                elif wind_speed_float > 300:  # Prędkość większa niż 300 km/h jest mało prawdopodobna
                    _LOGGER.warning("Weather entity %s: Nieprawdopodobnie wysoka wartość prędkości wiatru: %.1f km/h. Przycinam do 300 km/h.", 
                                 entity_id, wind_speed_float)
                    wind_speed_float = 300.0
                
                _LOGGER.debug("Weather entity %s: Pobrano prędkość wiatru: %.1f km/h", 
                             entity_id, wind_speed_float)
                return wind_speed_float
                
            except (TypeError, ValueError) as e:
                _LOGGER.warning("Weather entity %s: Nie można przekonwertować wartości prędkości wiatru '%s' na float: %s", 
                             entity_id, str(wind_speed), str(e))
                return None
                
        except Exception as e:
            _LOGGER.error("Krytyczny błąd w metodzie native_wind_speed dla encji %s: %s\nSzczegóły: %s\nTraceback: %s", 
                         entity_id, 
                         str(e), 
                         f"coordinator_present={hasattr(self, 'coordinator')}",
                         exc_info=True)
            return None

    @property
    def wind_bearing(self) -> float | None:
        """
        Return the current wind bearing in degrees.
        
        Returns:
            float | None: Kierunek wiatru w stopniach (0-360) lub None w przypadku błędu
            
        Note:
            Metoda pobiera dane o kierunku wiatru z sekcji 'current_weather' danych pogodowych.
            Wartość jest normalizowana do zakresu 0-360 stopni. W przypadku braku danych lub błędów
            zwraca None i loguje odpowiednie komunikaty. Wartość jest pobierana z klucza 'winddirection'.
        """
        entity_id = getattr(self, 'entity_id', 'nieznana')
        
        try:
            # Sprawdź dostępność i poprawność danych
            if not self.available:
                _LOGGER.debug("Weather entity %s: Encja niedostępna w metodzie wind_bearing", 
                            entity_id)
                return None
                
            # Sprawdź czy koordynator i jego dane istnieją
            if not hasattr(self, 'coordinator') or not hasattr(self.coordinator, 'data'):
                _LOGGER.warning("Weather entity %s: Brak danych koordynatora w metodzie wind_bearing", 
                             entity_id)
                return None
                
            # Sprawdź czy dane koordynatora mają oczekiwany format
            if not isinstance(self.coordinator.data, dict):
                _LOGGER.warning("Weather entity %s: Nieprawidłowy format danych koordynatora w wind_bearing: %s", 
                             entity_id, type(self.coordinator.data).__name__)
                return None
                
            if not self.coordinator.data or "current_weather" not in self.coordinator.data:
                _LOGGER.debug("Weather entity %s: Brak sekcji 'current_weather' w danych koordynatora", 
                            entity_id)
                return None
            
            # Pobierz dane o aktualnej pogodzie
            current_weather = self.coordinator.data.get("current_weather", {})
            if not current_weather or not isinstance(current_weather, dict):
                _LOGGER.debug("Weather entity %s: Brak lub nieprawidłowy format danych current_weather w wind_bearing: %s", 
                           entity_id, type(current_weather).__name__)
                return None
                
            # Pobierz kierunek wiatru (klucz 'winddirection' wg dokumentacji Open-Meteo)
            wind_direction = current_weather.get("winddirection")
            
            # Sprawdź czy mamy jakąkolwiek wartość kierunku wiatru
            if wind_direction is None:
                _LOGGER.debug("Weather entity %s: Brak danych o kierunku wiatru. Dostępne klucze: %s", 
                            entity_id, ", ".join(map(str, current_weather.keys())))
                return None
                
            # Spróbuj przekonwertować na float i znormalizować do zakresu 0-360 stopni
            try:
                wind_bearing = float(wind_direction)
                
                # Normalizacja do zakresu 0-360 stopni
                wind_bearing = wind_bearing % 360.0
                
                # Sprawdź czy wartość jest w rozsądnym zakresie (0-360°)
                if not (0 <= wind_bearing <= 360):
                    _LOGGER.warning("Weather entity %s: Nieprawidłowa wartość kierunku wiatru: %.1f°. Normalizuję do zakresu 0-360°.", 
                                 entity_id, wind_bearing)
                    wind_bearing = wind_bearing % 360.0
                
                _LOGGER.debug("Weather entity %s: Pobrano kierunek wiatru: %.1f°", 
                             entity_id, wind_bearing)
                return wind_bearing
                
            except (TypeError, ValueError) as e:
                _LOGGER.warning("Weather entity %s: Nie można przekonwertować wartości kierunku wiatru '%s' na float: %s", 
                             entity_id, str(wind_direction), str(e))
                return None
                
        except Exception as e:
            _LOGGER.error("Krytyczny błąd w metodzie wind_bearing dla encji %s: %s\nSzczegóły: %s\nTraceback: %s", 
                         entity_id, 
                         str(e), 
                         f"coordinator_present={hasattr(self, 'coordinator')}",
                         exc_info=True)
            return None

    @property
    def native_visibility(self) -> float | None:
        """
        Return the current visibility in the native unit of measurement (kilometers).
        
        Returns:
            float | None: Widoczność w kilometrach lub None w przypadku błędu
            
        Note:
            Metoda pobiera dane o widoczności z sekcji 'hourly' danych pogodowych.
            W przypadku braku danych lub błędów zwraca None i loguje odpowiednie komunikaty.
            Wartość jest pobierana z klucza 'visibility' w danych godzinnych.
        """
        entity_id = getattr(self, 'entity_id', 'nieznana')
        
        try:
            # Sprawdź dostępność i poprawność danych
            if not self.available:
                _LOGGER.debug("Weather entity %s: Encja niedostępna", entity_id)
                return None
                
            # Sprawdź czy koordynator i jego dane istnieją
            if not hasattr(self, 'coordinator') or not hasattr(self.coordinator, 'data'):
                _LOGGER.warning("Weather entity %s: Brak danych koordynatora", entity_id)
                return None
                
            coordinator_data = self.coordinator.data
            if not isinstance(coordinator_data, dict):
                _LOGGER.warning("Weather entity %s: Nieprawidłowy format danych koordynatora: %s", 
                             entity_id, type(coordinator_data).__name__)
                return None
                
            hourly_data = coordinator_data.get("hourly")
            if not hourly_data or not isinstance(hourly_data, dict):
                _LOGGER.debug("Weather entity %s: Brak danych godzinnych", entity_id)
                return None
                
            visibility_data = hourly_data.get("visibility")
            if not isinstance(visibility_data, list) or not visibility_data:
                _LOGGER.debug("Weather entity %s: Brak danych o widoczności. Dostępne klucze: %s", 
                            entity_id, list(hourly_data.keys()))
                return None
                
            # Pobierz pierwszą dostępną wartość widoczności
            visibility = visibility_data[0] if visibility_data else None
            if visibility is None:
                _LOGGER.debug("Weather entity %s: Brak wartości widoczności", entity_id)
                return None
                
            try:
                # Spróbuj przekonwertować na float i zweryfikować zakres
                visibility_km = float(visibility)
                
                if visibility_km < 0:
                    _LOGGER.warning("Weather entity %s: Ujemna wartość widoczności: %.1f km", 
                                 entity_id, visibility_km)
                    return 0.0
                    
                if visibility_km > 50:  # Ogranicz do realistycznej wartości
                    _LOGGER.debug("Weather entity %s: Wysoka wartość widoczności: %.1f km", 
                               entity_id, visibility_km)
                    return 50.0
                    
                _LOGGER.debug("Weather entity %s: Pobrano widoczność: %.1f km", 
                             entity_id, visibility_km)
                return visibility_km
                
            except (TypeError, ValueError) as e:
                _LOGGER.warning("Weather entity %s: Nieprawidłowa wartość widoczności '%s': %s", 
                             entity_id, str(visibility), str(e))
                return None
                
            except (TypeError, ValueError) as e:
                _LOGGER.warning("Weather entity %s: Nie można przekonwertować wartości widoczności '%s' na float: %s", 
                             entity_id, str(visibility), str(e))
                return None
                
        except Exception as e:
            _LOGGER.error("Krytyczny błąd w metodzie native_visibility dla encji %s: %s\nSzczegóły: %s\nTraceback: %s", 
                         entity_id, 
                         str(e), 
                         f"coordinator_present={hasattr(self, 'coordinator')}",
                         exc_info=True)
            return None

    @property
    def forecast_daily(self) -> list[dict[str, Any]]:
        """
        Return the daily forecast in the format required by the UI.
        
        Returns:
            list[dict[str, Any]]: Lista prognoz dziennych w formacie zgodnym z wymaganiami interfejsu użytkownika
            
        Note:
            Metoda przetwarza dane prognozy dziennej z API Open-Meteo i konwertuje je do formatu
            wymaganego przez interfejs użytkownika Home Assistant. W przypadku braku danych lub błędów
            zwraca pustą listę i loguje odpowiednie komunikaty.
        """
        entity_id = getattr(self, 'entity_id', 'nieznana')
        
        try:
            # Sprawdź dostępność i poprawność danych
            if not self.available:
                _LOGGER.debug("Weather entity %s: Encja niedostępna w metodzie forecast_daily", 
                            entity_id)
                return []
                
            # Sprawdź czy koordynator i jego dane istnieją
            if not hasattr(self, 'coordinator') or not hasattr(self.coordinator, 'data'):
                _LOGGER.warning("Weather entity %s: Brak danych koordynatora w metodzie forecast_daily", 
                             entity_id)
                return []
                
            # Sprawdź czy dane koordynatora mają oczekiwany format
            if not isinstance(self.coordinator.data, dict):
                _LOGGER.warning("Weather entity %s: Nieprawidłowy format danych koordynatora w forecast_daily: %s", 
                             entity_id, type(self.coordinator.data).__name__)
                return []
                
            if not self.coordinator.data or "daily" not in self.coordinator.data:
                _LOGGER.debug("Weather entity %s: Brak sekcji 'daily' w danych koordynatora", 
                            entity_id)
                return []
            
            # Pobierz dane o pogodzie dziennej
            daily = self.coordinator.data.get("daily", {})
            if not daily or not isinstance(daily, dict):
                _LOGGER.debug("Weather entity %s: Brak lub nieprawidłowy format danych dziennych w forecast_daily: %s", 
                           entity_id, type(daily).__name__)
                return []
            
            # Pobierz listę czasów dla prognozy dziennej
            time_entries = daily.get("time", [])
            if not time_entries or not isinstance(time_entries, list):
                _LOGGER.debug("Weather entity %s: Brak danych o czasie w prognozie dziennej", 
                            getattr(self, 'entity_id', 'nieznana'))
                return []
            
            forecast_data = []
            max_days = min(7, len(time_entries))  # Maksymalnie 7 dni
            
            for i in range(max_days):
                try:
                    time_entry = time_entries[i]
                    if not isinstance(time_entry, str):
                        _LOGGER.debug("Weather entity %s: Nieprawidłowy format czasu w prognozie dziennej, dzień %d", 
                                    getattr(self, 'entity_id', 'nieznana'), i)
                        continue
                    
                    # Przygotuj dane prognozy z domyślnymi wartościami
                    forecast = {
                        ATTR_FORECAST_TIME: dt_util.parse_datetime(f"{time_entry}T12:00:00"),
                        ATTR_FORECAST_CONDITION: None,
                        ATTR_FORECAST_TEMP: None,
                        ATTR_FORECAST_TEMP_LOW: None,
                        ATTR_FORECAST_PRECIPITATION: 0.0
                    }
                    
                    # Pobierz kod pogodowy z obsługą błędów
                    weather_codes = daily.get("weathercode", [])
                    if isinstance(weather_codes, list) and i < len(weather_codes):
                        weather_code = weather_codes[i]
                        forecast[ATTR_FORECAST_CONDITION] = self._get_condition(weather_code, is_day=True)
                    
                    # Pobierz maksymalną temperaturę
                    temp_max = daily.get("temperature_2m_max", [])
                    if isinstance(temp_max, list) and i < len(temp_max) and temp_max[i] is not None:
                        forecast[ATTR_FORECAST_TEMP] = float(temp_max[i])
                    
                    # Pobierz minimalną temperaturę
                    temp_min = daily.get("temperature_2m_min", [])
                    if isinstance(temp_min, list) and i < len(temp_min) and temp_min[i] is not None:
                        forecast[ATTR_FORECAST_TEMP_LOW] = float(temp_min[i])
                    
                    # Pobierz sumę opadów
                    precipitation = daily.get("precipitation_sum", [])
                    if isinstance(precipitation, list) and i < len(precipitation) and precipitation[i] is not None:
                        try:
                            forecast[ATTR_FORECAST_PRECIPITATION] = float(precipitation[i])
                        except (TypeError, ValueError):
                            forecast[ATTR_FORECAST_PRECIPITATION] = 0.0
                    
                    # Pobierz prędkość i kierunek wiatru, jeśli dostępne
                    wind_speeds = daily.get("windspeed_10m_max", [])
                    wind_directions = daily.get("winddirection_10m_dominant", [])
                    
                    if (isinstance(wind_speeds, list) and i < len(wind_speeds) and 
                        isinstance(wind_directions, list) and i < len(wind_directions)):
                        try:
                            forecast[ATTR_FORECAST_WIND_SPEED] = float(wind_speeds[i])
                            forecast[ATTR_FORECAST_WIND_BEARING] = float(wind_directions[i])
                        except (TypeError, ValueError):
                            pass  # Opcjonalne: zaloguj błąd konwersji
                    
                    # Pobierz prawdopodobieństwo opadów, jeśli dostępne
                    precip_probs = daily.get("precipitation_probability_max", [])
                    if isinstance(precip_probs, list) and i < len(precip_probs) and precip_probs[i] is not None:
                        try:
                            forecast[ATTR_FORECAST_PRECIPITATION_PROBABILITY] = float(precip_probs[i])
                        except (TypeError, ValueError):
                            pass  # Opcjonalne: zaloguj błąd konwersji
                    
                    forecast_data.append(forecast)
                    
                except Exception as e:
                    _LOGGER.warning("Weather entity %s: Błąd podczas przetwarzania prognozy na dzień %d: %s", 
                                 getattr(self, 'entity_id', 'nieznana'), i, str(e), exc_info=True)
                    continue
            
            return forecast_data
            
        except Exception as e:
            _LOGGER.error("Błąd w metodzie forecast_daily dla encji %s: %s", 
                         getattr(self, 'entity_id', 'nieznana'), str(e), exc_info=True)
            return []

    def _get_condition(self, weather_code: int | None, is_day: bool = True) -> str | None:
        """
        Return the condition from weather code.
        
        Args:
            weather_code: Kod warunków pogodowych z API Open-Meteo (0-99)
            is_day: Czy jest dzień (wpływa na ikonę dla czystego nieba)
            
        Returns:
            str | None: Warunek pogodowy zrozumiały dla interfejsu Home Assistant lub None w przypadku błędu
            
        Note:
            Mapa warunków pogodowych jest zdefiniowana w pliku const.py jako CONDITION_MAP.
            Kody pogodowe są zgodne z dokumentacją Open-Meteo:
            https://open-meteo.com/en/docs#api_form
        """
        try:
            # Sprawdź czy weather_code jest None
            if weather_code is None:
                _LOGGER.debug("Weather entity %s: Brak kodu pogodowego w _get_condition", 
                            getattr(self, 'entity_id', 'nieznana'))
                return None
            
            # Sprawdź czy is_day jest prawidłową wartością logiczną
            if not isinstance(is_day, bool):
                _LOGGER.warning("Weather entity %s: Nieprawidłowa wartość is_day: %s. Używam domyślnej wartości True", 
                             getattr(self, 'entity_id', 'nieznana'), str(is_day))
                is_day = True
                
            # Sprawdź czy weather_code jest prawidłową liczbą całkowitą
            try:
                weather_code = int(weather_code)
            except (TypeError, ValueError) as e:
                _LOGGER.warning("Weather entity %s: Nieprawidłowy format kodu pogodowego: %s (typ: %s)", 
                             getattr(self, 'entity_id', 'nieznana'), 
                             str(weather_code), 
                             type(weather_code).__name__)
                return None
            
            # Sprawdź zakres kodu pogodowego (0-99 zgodnie z dokumentacją Open-Meteo)
            if not (0 <= weather_code <= 99):
                _LOGGER.warning("Weather entity %s: Kod pogodowy poza zakresem 0-99: %d", 
                             getattr(self, 'entity_id', 'nieznana'), weather_code)
                return None
            
            # Obsłuż specjalny przypadek czystego nieba (kod 0), który ma różne ikony w dzień i w nocy
            if weather_code == 0:
                return "sunny" if is_day else "clear-night"
            
            # Dla pozostałych kodów użyj mapy warunków z const.py
            condition = CONDITION_MAP.get(weather_code)
            
            if condition is None:
                # To nie powinno się zdarzyć, ponieważ mamy pełną mapę warunków,
                # ale na wszelki wypadek logujemy ostrzeżenie
                _LOGGER.warning("Weather entity %s: Brak mapowania dla kodu warunków pogodowych: %d. "
                             "Używam domyślnej wartości None.", 
                             getattr(self, 'entity_id', 'nieznana'), weather_code)
                return None
                
            _LOGGER.debug("Weather entity %s: Dla kodu %d zwrócono warunek: %s (is_day=%s)", 
                         getattr(self, 'entity_id', 'nieznana'), weather_code, condition, str(is_day))
            
            return condition
            
        except Exception as e:
            _LOGGER.error("Błąd w metodzie _get_condition dla encji %s: %s\nSzczegóły: %s", 
                         getattr(self, 'entity_id', 'nieznana'), 
                         str(e), 
                         f"weather_code={weather_code}, is_day={is_day}",
                         exc_info=True)
            return None
    @property
    def forecast_hourly(self) -> list[dict[str, Any]] | None:
        """
        Return the hourly forecast in the format required by the UI.
        
        Returns:
            list[dict[str, Any]] | None: Lista prognoz godzinowych w formacie zgodnym z wymaganiami interfejsu użytkownika
                                        lub None w przypadku błędu
            
        Note:
            Metoda przetwarza dane prognozy godzinnej z API Open-Meteo i konwertuje je do formatu
            wymaganego przez interfejs użytkownika Home Assistant. W przypadku braku danych lub błędów
            zwraca None i loguje odpowiednie komunikaty.
        """
        entity_id = getattr(self, 'entity_id', 'nieznana')
        
        try:
            # Sprawdź dostępność i poprawność danych
            if not self.available:
                _LOGGER.debug("Weather entity %s: Encja niedostępna w metodzie forecast_hourly", 
                            entity_id)
                return None
                
            # Sprawdź czy koordynator i jego dane istnieją
            if not hasattr(self, 'coordinator') or not hasattr(self.coordinator, 'data'):
                _LOGGER.warning("Weather entity %s: Brak danych koordynatora w metodzie forecast_hourly", 
                             entity_id)
                return None
                
            # Sprawdź czy dane koordynatora mają oczekiwany format
            if not isinstance(self.coordinator.data, dict):
                _LOGGER.warning("Weather entity %s: Nieprawidłowy format danych koordynatora w forecast_hourly: %s", 
                             entity_id, type(self.coordinator.data).__name__)
                return None
                
            if not self.coordinator.data or "hourly" not in self.coordinator.data:
                _LOGGER.debug("Weather entity %s: Brak sekcji 'hourly' w danych koordynatora", 
                            entity_id)
                return None
            
            # Pobierz dane o pogodzie godzinowej
            hourly = self.coordinator.data.get("hourly", {})
            if not hourly or not isinstance(hourly, dict):
                _LOGGER.debug("Weather entity %s: Brak lub nieprawidłowy format danych godzinnych w forecast_hourly: %s", 
                           entity_id, type(hourly).__name__)
                return None
                
            # Pobierz listę czasów dla prognozy godzinowej
            time_entries = hourly.get("time", [])
            # Apply horizon to limit heavy processing
            time_entries = time_entries[:HOURLY_FORECAST_HORIZON]
            if not time_entries or not isinstance(time_entries, list):
                _LOGGER.debug("Weather entity %s: Brak danych o czasie w prognozie godzinowej", 
                            entity_id)
                return None
            # Pobierz pozostałe dane pogodowe
            temperature_2m = hourly.get("temperature_2m", [])
            weather_code = hourly.get("weathercode", [])
            precipitation = hourly.get("precipitation", [])
            precipitation_probability = hourly.get("precipitation_probability", [])
            
            # Ujednolicenie długości serii: tniemy wszystkie do wspólnego minimum i do horyzontu
            try:
                series_lengths = [
                    len(time_entries) if isinstance(time_entries, list) else 0,
                    len(temperature_2m) if isinstance(temperature_2m, list) else 0,
                    len(weather_code) if isinstance(weather_code, list) else 0,
                    len(precipitation) if isinstance(precipitation, list) else 0,
                    len(precipitation_probability) if isinstance(precipitation_probability, list) else 0,
                ]
                min_len = min([l for l in series_lengths if l > 0]) if any(series_lengths) else 0
                # Ogranicz do horyzontu
                try:
                    horizon = HOURLY_FORECAST_HORIZON
                except Exception:
                    horizon = 48
                max_hours = min(min_len, horizon)
            except Exception:
                max_hours = min(len(time_entries), 48) if isinstance(time_entries, list) else 0
            
            if max_hours <= 0:
                _LOGGER.debug("Weather entity %s: Brak spójnych danych dla forecast_hourly", entity_id)
                return []
            
            # Przygotuj listę prognoz godzinowych
            forecast_hourly = []
            for i in range(max_hours):
                try:
                    time_entry = time_entries[i]
                    temp_val = float(temperature_2m[i]) if i < len(temperature_2m) else None
                    code_val = int(weather_code[i]) if i < len(weather_code) else None
                    precip_val = float(precipitation[i]) if i < len(precipitation) else None
                    prob_val = int(precipitation_probability[i]) if i < len(precipitation_probability) else None
                    
                    forecast_entry = {
                        "datetime": time_entry,
                        "temperature": temp_val,
                        "condition": self._get_condition(code_val, is_day=self._is_daytime(time_entry)),
                        "precipitation": precip_val,
                        "precipitation_probability": prob_val,
                    }
                    forecast_hourly.append(forecast_entry)
                except (TypeError, ValueError, IndexError) as e:
                    _LOGGER.debug("Weather entity %s: Pomijam błędny rekord forecast_hourly[%d]: %s", entity_id, i, e)
                    continue
            
            return forecast_hourly

            
        except Exception as e:
            _LOGGER.error("Krytyczny błąd w metodzie forecast_hourly dla encji %s: %s\nSzczegóły: %s\nTraceback: %s", 
                         entity_id, 
                         str(e), 
                         f"coordinator_present={hasattr(self, 'coordinator')}",
                         exc_info=True)
            return None
            wind_speeds = hourly.get("windspeed_10m", [])
            wind_directions = hourly.get("winddirection_10m", [])
            precip_probs = hourly.get("precipitation_probability", [])
            
            for i in range(max_hours):
                try:
                    time_entry = time_entries[i]
                    if not isinstance(time_entry, str):
                        _LOGGER.debug("Weather entity %s: Nieprawidłowy format czasu w prognozie godzinowej, godzina %d", 
                                    getattr(self, 'entity_id', 'nieznana'), i)
                        continue
                    
                    # Przygotuj dane prognozy z domyślnymi wartościami
                    forecast = {
                        ATTR_FORECAST_TIME: None,
                        ATTR_FORECAST_CONDITION: None,
                        ATTR_FORECAST_TEMP: None,
                        ATTR_FORECAST_PRECIPITATION: 0.0
                    }
                    
                    # Ustaw czas prognozy
                    try:
                        forecast[ATTR_FORECAST_TIME] = dt_util.parse_datetime(time_entry)
                    except (TypeError, ValueError) as e:
                        _LOGGER.debug("Weather entity %s: Nieprawidłowy format czasu: %s", 
                                    getattr(self, 'entity_id', 'nieznana'), str(time_entry))
                        continue
                    
                    # Ustaw warunki pogodowe (czy jest dzień i kod pogodowy)
                    is_day = is_day_list[i] == 1 if i < len(is_day_list) else True
                    weather_code = weather_codes[i] if i < len(weather_codes) else None
                    forecast[ATTR_FORECAST_CONDITION] = self._get_condition(weather_code, is_day)
                    
                    # Ustaw temperaturę
                    if i < len(temperatures) and temperatures[i] is not None:
                        try:
                            forecast[ATTR_FORECAST_TEMP] = float(temperatures[i])
                        except (TypeError, ValueError):
                            pass
                    
                    # Ustaw opady
                    if i < len(precipitations) and precipitations[i] is not None:
                        try:
                            forecast[ATTR_FORECAST_PRECIPITATION] = float(precipitations[i])
                        except (TypeError, ValueError):
                            pass
                    
                    # Ustaw prędkość i kierunek wiatru, jeśli dostępne
                    if (i < len(wind_speeds) and wind_speeds[i] is not None and 
                        i < len(wind_directions) and wind_directions[i] is not None):
                        try:
                            forecast[ATTR_FORECAST_WIND_SPEED] = float(wind_speeds[i])
                            forecast[ATTR_FORECAST_WIND_BEARING] = float(wind_directions[i])
                        except (TypeError, ValueError):
                            pass  # Opcjonalne: zaloguj błąd konwersji
                    
                    # Ustaw prawdopodobieństwo opadów, jeśli dostępne
                    if i < len(precip_probs) and precip_probs[i] is not None:
                        try:
                            forecast[ATTR_FORECAST_PRECIPITATION_PROBABILITY] = float(precip_probs[i])
                        except (TypeError, ValueError):
                            pass  # Opcjonalne: zaloguj błąd konwersji
                    
                    forecast_data.append(forecast)
                    
                except Exception as e:
                    _LOGGER.warning("Weather entity %s: Błąd podczas przetwarzania prognozy na godzinę %d: %s", 
                                 getattr(self, 'entity_id', 'nieznana'), i, str(e), exc_info=True)
                    continue
            
            return forecast_data
            
        except Exception as e:
            _LOGGER.error("Błąd w metodzie forecast_hourly dla encji %s: %s", 
                         getattr(self, 'entity_id', 'nieznana'), str(e), exc_info=True)
            return []

    # These async forecast methods are for newer HA versions and call the properties
    async def async_forecast_daily(self) -> list[dict[str, Any]]:
        """
        Return the daily forecast asynchronously.
        
        Returns:
            list[dict]: Lista prognoz dziennych, gdzie każda prognoza to słownik z danymi pogodowymi
        """
        try:
            if not hasattr(self, 'forecast_daily'):
                _LOGGER.error("Weather entity %s: Brak metody forecast_daily w async_forecast_daily", 
                            getattr(self, 'entity_id', 'nieznana'))
                return []
                
            result = self.forecast_daily
            
            if not isinstance(result, list):
                _LOGGER.warning("Weather entity %s: Nieprawidłowy format wyniku z forecast_daily: %s", 
                             getattr(self, 'entity_id', 'nieznana'), str(type(result)))
                return []
                
            return result
            
        except Exception as e:
            _LOGGER.error("Błąd w metodzie async_forecast_daily dla encji %s: %s", 
                         getattr(self, 'entity_id', 'nieznana'), str(e), exc_info=True)
            return []

    async def async_forecast_hourly(self) -> list[dict[str, Any]]:
        """
        Return the hourly forecast asynchronously.
        
        Returns:
            list[dict]: Lista prognoz godzinowych, gdzie każda prognoza to słownik z danymi pogodowymi
        """
        try:
            if not hasattr(self, 'forecast_hourly'):
                _LOGGER.error("Weather entity %s: Brak metody forecast_hourly w async_forecast_hourly", 
                            getattr(self, 'entity_id', 'nieznana'))
                return []
                
            result = self.forecast_hourly
            
            if not isinstance(result, list):
                _LOGGER.warning("Weather entity %s: Nieprawidłowy format wyniku z forecast_hourly: %s", 
                             getattr(self, 'entity_id', 'nieznana'), str(type(result)))
                return []
                
            return result
            
        except Exception as e:
            _LOGGER.error("Błąd w metodzie async_forecast_hourly dla encji %s: %s", 
                         getattr(self, 'entity_id', 'nieznana'), str(e), exc_info=True)
            return []

    @callback
    def _check_device_removed(self, *_) -> None:
        """Check if this entity's device has been removed and remove the entity if so."""
        if not hasattr(self, 'hass') or not hasattr(self, '_config_entry') or not self._config_entry:
            return
            
        try:
            # Check if this is a device instance and if the device still exists
            if hasattr(self, '_device_id') and self._device_id:
                device_instances = self.hass.data[DOMAIN][self._config_entry.entry_id].get("device_instances", {})
                if self._device_id not in device_instances:
                    _LOGGER.debug("Removing weather entity for removed device: %s", self._device_id)
                    self.hass.async_create_task(self.async_remove(force_remove=True))
        except Exception as err:
            _LOGGER.error("Error in _check_device_removed: %s", str(err), exc_info=True)

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to Home Assistant."""
        await super().async_added_to_hass()
        
        # Initialize coordinator data if it's None
        if not hasattr(self, 'coordinator') or self.coordinator is None:
            _LOGGER.error("Coordinator not available for entity %s", getattr(self, 'entity_id', 'unknown'))
            return
            
        # Initialize coordinator data if it's empty
        if not hasattr(self.coordinator, 'data') or self.coordinator.data is None:
            _LOGGER.debug("Initializing empty coordinator data for entity %s", getattr(self, 'entity_id', 'unknown'))
            self.coordinator.data = {}
        
        # Add listener for coordinator updates
        self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))
        
        # Additional safeguards for NoneType errors
        if not hasattr(self, 'hass') or not hasattr(self, '_config_entry') or not self._config_entry:
            _LOGGER.error("Initialization error: missing required attributes in entity %s", 
                        getattr(self, 'entity_id', 'unknown'))
            return
            
        # Logika widoczności głównej encji: ukryj, jeśli istnieją instancje urządzeń
        if not self._device_id:  # Tylko dla głównej encji
            if DOMAIN not in self.hass.data or not self._config_entry.entry_id in self.hass.data[DOMAIN]:
                _LOGGER.error("Brak danych konfiguracyjnych dla wpisu %s w domenie %s", 
                           self._config_entry.entry_id, DOMAIN)
                return
                
            device_instances = self.hass.data[DOMAIN][self._config_entry.entry_id].get("device_instances", {})
            
            # Dodaj nasłuchiwacz, aby aktualizować stan encji po pomyślnej aktualizacji urządzeń
            self.async_on_remove(
                async_dispatcher_connect(
                    self.hass,
                    SIGNAL_UPDATE_ENTITIES,
                    self._check_device_removed,
                )
            )
            
            # Ustaw prawidłową nazwę obszaru na podstawie dostępnych danych
            if hasattr(self, '_device_entity_id') and self._device_entity_id:
                try:
                    device_registry = await self.hass.helpers.device_registry.async_get_registry()
                    
                    # Pobierz identyfikator urządzenia z entity_id
                    device_id = None
                    if '.' in self._device_entity_id:
                        domain, object_id = self._device_entity_id.split('.', 1)
                        device_entry = device_registry.async_get_device(identifiers={(domain, object_id)})
                        
                        if device_entry:
                            # Użyj nazwy z rejestru urządzeń, jeśli jest dostępna
                            if device_entry.name:
                                self._device_name = device_entry.name
                            
                            # Sprawdź, czy urządzenie ma przypisany obszar
                            if device_entry.area_id:
                                area_registry = await self.hass.helpers.area_registry.async_get_registry()
                                area_entry = area_registry.async_get_area(device_entry.area_id)
                                if area_entry and area_entry.name:
                                    self._attr_device_info["suggested_area"] = area_entry.name
                                    self._force_update = True  # Wymuś aktualizację interfejsu
                                    self.async_write_ha_state()
                                    return
                    
                    # Jeśli nie udało się pobrać obszaru z rejestru obszarów, użyj innych dostępnych danych
                    if self._device_entity_id in self._area_overrides:
                        self._attr_device_info["suggested_area"] = self._area_overrides[self._device_entity_id]
                    elif self._device_name:
                        self._attr_device_info["suggested_area"] = self._device_name
                    elif " - " in self._attr_name:
                        self._attr_device_info["suggested_area"] = self._attr_name.split(" - ")[-1].strip()
                    
                    # Wymuś aktualizację interfejsu
                    self._force_update = True
                    self.async_write_ha_state()
                    
                except Exception as e:
                    _LOGGER.warning("Nie udało się zaktualizować nazwy obszaru: %s", e)
                    
    def _is_daytime(self, dt_input) -> bool:
        """
        Check if given datetime is during daytime based on sunrise/sunset data.
        
        Args:
            dt_input: Datetime to check (can be datetime object or ISO format string)
            
        Returns:
            bool: True if it's daytime, False otherwise
        """
        _LOGGER.debug("Sprawdzanie pory dnia dla: %s (typ: %s)", dt_input, type(dt_input).__name__)
        try:
            if not hasattr(self, 'coordinator') or not hasattr(self.coordinator, 'data'):
                _LOGGER.debug("Brak danych koordynatora do określenia dnia/nocy")
                return True  # Domyślnie uznajemy, że jest dzień
            
            # Konwertuj wejście na obiekt datetime, jeśli to konieczne
            if isinstance(dt_input, str):
                try:
                    dt_utc = datetime.fromisoformat(dt_input.replace('Z', '+00:00'))
                except ValueError:
                    _LOGGER.warning("Nieprawidłowy format daty: %s", dt_input)
                    return True
            elif isinstance(dt_input, datetime):
                dt_utc = dt_input
            else:
                _LOGGER.warning("Nieobsługiwany typ danych wejściowych: %s", type(dt_input))
                return True
                
            # Pobierz dane o wschodzie i zachodzie słońca
            data = self.coordinator.data
            sunrise = data.get('daily', {}).get('sunrise', [])
            sunset = data.get('daily', {}).get('sunset', [])
            
            if not sunrise or not sunset:
                _LOGGER.debug("Brak danych o wschodzie/zachodzie słońca")
                return True  # Domyślnie uznajemy, że jest dzień
                
            try:
                # Użyj pierwszego dostępnego wschodu i zachodu
                sunrise_time = datetime.fromisoformat(sunrise[0].replace('Z', '+00:00'))
                sunset_time = datetime.fromisoformat(sunset[0].replace('Z', '+00:00'))
                
                # Sprawdź, czy aktualna godzina jest między wschodem a zachodem
                is_day = sunrise_time.time() <= dt_utc.time() < sunset_time.time()
                _LOGGER.debug("Określono porę dnia: %s (godzina: %s, wschód: %s, zachód: %s)", 
                            'dzień' if is_day else 'noc', 
                            dt_utc.time(), 
                            sunrise_time.time(), 
                            sunset_time.time())
                return is_day
                
            except (ValueError, IndexError) as e:
                _LOGGER.warning("Błąd podczas przetwarzania czasu wschodu/zachodu: %s", str(e))
                return True
            
        except Exception as e:
            _LOGGER.error("Błąd podczas określania pory dnia: %s", str(e), exc_info=True)
            return True  # W przypadku błędu uznajemy, że jest dzień
            
    async def async_update(self) -> None:
        """Update the entity."""
        _LOGGER.debug("Rozpoczęcie aktualizacji danych dla encji %s", getattr(self, 'entity_id', 'nieznana'))
        try:
            if not hasattr(self, 'coordinator') or not self.coordinator:
                _LOGGER.error("Brak koordynatora do aktualizacji dla encji %s", getattr(self, 'entity_id', 'nieznana'))
                return
                
            # Pobierz bieżące dane lokalizacyjne przed aktualizacją
            old_lat = None
            old_lon = None
            if hasattr(self.coordinator, 'latitude'):
                old_lat = self.coordinator.latitude
            if hasattr(self.coordinator, 'longitude'):
                old_lon = self.coordinator.longitude
            
            # Wymuś aktualizację danych
            await self.coordinator.async_request_refresh()
            
            # Sprawdź, czy lokalizacja się zmieniła
            new_lat = getattr(self.coordinator, 'latitude', None)
            new_lon = getattr(self.coordinator, 'longitude', None)
            
            if old_lat != new_lat or old_lon != new_lon:
                _LOGGER.info("Zmiana lokalizacji z (%s, %s) na (%s, %s) dla encji %s", 
                           old_lat, old_lon, new_lat, new_lon, getattr(self, 'entity_id', 'nieznana'))
            
            _LOGGER.debug("Zakończono aktualizację danych dla encji %s. Nowe dane: %s", 
                         getattr(self, 'entity_id', 'nieznana'), 
                         bool(self.coordinator.data) if hasattr(self.coordinator, 'data') else 'brak danych')
                         
            # Wymuś aktualizację interfejsu użytkownika
            self.async_write_ha_state()
            
        except Exception as e:
            _LOGGER.error("Błąd podczas aktualizacji danych dla encji %s: %s", 
                         getattr(self, 'entity_id', 'nieznana'), 
                         str(e), 
                         exc_info=True)
            raise

    @property
    def entity_picture(self) -> str | None:
        """
        Return the entity picture to use in the frontend, if any.
        
        Returns:
            str | None: Ścieżka do ikony lub None w przypadku błędu
        """
        try:
            # Sprawdź, czy mamy dostęp do atrybutu condition
            if not hasattr(self, 'condition'):
                _LOGGER.debug("Weather entity %s: Brak atrybutu 'condition' w metodzie entity_picture",
                            getattr(self, 'entity_id', 'nieznana'))
                return None
                
            # Sprawdź, czy warunek jest ustawiony
            if not self.condition:
                _LOGGER.debug("Weather entity %s: Brak warunku pogodowego w metodzie entity_picture",
                            getattr(self, 'entity_id', 'nieznana'))
                return None
                
            # Mapowanie warunków na nazwy plików ikon
            icon_mapping = {
                "clear-night": "clear-night",
                "cloudy": "cloudy",
                "fog": "fog",
                "hail": "hail",
                "lightning": "lightning",
                "lightning-rainy": "lightning-rainy",
                "partlycloudy": "partlycloudy",
                "pouring": "pouring",
                "rainy": "rainy",
                "snowy": "snowy",
                "snowy-rainy": "snowy-rainy",
                "sunny": "sunny",
                "windy": "windy",
                "windy-variant": "windy-variant",
                "exceptional": "alert"
            }
            
            # Pobierz odpowiednią nazwę ikony z mapowania z domyślną wartością
            icon_name = icon_mapping.get(self.condition, "weather-sunny")
            
            # Sprawdź, czy nazwa ikony jest poprawnym łańcuchem znaków
            if not isinstance(icon_name, str) or not icon_name.strip():
                _LOGGER.warning("Weather entity %s: Nieprawidłowa nazwa ikony: %s",
                             getattr(self, 'entity_id', 'nieznana'), str(icon_name))
                icon_name = "weather-sunny"  # Domyślna ikona w przypadku błędu
            
            # Utwórz ścieżkę do ikony
            icon_path = f"/local/weather_icons/{icon_name}.svg"
            
            _LOGGER.debug("Weather entity %s: Użyto ikony: %s dla warunku: %s",
                        getattr(self, 'entity_id', 'nieznana'), icon_path, self.condition)
            
            return icon_path
            
        except Exception as e:
            _LOGGER.error("Błąd w metodzie entity_picture dla encji %s: %s",
                         getattr(self, 'entity_id', 'nieznana'), str(e), exc_info=True)
            return None