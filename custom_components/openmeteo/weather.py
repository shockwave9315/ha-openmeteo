"""Support for Open-Meteo weather service with device tracking."""
from __future__ import annotations

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
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from . import OpenMeteoDataUpdateCoordinator, OpenMeteoInstance
from .const import CONDITION_MAP, DOMAIN, SIGNAL_UPDATE_ENTITIES

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Open-Meteo weather entity based on a config entry."""
    entry_id = config_entry.entry_id
    
    # Check if this is a device instance
    if "device_id" in config_entry.data:
        # This is a device instance, add a single weather entity
        device_id = config_entry.data["device_id"]
        coordinator = hass.data[DOMAIN][entry_id]["device_instances"][device_id].coordinator
        async_add_entities([OpenMeteoWeather(coordinator, config_entry, device_id)])
    else:
        # This is the main instance, add a single weather entity
        coordinator = hass.data[DOMAIN][entry_id]["main_instance"].coordinator
        async_add_entities([OpenMeteoWeather(coordinator, config_entry)])
        
        # Add a listener for device instance updates
        @callback
        def _async_update_entities(entry_id: str) -> None:
            """Update entities when device instances change."""
            if entry_id != config_entry.entry_id:
                return
                
            # Get all device instances
            device_instances = hass.data[DOMAIN][entry_id].get("device_instances", {})
            
            # Get all existing entities
            entity_registry = er.async_get(hass)
            entities = er.async_entries_for_config_entry(
                entity_registry, config_entry.entry_id
            )
            
            # Find all device weather entities
            device_entities = [
                entity for entity in entities 
                if entity.domain == "weather" and "device_id" in entity.unique_id
            ]
            
            # Find all device IDs that already have entities
            existing_device_ids = {
                entity.unique_id.split("_")[-1] 
                for entity in device_entities
            }
            
            # Add entities for new device instances
            for device_id, instance in device_instances.items():
                if device_id not in existing_device_ids:
                    async_add_entities([
                        OpenMeteoWeather(instance.coordinator, instance.entry, device_id)
                    ])
        
        # Listen for device instance updates
        config_entry.async_on_unload(
            async_dispatcher_connect(
                hass, 
                SIGNAL_UPDATE_ENTITIES, 
                _async_update_entities
            )
        )
        
        # Initial update
        _async_update_entities(config_entry.entry_id)

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
        device_id: str = None
    ) -> None:
        """Initialize the Open-Meteo weather."""
        self.coordinator = coordinator
        self._device_id = device_id
        self._config_entry = config_entry
        
        # Set up unique ID and name based on whether this is a device instance or not
        if device_id:
            # This is a device instance
            self._attr_name = config_entry.data.get("friendly_name", f"Open-Meteo {device_id}")
            self._attr_unique_id = f"{config_entry.entry_id}-weather-{device_id}"
            self._attr_entity_registry_visible_default = True
        else:
            # This is the main instance
            self._attr_name = config_entry.data.get("name", "Open-Meteo")
            self._attr_unique_id = f"{config_entry.entry_id}-weather"
            
            # Only show the main entity if there are no device instances
            device_instances = self.hass.data[DOMAIN][config_entry.entry_id].get("device_instances", {})
            self._attr_entity_registry_visible_default = len(device_instances) == 0
        
        # Set up device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
            "name": self._attr_name,
            "manufacturer": "Open-Meteo",
        }
        
        # Add device ID to device info if this is a device instance
        if device_id:
            self._attr_device_info["via_device"] = (DOMAIN, config_entry.entry_id)
            
            # Pobierz dane potrzebne do późniejszego ustawienia suggested_area
            self._device_entity_id = config_entry.data.get("device_entity_id")
            self._device_name = config_entry.data.get("device_name")
            self._area_overrides = config_entry.data.get("area_overrides", {})
            self._device_id = device_id
            
            # Tymczasowo ustaw domyślną wartość, zostanie zaktualizowana w async_added_to_hass
            self._attr_device_info["suggested_area"] = f"Lokalizacja {device_id[-4:]}"
        
        self._attr_should_poll = False

    @property
    def available(self) -> bool:
        """Return if weather data is available."""
        if not hasattr(self, 'coordinator') or not self.coordinator:
            return False
            
        # Check if this is a device instance that has been removed
        if self._device_id and hasattr(self.hass.data, 'get'):
            entry_id = self._config_entry.entry_id
            if (DOMAIN in self.hass.data and 
                entry_id in self.hass.data[DOMAIN] and 
                self._device_id not in self.hass.data[DOMAIN][entry_id].get("device_instances", {})):
                return False
                
        return bool(self.coordinator.last_update_success if hasattr(self.coordinator, 'last_update_success') else False)

    @property
    def condition(self) -> str | None:
        """Return the current condition."""
        if not self.available or not hasattr(self.coordinator, 'data') or "current_weather" not in self.coordinator.data:
            return None
        
        is_day = self.coordinator.data["current_weather"].get("is_day", 1) == 1
        weather_code = self.coordinator.data["current_weather"].get("weathercode")
        return self._get_condition(weather_code, is_day) if weather_code is not None else None

    @property
    def native_temperature(self) -> float | None:
        """Return the temperature."""
        if not self.available or not hasattr(self.coordinator, 'data') or "current_weather" not in self.coordinator.data:
            return None
            
        temp = self.coordinator.data["current_weather"].get("temperature")
        return float(temp) if temp is not None else None

    @property
    def native_pressure(self) -> float | None:
        """Return the pressure."""
        if not self.available or not hasattr(self.coordinator, 'data') or "hourly" not in self.coordinator.data:
            return None
            
        pressures = self.coordinator.data["hourly"].get("surface_pressure", [])
        return float(pressures[0]) if pressures and pressures[0] is not None else None

    @property
    def humidity(self) -> float | None:
        """Return the humidity."""
        if not self.available or not hasattr(self.coordinator, 'data') or "hourly" not in self.coordinator.data:
            return None
        humidity_values = self.coordinator.data["hourly"].get("relativehumidity_2m", [None])
        return float(humidity_values[0]) if humidity_values and humidity_values[0] is not None else None

    @property
    def native_wind_speed(self) -> float | None:
        """Return the wind speed."""
        if not self.available or not hasattr(self.coordinator, 'data') or "current_weather" not in self.coordinator.data:
            return None
        wind_speed = self.coordinator.data["current_weather"].get("windspeed")
        return float(wind_speed) if wind_speed is not None else None

    @property
    def wind_bearing(self) -> float | None:
        """Return the wind bearing."""
        if not self.available or not hasattr(self.coordinator, 'data') or "current_weather" not in self.coordinator.data:
            return None
        wind_direction = self.coordinator.data["current_weather"].get("winddirection")
        return float(wind_direction) if wind_direction is not None else None

    @property
    def native_visibility(self) -> float | None:
        """Return the visibility."""
        if not self.available or not hasattr(self.coordinator, 'data') or "hourly" not in self.coordinator.data:
            return None
        visibility_values = self.coordinator.data["hourly"].get("visibility", [None])
        return float(visibility_values[0]) if visibility_values and visibility_values[0] is not None else None

    @property
    def forecast_daily(self) -> list[dict[str, Any]]:
        """Return the daily forecast in the format required by the UI."""
        if not self.available or not hasattr(self.coordinator, 'data') or "daily" not in self.coordinator.data:
            return []

        daily = self.coordinator.data["daily"]
        time_entries = daily.get("time", [])
        forecast_data = []

        for i, time_entry in enumerate(time_entries):
            if i >= 7:  # Limit to 7 days
                break

            forecast_time = dt_util.parse_datetime(f"{time_entry}T12:00:00")
            forecast = {
                ATTR_FORECAST_TIME: forecast_time,
                ATTR_FORECAST_CONDITION: self._get_condition(
                    daily.get("weathercode", [None] * len(time_entries))[i],
                    is_day=True  # Daily forecast always assumes day
                ),
                ATTR_FORECAST_TEMP: daily.get("temperature_2m_max", [None] * len(time_entries))[i],
                ATTR_FORECAST_TEMP_LOW: daily.get("temperature_2m_min", [None] * len(time_entries))[i],
                ATTR_FORECAST_PRECIPITATION: daily.get("precipitation_sum", [0] * len(time_entries))[i],
            }

            if "windspeed_10m_max" in daily and "winddirection_10m_dominant" in daily:
                forecast[ATTR_FORECAST_WIND_SPEED] = daily["windspeed_10m_max"][i]
                forecast[ATTR_FORECAST_WIND_BEARING] = daily["winddirection_10m_dominant"][i]

            if "precipitation_probability_max" in daily:
                forecast[ATTR_FORECAST_PRECIPITATION_PROBABILITY] = daily["precipitation_probability_max"][i]

            forecast_data.append(forecast)

        return forecast_data

    def _get_condition(self, weather_code: int | None, is_day: bool = True) -> str | None:
        """Return the condition from weather code."""
        if weather_code is None:
            return None

        # Handle the unique case for clear sky first, which has a distinct night state
        if weather_code == 0:
            return "sunny" if is_day else "clear-night"

        # For all other codes, rely on the CONDITION_MAP.
        # The frontend will handle showing the correct day/night icon automatically
        # based on the sun's state and this base condition.
        return CONDITION_MAP.get(weather_code)

    @property
    def forecast_hourly(self) -> list[dict[str, Any]]:
        """Return the hourly forecast in the format required by the UI."""
        if not self.available or not hasattr(self.coordinator, 'data') or "hourly" not in self.coordinator.data:
            return []

        hourly = self.coordinator.data["hourly"]
        time_entries = hourly.get("time", [])
        forecast_data = []

        for i, time_entry in enumerate(time_entries):
            if i >= 24:  # Limit to 24 hours
                break

            is_day = hourly.get("is_day", [1] * len(time_entries))[i] == 1
            weather_code = hourly.get("weathercode", [None] * len(time_entries))[i]
            
            forecast = {
                ATTR_FORECAST_TIME: dt_util.parse_datetime(time_entry),
                ATTR_FORECAST_CONDITION: self._get_condition(weather_code, is_day),
                ATTR_FORECAST_TEMP: hourly.get("temperature_2m", [None] * len(time_entries))[i],
                ATTR_FORECAST_PRECIPITATION: hourly.get("precipitation", [0] * len(time_entries))[i],
            }

            if "windspeed_10m" in hourly and "winddirection_10m" in hourly:
                forecast[ATTR_FORECAST_WIND_SPEED] = hourly["windspeed_10m"][i]
                forecast[ATTR_FORECAST_WIND_BEARING] = hourly["winddirection_10m"][i]

            if "precipitation_probability" in hourly:
                forecast[ATTR_FORECAST_PRECIPITATION_PROBABILITY] = hourly["precipitation_probability"][i]

            forecast_data.append(forecast)

        return forecast_data

    # These async forecast methods are for newer HA versions and call the properties
    async def async_forecast_daily(self) -> list[dict[str, Any]]:
        """Return the daily forecast."""
        return self.forecast_daily

    async def async_forecast_hourly(self) -> list[dict[str, Any]]:
        """Return the hourly forecast."""
        return self.forecast_hourly

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        
        # Add coordinator listener
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )
        
        # Add listener for device tracker updates
        if hasattr(self, '_device_id'):
            self.async_on_remove(
                async_dispatcher_connect(
                    self.hass,
                    f"{DOMAIN}_update_entities_{self._config_entry.entry_id}",
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
                    
    @property
    def entity_picture(self) -> str | None:
        """Return the entity picture to use in the frontend, if any."""
        if not hasattr(self, 'condition') or not self.condition:
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
        
        # Pobierz odpowiednią nazwę ikony z mapowania
        icon_name = icon_mapping.get(self.condition, "weather-sunny")
        
        # Zwróć pełną ścieżkę do ikony w katalogu www
        return f"/local/weather_icons/{icon_name}.svg"