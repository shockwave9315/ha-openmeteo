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

from . import OpenMeteoDataUpdateCoordinator
from .const import DOMAIN

# --- Helper: safely get first hourly value ---
def _first_hourly(data: dict, key: str):
    arr = data.get("hourly", {}).get(key)
    if isinstance(arr, list) and arr:
        return arr[0]
    return None

SENSOR_TYPES: dict[str, dict] = {
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
        "value_fn": lambda data: _first_hourly(data, "relativehumidity_2m"),
    },
    "apparent_temperature": {
        "name": "Temperatura odczuwalna",
        "unit": UnitOfTemperature.CELSIUS,
        "icon": "mdi:thermometer-alert",
        "device_class": "temperature",
        "value_fn": lambda data: _first_hourly(data, "apparent_temperature"),
    },
    "uv_index": {
        "name": "Indeks UV",
        "unit": "UV Index",
        "icon": "mdi:sun-wireless-outline",
        "device_class": None,
        "value_fn": lambda data: _first_hourly(data, "uv_index"),
    },
    "precipitation_probability": {
        "name": "Prawdopodobieństwo opadów",
        "unit": PERCENTAGE,
        "icon": "mdi:weather-pouring",
        "device_class": None,
        "value_fn": lambda data: _first_hourly(data, "precipitation_probability"),
    },
    "precipitation_total": {
        "name": "Suma opadów (deszcz+śnieg)",
        "unit": UnitOfPrecipitationDepth.MILLIMETERS,
        "icon": "mdi:cup-water",
        "device_class": "precipitation",
        "value_fn": lambda data: (
            (data.get("hourly", {}).get("precipitation", [0])[0] or 0) + 
            (data.get("hourly", {}).get("snowfall", [0])[0] or 0)
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
        "value_fn": lambda data: _first_hourly(data, "windgusts_10m"),
    },
    "wind_bearing": {
        "name": "Kierunek wiatru",
        "unit": DEGREE,
        "icon": "mdi:compass",
        "device_class": None,
        "value_fn": lambda data: data.get("current_weather", {}).get("winddirection"),
    },
    "pressure": {
        "name": "Ciśnienie",
        "unit": UnitOfPressure.HPA,
        "icon": "mdi:gauge",
        "device_class": "pressure",
        "value_fn": lambda data: _first_hourly(data, "surface_pressure"),
    },
    "visibility": {
        "name": "Widzialność",
        "unit": UnitOfLength.KILOMETERS,
        "icon": "mdi:eye",
        "device_class": None,
        "value_fn": lambda data: (
            (v := _first_hourly(data, "visibility")) / 1000 if isinstance(v, (int, float)) else None
        ),
    },
}


# Reszta pliku bez zmian
async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Open-Meteo sensor entities based on a config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    entities = [
        OpenMeteoSensor(coordinator, config_entry, sensor_type)
        for sensor_type in SENSOR_TYPES
    ]
    async_add_entities(entities)


class OpenMeteoSensor(SensorEntity):
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
            "manufacturer": "Open-Meteo",
        }

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        
        value = SENSOR_TYPES[self._sensor_type]["value_fn"](self.coordinator.data)
        
        if isinstance(value, (int, float)):
            return round(value, 2)
        return value

    @property
    def native_unit_of_measurement(self):
        """Return unit of measurement."""
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
        return self.coordinator.last_update_success
