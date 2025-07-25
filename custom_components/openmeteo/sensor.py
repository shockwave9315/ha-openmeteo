"""Sensor platform for Open-Meteo with device tracking support."""
from __future__ import annotations

import logging
from typing import Any, Optional

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)

_LOGGER = logging.getLogger(__name__)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import OpenMeteoDataUpdateCoordinator, OpenMeteoInstance
from .const import DOMAIN, SIGNAL_UPDATE_ENTITIES

SENSOR_TYPES = {
    "temperature": {
        "name": "Temperatura",
        "unit": UnitOfTemperature.CELSIUS,
        "icon": "mdi:thermometer",
        "device_class": "temperature",
        "value_fn": lambda data: data.get("current_weather", {}).get("temperature"),
    },
    "humidity": {
        "name": "Wilgotność",
        "unit": PERCENTAGE,
        "icon": "mdi:water-percent",
        "device_class": "humidity",
        "value_fn": lambda data: data.get("hourly", {}).get("relativehumidity_2m", [None])[0],
    },
    "apparent_temperature": {
        "name": "Temperatura odczuwalna",
        "unit": UnitOfTemperature.CELSIUS,
        "icon": "mdi:thermometer-alert",
        "device_class": "temperature",
        "value_fn": lambda data: data.get("hourly", {}).get("apparent_temperature", [None])[0],
    },
    "uv_index": {
        "name": "Indeks UV",
        "unit": "UV Index",
        "icon": "mdi:sun-wireless-outline",
        "device_class": None,
        "value_fn": lambda data: data.get("hourly", {}).get("uv_index", [None])[0],
    },
    "precipitation_probability": {
        "name": "Prawdopodobieństwo opadów",
        "unit": PERCENTAGE,
        "icon": "mdi:weather-pouring",
        "device_class": None,
        "value_fn": lambda data: data.get("hourly", {}).get("precipitation_probability", [None])[0],
    },
    "precipitation_total": {
        "name": "Suma opadów (deszcz+śnieg)",
        "unit": UnitOfPrecipitationDepth.MILLIMETERS,
        "icon": "mdi:cup-water",
        "device_class": "precipitation",
        "value_fn": lambda data: (
            data.get("hourly", {}).get("precipitation", [0])[0] or 0
        ) + (
            data.get("hourly", {}).get("snowfall", [0])[0] or 0
        ),
    },
    "wind_speed": {
        "name": "Prędkość wiatru",
        "unit": UnitOfSpeed.KILOMETERS_PER_HOUR,
        "icon": "mdi:weather-windy",
        "device_class": None,
        "value_fn": lambda data: data.get("current_weather", {}).get("windspeed"),
    },
    "wind_gust": {
        "name": "Porywy wiatru",
        "unit": UnitOfSpeed.KILOMETERS_PER_HOUR,
        "icon": "mdi:weather-windy-variant",
        "device_class": None,
        "value_fn": lambda data: data.get("hourly", {}).get("windgusts_10m", [None])[0],
    },
    "wind_bearing": {
        "name": "Kierunek wiatru",
        "unit": "°",
        "icon": "mdi:compass",
        "device_class": None,
        "value_fn": lambda data: data.get("current_weather", {}).get("winddirection"),
    },
    "pressure": {
        "name": "Ciśnienie",
        "unit": UnitOfPressure.HPA,
        "icon": "mdi:gauge",
        "device_class": "pressure",
        "value_fn": lambda data: data.get("hourly", {}).get("surface_pressure", [None])[0],
    },
    "visibility": {
        "name": "Widzialność",
        "unit": "km",
        "icon": "mdi:eye",
        "device_class": None,
        "value_fn": lambda data: data.get("hourly", {}).get("visibility", [None])[0],
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Open-Meteo sensor entities based on a config entry."""
    entry_id = config_entry.entry_id
    
    # Check if this is a device instance
    if "device_id" in config_entry.data:
        # This is a device instance, add sensors for this device
        device_id = config_entry.data["device_id"]
        coordinator = hass.data[DOMAIN][entry_id]["device_instances"][device_id].coordinator
        
        entities = [
            OpenMeteoSensor(coordinator, config_entry, sensor_type, device_id)
            for sensor_type in SENSOR_TYPES
        ]
        
        async_add_entities(entities)
    else:
        # This is the main instance, add main sensors
        coordinator = hass.data[DOMAIN][entry_id]["main_instance"].coordinator
        
        entities = [
            OpenMeteoSensor(coordinator, config_entry, sensor_type)
            for sensor_type in SENSOR_TYPES
        ]
        
        async_add_entities(entities)
        
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
            
            # Find all device sensor entities
            device_entities = [
                entity for entity in entities 
                if entity.domain == "sensor" and "device_id" in entity.unique_id
            ]
            
            # Find all device IDs that already have entities
            existing_device_ids = {
                "_".join(entity.unique_id.split("_")[-2:]) 
                for entity in device_entities
            }
            
            # Add entities for new device instances
            new_entities = []
            for device_id, instance in device_instances.items():
                if device_id not in existing_device_ids:
                    new_entities.extend([
                        OpenMeteoSensor(instance.coordinator, instance.entry, sensor_type, device_id)
                        for sensor_type in SENSOR_TYPES
                    ])
            
            if new_entities:
                async_add_entities(new_entities)
        
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


class OpenMeteoSensor(CoordinatorEntity, SensorEntity):
    """Representation of an Open-Meteo sensor with device tracking support."""

    def __init__(
        self,
        coordinator: OpenMeteoDataUpdateCoordinator,
        config_entry: ConfigEntry,
        sensor_type: str,
        device_id: str = None,
        friendly_name: str = None,
    ) -> None:
        """Initialize the sensor."""
        try:
            super().__init__(coordinator)
            self._sensor_type = sensor_type
            self._config_entry = config_entry
            self._device_id = device_id
            self._friendly_name = friendly_name
            
            if sensor_type not in SENSOR_TYPES:
                _LOGGER.error("Nieznany typ czujnika: %s", sensor_type)
                raise ValueError(f"Nieznany typ czujnika: {sensor_type}")
                
            sensor_config = SENSOR_TYPES[sensor_type]
            
            # Ustaw podstawowe atrybuty
            self._attr_available = False
            self._attr_should_poll = False
            
            # Ustaw unikalny identyfikator i nazwę w zależności od tego, czy to instancja urządzenia, czy główna
            if device_id and friendly_name:
                # To jest instancja urządzenia
                self._attr_name = f"{friendly_name} {sensor_config.get('name', '')}".strip()
                self._attr_unique_id = f"{config_entry.entry_id}-{sensor_type}-{device_id}"
                self._attr_entity_registry_visible_default = True
            else:
                # To jest główna instancja
                base_name = config_entry.data.get('name', 'Open-Meteo')
                self._attr_name = f"{base_name} {sensor_config.get('name', '')}".strip()
                self._attr_unique_id = f"{config_entry.entry_id}-{sensor_type}"
                
                # Pokaż główną encję tylko jeśli nie ma instancji urządzeń
                try:
                    device_instances = self.hass.data.get(DOMAIN, {}).get(config_entry.entry_id, {}).get("device_instances", {})
                    self._attr_entity_registry_visible_default = not bool(device_instances)
                except Exception as e:
                    _LOGGER.warning("Błąd podczas sprawdzania instancji urządzeń: %s", e)
                    self._attr_entity_registry_visible_default = True
            
            # Ustaw podstawowe informacje o urządzeniu
            self._attr_device_info = {
                "identifiers": {(DOMAIN, config_entry.entry_id)},
                "name": self._attr_name.replace(f" {sensor_config.get('name', '')}", "").strip() or "Open-Meteo",
                "manufacturer": "Open-Meteo",
            }
            
            # Dodaj ID urządzenia do informacji o urządzeniu, jeśli to instancja urządzenia
            if device_id and hasattr(self, '_attr_device_info'):
                self._attr_device_info["via_device"] = (DOMAIN, config_entry.entry_id)
                
                # Pobierz dane konfiguracyjne
                config_data = config_entry.data or {}
                device_name = config_data.get("device_name")
                area_overrides = config_data.get("area_overrides", {})
                device_entity_id = config_data.get("device_entity_id")
                
                # Ustaw sugerowany obszar na podstawie dostępnych danych
                if device_entity_id and device_entity_id in area_overrides:
                    self._attr_device_info["suggested_area"] = str(area_overrides[device_entity_id])
                elif device_name:
                    self._attr_device_info["suggested_area"] = str(device_name)
                elif " - " in self._attr_name:
                    self._attr_device_info["suggested_area"] = str(self._attr_name.split(" - ")[-1].strip())
                
                # Ustaw domyślną dostępność na False, aby uniknąć błędów przed pierwszą aktualizacją
                self._attr_available = False
                
        except Exception as e:
            _LOGGER.error("Błąd podczas inicjalizacji czujnika %s: %s", sensor_type, str(e), exc_info=True)
            raise

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if not hasattr(self, 'coordinator') or not self.coordinator or not hasattr(self.coordinator, 'data') or not self.coordinator.data:
            return None
        
        try:
            value = SENSOR_TYPES[self._sensor_type]["value_fn"](self.coordinator.data)
            
            if value is None:
                return None
                
            if isinstance(value, (int, float)):
                return round(float(value), 2)
                
            return value
            
        except (KeyError, IndexError, TypeError, AttributeError) as err:
            _LOGGER.debug("Error getting sensor value for %s: %s", self._sensor_type, err)
            return None

    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement."""
        return SENSOR_TYPES[self._sensor_type]["unit"]

    @property
    def icon(self):
        """Return the icon to use in the frontend."""
        return SENSOR_TYPES[self._sensor_type]["icon"]

    @property
    def device_class(self):
        """Return the device class of the sensor."""
        return SENSOR_TYPES[self._sensor_type]["device_class"]

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not hasattr(self, 'coordinator') or not self.coordinator:
            return False
            
        # Check if this is a device instance that has been removed
        if hasattr(self, '_device_id') and self._device_id and hasattr(self, 'hass') and hasattr(self.hass.data, 'get') and DOMAIN in self.hass.data:
            entry_id = self._config_entry.entry_id
            if (entry_id in self.hass.data[DOMAIN] and 
                self._device_id not in self.hass.data[DOMAIN][entry_id].get("device_instances", {})):
                return False
                
        return bool(self.coordinator.last_update_success if hasattr(self.coordinator, 'last_update_success') else False)
        
    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        
        # Add coordinator listener
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )
        
        # Add listener for device instance removal if this is a device sensor
        if hasattr(self, '_device_id') and self._device_id and hasattr(self, 'hass') and hasattr(self.hass.data, 'get') and DOMAIN in self.hass.data:
            entry_id = self._config_entry.entry_id
            
            @callback
            def _check_device_removed(entry_id: str) -> None:
                """Check if this device instance has been removed."""
                if (entry_id != self._config_entry.entry_id or 
                    not hasattr(self, 'hass') or 
                    DOMAIN not in self.hass.data or 
                    entry_id not in self.hass.data[DOMAIN] or 
                    self._device_id not in self.hass.data[DOMAIN][entry_id].get("device_instances", {})):
                    
                    # Device instance was removed, remove this entity
                    if hasattr(self, 'hass') and hasattr(self, 'entity_id'):
                        self.hass.async_create_task(self.async_remove(force_remove=True))
            
            # Listen for device instance updates
            self.async_on_remove(
                async_dispatcher_connect(
                    self.hass,
                    SIGNAL_UPDATE_ENTITIES,
                    _check_device_removed
                )
            )
    
    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        # Check if this is still a valid device instance
        if hasattr(self, '_device_id') and self._device_id and hasattr(self, 'hass') and hasattr(self.hass.data, 'get') and DOMAIN in self.hass.data:
            entry_id = self._config_entry.entry_id
            if (entry_id in self.hass.data[DOMAIN] and 
                self._device_id not in self.hass.data[DOMAIN][entry_id].get("device_instances", {})):
                # This device instance was removed, remove this entity
                self.hass.async_create_task(self.async_remove(force_remove=True))
                return
        
        # Update the state
        self.async_write_ha_state()