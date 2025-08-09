"""Sensor platform for Open-Meteo."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    DEGREE,
    PERCENTAGE,
    UnitOfLength,
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import OpenMeteoDataUpdateCoordinator
from .const import DOMAIN, MANUFACTURER


def _first_hourly(data: dict, key: str):
    """Get the first item from a hourly data list."""
    arr = data.get("hourly", {}).get(key)
    if isinstance(arr, list) and arr:
        return arr[0]
    return None


def _visibility_km(data: dict):
    """Get visibility in kilometers."""
    v = _first_hourly(data, "visibility")
    return v / 1000 if isinstance(v, (int, float)) else None


SENSOR_TYPES: dict[str, dict] = {
    "temperature": {
        "name": "Temperatura",
        "unit": UnitOfTemperature.CELSIUS,
        "icon": "mdi:thermometer",
        "device_class": "temperature",
        "value_fn": lambda d: d.get("current_weather", {}).get("temperature"),
    },
    "humidity": {
        "name": "Wilgotność",
        "unit": PERCENTAGE,
        "icon": "mdi:water-percent",
        "device_class": "humidity",
        "value_fn": lambda d: _first_hourly(d, "relativehumidity_2m"),
    },
    "apparent_temperature": {
        "name": "Temperatura odczuwalna",
        "unit": UnitOfTemperature.CELSIUS,
        "icon": "mdi:thermometer-alert",
        "device_class": "temperature",
        "value_fn": lambda d: _first_hourly(d, "apparent_temperature"),
    },
    "surface_pressure": {
        "name": "Ciśnienie",
        "unit": UnitOfPressure.HPA,
        "icon": "mdi:gauge",
        "device_class": "pressure",
        "value_fn": lambda d: _first_hourly(d, "surface_pressure"),
    },
    "precipitation": {
        "name": "Opady godzinowe",
        "unit": UnitOfPrecipitationDepth.MILLIMETERS,
        "icon": "mdi:weather-rainy",
        "device_class": "precipitation",
        "value_fn": lambda d: _first_hourly(d, "precipitation"),
    },
    "precipitation_probability": {
        "name": "Prawdopodobieństwo opadów",
        "unit": PERCENTAGE,
        "icon": "mdi:weather-cloudy-alert",
        "device_class": None,
        "value_fn": lambda d: _first_hourly(d, "precipitation_probability"),
    },
    "windspeed": {
        "name": "Prędkość wiatru",
        "unit": UnitOfSpeed.KILOMETERS_PER_HOUR,
        "icon": "mdi:weather-windy",
        "device_class": None,
        "value_fn": lambda d: d.get("current_weather", {}).get("windspeed"),
    },
    "winddirection": {
        "name": "Kierunek wiatru",
        "unit": DEGREE,
        "icon": "mdi:compass-outline",
        "device_class": None,
        "value_fn": lambda d: d.get("current_weather", {}).get("winddirection"),
    },
    "cloudcover": {
        "name": "Zachmurzenie",
        "unit": PERCENTAGE,
        "icon": "mdi:weather-cloudy",
        "device_class": None,
        "value_fn": lambda d: _first_hourly(d, "cloudcover"),
    },
    "visibility": {
        "name": "Widoczność",
        "unit": UnitOfLength.KILOMETERS,
        "icon": "mdi:eye",
        "device_class": None,
        "value_fn": _visibility_km,
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    entities = [OpenMeteoSensor(coordinator, config_entry, k) for k in SENSOR_TYPES]
    async_add_entities(entities)


class OpenMeteoSensor(CoordinatorEntity, SensorEntity):
    """Representation of an Open-Meteo sensor."""

    def __init__(
        self,
        coordinator: OpenMeteoDataUpdateCoordinator,
        config_entry: ConfigEntry,
        sensor_type: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._sensor_type = sensor_type
        self._attr_name = f"{config_entry.data.get('name', 'Open-Meteo')} {SENSOR_TYPES[sensor_type]['name']}"
        self._attr_unique_id = f"{config_entry.entry_id}-{sensor_type}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
            "name": "Open-Meteo",
            "manufacturer": MANUFACTURER,
        }

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        value = SENSOR_TYPES[self._sensor_type]["value_fn"](self.coordinator.data)
        return round(value, 2) if isinstance(value, (int, float)) else value

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
    def state_class(self):
        """Return the state class of the sensor."""
        return SENSOR_TYPES[self._sensor_type].get("state_class")