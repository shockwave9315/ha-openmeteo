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
    "location": {
        "name": "Lokalizacja",
        "unit": None,
        "icon": "mdi:map-marker",
        "device_class": None,
        "value_fn": lambda data: f"{data.get('latitude', 0):.4f}, {data.get('longitude', 0):.4f}",
    },
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
        
        # Safely get the device instance
        try:
            device_instances = hass.data[DOMAIN][entry_id].get("device_instances", {})
            device_instance = device_instances.get(device_id)
            
            if not device_instance:
                _LOGGER.warning("Device instance not found for device_id %s", device_id)
                return
                
            coordinator = device_instance.coordinator
            if not coordinator:
                _LOGGER.error("Coordinator not found for device_id %s", device_id)
                return
            
            entities = [
                OpenMeteoSensor(coordinator, config_entry, sensor_type, device_id)
                for sensor_type in SENSOR_TYPES
            ]
            
            async_add_entities(entities)
            _LOGGER.debug("Successfully added sensors for device_id %s", device_id)
            
        except Exception as err:
            _LOGGER.error(
                "Error setting up sensors for device_id %s: %s",
                device_id,
                str(err),
                exc_info=True
            )
    else:
        # This is the main instance, add main sensors if they exist
        main_instance = hass.data[DOMAIN][entry_id].get("main_instance")
        device_instances = hass.data[DOMAIN][entry_id].get("device_instances", {})
        
        # Only create main instance entities if there are no device instances
        if not device_instances and main_instance:
            _LOGGER.debug("Setting up main instance sensors")
            try:
                entities = [
                    OpenMeteoSensor(main_instance.coordinator, config_entry, sensor_type)
                    for sensor_type in SENSOR_TYPES
                ]
                async_add_entities(entities)
                _LOGGER.debug("Added %d main instance sensors", len(entities))
            except Exception as err:
                _LOGGER.error(
                    "Error creating main instance sensors: %s",
                    str(err),
                    exc_info=True
                )
        elif device_instances:
            _LOGGER.debug("Device instances present, skipping main instance sensors")
        else:
            _LOGGER.warning("No main instance and no device instances found")
        
        # Add a listener for device instance updates
        @callback
        def _async_update_entities(entry_id: str) -> None:
            """Update entities when device instances change."""
            if entry_id != config_entry.entry_id:
                return
                
            try:
                # Get all device instances
                domain_data = hass.data.get(DOMAIN, {})
                entry_data = domain_data.get(entry_id, {})
                device_instances = entry_data.get("device_instances", {})
                
                if not device_instances:
                    _LOGGER.debug("No device instances found, nothing to update")
                    return
                
                _LOGGER.debug("Updating entities for %d device instances", len(device_instances))
                
                # Get all existing entities
                entity_registry = er.async_get(hass)
                entities = er.async_entries_for_config_entry(
                    entity_registry, config_entry.entry_id
                )
                
                # Find all device sensor entities and their device IDs
                device_entity_map = {}
                for entity in entities:
                    if entity.domain == "sensor" and "device_id" in entity.unique_id:
                        # Extract device ID from unique_id (format: {entry_id}-{device_id}-{sensor_type})
                        parts = entity.unique_id.split('-')
                        if len(parts) >= 2:
                            dev_id = parts[1]  # The part after entry_id
                            device_entity_map[dev_id] = entity
                
                # Add entities for new device instances
                new_entities = []
                for device_id, instance in device_instances.items():
                    if not instance or not hasattr(instance, 'coordinator') or not instance.coordinator:
                        _LOGGER.warning(
                            "Skipping invalid device instance: %s", 
                            device_id
                        )
                        continue
                        
                    # Skip if we already have entities for this device
                    if device_id in device_entity_map:
                        continue
                    
                    # Get friendly name from config or use default
                    friendly_name = None
                    try:
                        if hasattr(instance, 'entry') and hasattr(instance.entry, 'data'):
                            friendly_name = instance.entry.data.get(
                                "friendly_name", 
                                f"Open-Meteo {device_id}"
                            )
                    except Exception as name_err:
                        _LOGGER.warning(
                            "Could not get friendly name for device %s: %s",
                            device_id, str(name_err)
                        )
                        friendly_name = f"Open-Meteo {device_id}"
                    
                    # Create sensors for this device
                    try:
                        device_entities = [
                            OpenMeteoSensor(
                                instance.coordinator, 
                                config_entry, 
                                sensor_type, 
                                device_id,
                                friendly_name
                            )
                            for sensor_type in SENSOR_TYPES
                        ]
                        new_entities.extend(device_entities)
                        _LOGGER.debug("Created %d sensors for device_id: %s", 
                                    len(device_entities), device_id)
                    except Exception as err:
                        _LOGGER.error(
                            "Error creating sensors for device_id %s: %s",
                            device_id,
                            str(err),
                            exc_info=True
                        )
                
                # Add all new entities at once
                if new_entities:
                    _LOGGER.debug("Adding %d new sensor entities", len(new_entities))
                    async_add_entities(new_entities)
                    
            except Exception as update_err:
                _LOGGER.error(
                    "Error in _async_update_entities: %s",
                    str(update_err),
                    exc_info=True
                )
        
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
            # Initialize parent class first
            super().__init__(coordinator)
            
            # Basic attribute initialization
            self._sensor_type = sensor_type
            self._config_entry = config_entry
            self._device_id = device_id
            self._friendly_name = friendly_name
            
            # Validate sensor type
            if sensor_type not in SENSOR_TYPES:
                error_msg = f"Nieznany typ czujnika: {sensor_type}"
                _LOGGER.error(error_msg)
                raise ValueError(error_msg)
                
            sensor_config = SENSOR_TYPES[sensor_type]
            
            # Set basic attributes
            self._attr_available = False
            self._attr_should_poll = False
            
            # Set unique identifier and name based on device instance or main instance
            sensor_name = sensor_config.get('name', '').strip()
            
            if device_id:
                # This is a device instance
                if friendly_name:
                    self._attr_name = f"{friendly_name} {sensor_name}".strip()
                else:
                    # Fallback to device_id if friendly_name is not available
                    device_name = device_id.split('.')[-1].replace('_', ' ').title()
                    self._attr_name = f"{device_name} {sensor_name}".strip()
                
                # Create a more unique ID with entry_id, device_id, and coordinates hash
                coord_hash = ""
                if hasattr(coordinator, '_latitude') and hasattr(coordinator, '_longitude'):
                    coord_hash = f"-{abs(hash((coordinator._latitude, coordinator._longitude))) % 10000:04d}"
                
                self._attr_unique_id = f"{config_entry.entry_id}-{device_id}{coord_hash}-{sensor_type}"
                self._attr_entity_registry_visible_default = True
            else:
                # This is the main instance
                base_name = config_entry.data.get('name', 'Open-Meteo') if config_entry.data else 'Open-Meteo'
                self._attr_name = f"{base_name} {sensor_name}".strip()
                self._attr_unique_id = f"{config_entry.entry_id}-main-{sensor_type}"
                
                # Add coordinates hash to ensure uniqueness for main instance
                if hasattr(coordinator, '_latitude') and hasattr(coordinator, '_longitude'):
                    coord_hash = abs(hash((coordinator._latitude, coordinator._longitude))) % 10000
                    self._attr_unique_id = f"{self._attr_unique_id}-{coord_hash:04d}"
                
                # Show main entity only if there are no device instances
                try:
                    # Safely get device_instances with proper None checks
                    hass = getattr(self, 'hass', None)
                    if hass and hasattr(hass, 'data') and isinstance(hass.data, dict):
                        domain_data = hass.data.get(DOMAIN, {})
                        if isinstance(domain_data, dict):
                            entry_data = domain_data.get(config_entry.entry_id, {})
                            if isinstance(entry_data, dict):
                                device_instances = entry_data.get("device_instances", {})
                                self._attr_entity_registry_visible_default = not bool(device_instances)
                                _LOGGER.debug(
                                    "Sprawdzono instancje urządzeń dla %s. Widoczność: %s",
                                    sensor_type,
                                    self._attr_entity_registry_visible_default
                                )
                                # Przejdź do ustawień urządzenia
                                self._setup_device_info(config_entry, sensor_config, device_id)
                                return
                    
                    # Jeśli dotarliśmy tutaj, coś poszło nie tak z sprawdzaniem
                    _LOGGER.debug(
                        "Nie można określić instancji urządzeń dla %s. Domyślnie widoczne.",
                        sensor_type
                    )
                    self._attr_entity_registry_visible_default = True
                    
                except Exception as e:
                    _LOGGER.warning(
                        "Błąd podczas sprawdzania instancji urządzeń dla %s: %s",
                        sensor_type,
                        str(e),
                        exc_info=True
                    )
                    # Domyślnie ustaw na True, aby upewnić się, że encja jest widoczna w przypadku błędu
                    self._attr_entity_registry_visible_default = True
            
            # Ustaw podstawowe informacje o urządzeniu
            self._setup_device_info(config_entry, sensor_config, device_id)
            
        except Exception as e:
            _LOGGER.error(
                "Błąd podczas inicjalizacji czujnika %s: %s",
                sensor_type,
                str(e),
                exc_info=True
            )
            raise
            
    def _setup_device_info(self, config_entry, sensor_config, device_id):
        """Configure device information for the sensor.
        
        Args:
            config_entry: The config entry for this integration
            sensor_config: Configuration dictionary for this sensor type
            device_id: The device ID if this is a device instance, None for main instance
            
        Note:
            - For device instances, we don't set device_info as the device is managed in __init__.py
            - Only the main instance (when no device_id) gets device_info
        """
        try:
            if not device_id:
                # Only set device_info for the main instance
                self._attr_device_info = {
                    "identifiers": {(DOMAIN, config_entry.entry_id)},
                    "name": "Open-Meteo",
                    "manufacturer": "Open-Meteo",
                }
                _LOGGER.debug("Set device_info for main instance sensor %s", self._sensor_type)
            else:
                # For device instances, don't set device_info as the device is managed in __init__.py
                self._attr_device_info = None
                _LOGGER.debug("Skipping device_info for device instance %s (%s)", 
                            device_id, self._sensor_type)
        except Exception as e:
            _LOGGER.warning(
                "Error configuring device info for %s: %s",
                self._sensor_type,
                str(e),
                exc_info=True
            )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        try:
            # Check if we have all required attributes
            if not getattr(self, 'coordinator', None):
                _LOGGER.debug("No coordinator available for sensor %s", self._sensor_type)
                return None
                
            # Check if coordinator has data
            if not getattr(self.coordinator, 'data', None):
                _LOGGER.debug("No data available in coordinator for sensor %s", self._sensor_type)
                return None
                
            # Get the value using the sensor's value function
            if self._sensor_type not in SENSOR_TYPES:
                _LOGGER.error("Unknown sensor type: %s", self._sensor_type)
                return None
                
            value_fn = SENSOR_TYPES[self._sensor_type].get("value_fn")
            if not callable(value_fn):
                _LOGGER.error("Invalid value function for sensor type: %s", self._sensor_type)
                return None
                
            # Safely call the value function
            value = value_fn(self.coordinator.data)
            
            if value is None:
                _LOGGER.debug("No value available for sensor %s", self._sensor_type)
                return None
                
            # Format the value if it's a number
            if isinstance(value, (int, float)):
                return round(float(value), 2)
                
            return value
            
        except Exception as err:
            _LOGGER.error(
                "Error getting value for sensor %s: %s",
                self._sensor_type,
                str(err),
                exc_info=True
            )
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
        try:
            await super().async_added_to_hass()
            
            # Validate coordinator exists and has required methods
            if not hasattr(self, 'coordinator') or not self.coordinator:
                _LOGGER.error("No coordinator available when adding sensor %s to hass", self._sensor_type)
                return
                
            if not hasattr(self.coordinator, 'async_add_listener'):
                _LOGGER.error("Coordinator does not support async_add_listener")
                return
            
            # Add coordinator listener with error handling
            try:
                self.async_on_remove(
                    self.coordinator.async_add_listener(self._handle_coordinator_update)
                )
            except Exception as err:
                _LOGGER.error(
                    "Error adding coordinator listener for sensor %s: %s",
                    self._sensor_type,
                    str(err),
                    exc_info=True
                )
            
            # Add listener for device instance removal if this is a device sensor
            if (hasattr(self, '_device_id') and self._device_id and 
                hasattr(self, 'hass') and hasattr(self.hass, 'data') and 
                isinstance(self.hass.data, dict) and DOMAIN in self.hass.data):
                
                entry_id = getattr(self._config_entry, 'entry_id', None)
                if not entry_id:
                    _LOGGER.error("No entry_id found in config entry")
                    return
                
                @callback
                def _check_device_removed(entry_id: str) -> None:
                    """Check if this device instance has been removed."""
                    try:
                        if not hasattr(self, 'hass') or not hasattr(self, '_config_entry'):
                            _LOGGER.debug("Missing required attributes in _check_device_removed")
                            return
                            
                        current_entry_id = getattr(self._config_entry, 'entry_id', None)
                        if not current_entry_id or entry_id != current_entry_id:
                            _LOGGER.debug("Entry ID mismatch in _check_device_removed")
                            return
                            
                        if (not hasattr(self.hass, 'data') or 
                            not isinstance(self.hass.data, dict) or 
                            DOMAIN not in self.hass.data or 
                            entry_id not in self.hass.data[DOMAIN] or 
                            self._device_id not in self.hass.data[DOMAIN][entry_id].get("device_instances", {})):
                            
                            # Device instance was removed, remove this entity
                            if hasattr(self, 'hass') and hasattr(self, 'entity_id'):
                                _LOGGER.debug("Removing entity %s as its device was removed", self.entity_id)
                                self.hass.async_create_task(self.async_remove(force_remove=True))
                                
                    except Exception as err:
                        _LOGGER.error(
                            "Error in _check_device_removed for sensor %s: %s",
                            getattr(self, '_sensor_type', 'unknown'),
                            str(err),
                            exc_info=True
                        )
        except Exception as err:
            _LOGGER.error(
                "Unexpected error in async_added_to_hass for sensor %s: %s",
                getattr(self, '_sensor_type', 'unknown'),
                str(err),
                exc_info=True
            )
            
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
        try:
            # Check if this device instance has been removed
            if (hasattr(self, '_device_id') and self._device_id and 
                hasattr(self, 'hass') and hasattr(self.hass, 'data') and 
                isinstance(self.hass.data, dict) and DOMAIN in self.hass.data):
                
                entry_id = getattr(self._config_entry, 'entry_id', None)
                if not entry_id:
                    _LOGGER.error("No entry_id found in config entry")
                    return
                    
                if (entry_id in self.hass.data[DOMAIN] and 
                    self._device_id not in self.hass.data[DOMAIN][entry_id].get("device_instances", {})):
                    
                    _LOGGER.debug("Removing entity %s as its device was removed", getattr(self, 'entity_id', 'unknown'))
                    if hasattr(self.hass, 'async_create_task') and hasattr(self, 'async_remove'):
                        self.hass.async_create_task(self.async_remove(force_remove=True))
                    return
            
            # Only update state if we have a coordinator with data
            if (hasattr(self, 'coordinator') and self.coordinator and 
                hasattr(self.coordinator, 'data') and self.coordinator.data is not None):
                
                self.async_write_ha_state()
                
        except Exception as err:
            _LOGGER.error(
                "Error in _handle_coordinator_update for sensor %s: %s",
                getattr(self, '_sensor_type', 'unknown'),
                str(err),
                exc_info=True
            )