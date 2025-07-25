"""Sensor platform for Open-Meteo with device tracking support."""
from __future__ import annotations

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
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._sensor_type = "precipitation_total" if sensor_type == "precipitation" else sensor_type
        self._device_id = device_id
        self._config_entry = config_entry
        
        # Get sensor configuration
        sensor_config = SENSOR_TYPES[self._sensor_type]
        
        # Set up unique ID and name based on whether this is a device instance or not
        if device_id:
            # This is a device instance
            friendly_name = config_entry.data.get("friendly_name", f"Open-Meteo {device_id}")
            self._attr_name = f"{friendly_name} {sensor_config['name']}"
            self._attr_unique_id = f"{config_entry.entry_id}-{self._sensor_type}-{device_id}"
            self._attr_entity_registry_visible_default = True
        else:
            # This is the main instance
            self._attr_name = f"{config_entry.data.get('name', 'Open-Meteo')} {sensor_config['name']}"
            self._attr_unique_id = f"{config_entry.entry_id}-{self._sensor_type}"
            
            # Only show the main entity if there are no device instances
            device_instances = self.hass.data[DOMAIN][config_entry.entry_id].get("device_instances", {})
            self._attr_entity_registry_visible_default = not device_instances
        
        # Set up basic device info
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
            "name": self._attr_name.replace(f" {sensor_config['name']}", ""),
            "manufacturer": "Open-Meteo",
        }
        
        # Add device ID to device info if this is a device instance
        if device_id:
            self._attr_device_info["via_device"] = (DOMAIN, config_entry.entry_id)
            
            # Pobierz nazwę urządzenia z konfiguracji, jeśli dostępna
            device_name = config_entry.data.get("device_name")
            
            # Sprawdź, czy mamy nadpisany obszar w konfiguracji
            area_overrides = config_entry.data.get("area_overrides", {})
            device_entity_id = config_entry.data.get("device_entity_id")
            
            if device_entity_id in area_overrides:
                # Użyj nadpisanego obszaru
                self._attr_device_info["suggested_area"] = area_overrides[device_entity_id]
            elif device_name:
                # Użyj nazwy urządzenia jako sugerowanego obszaru
                self._attr_device_info["suggested_area"] = device_name
            else:
                # Domyślnie: użyj części po myślniku w nazwie
                if " - " in self._attr_name:
                    self._attr_device_info["suggested_area"] = self._attr_name.split(" - ")[-1].strip()

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