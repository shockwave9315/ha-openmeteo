# SPDX-License-Identifier: Apache-2.0
# SPDX-License-Identifier: Apache-2.0
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
from homeassistant.util import dt as dt_util

from .coordinator import OpenMeteoDataUpdateCoordinator
from .const import DOMAIN




def _first_daily_dt(data: dict, key: str):
    try:
        val = data.get("daily", {}).get(key, [None])[0]
        if isinstance(val, str):
            try:
                dt = dt_util.parse_datetime(val)
                if dt and dt.tzinfo is None:
                    tz = dt_util.get_time_zone(data.get("timezone")) or dt_util.UTC
                    dt = dt.replace(tzinfo=tz)
                return dt
            except Exception:
                return None
        return val
    except Exception:
        return None
def _first_hourly(data: dict, key: str):
    arr = data.get("hourly", {}).get(key)
    if isinstance(arr, list) and arr:
        return arr[0]
    return None


# helper do widzialności w km (bez walrusa)
def _visibility_km(data: dict):
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
        "value_fn": lambda d: _first_hourly(d, "relative_humidity_2m"),
    },
    "apparent_temperature": {
        "name": "Temperatura odczuwalna",
        "unit": UnitOfTemperature.CELSIUS,
        "icon": "mdi:thermometer-alert",
        "device_class": "temperature",
        "value_fn": lambda d: _first_hourly(d, "apparent_temperature"),
    },
    "uv_index": {
        "name": "Indeks UV",
        "unit": "UV Index",
        "icon": "mdi:sun-wireless-outline",
        "device_class": None,
        "value_fn": lambda d: d.get("current", {}).get("uv_index")
        or _first_hourly(d, "uv_index"),
    },
    "precipitation_probability": {
        "name": "Prawdopodobieństwo opadów",
        "unit": PERCENTAGE,
        "icon": "mdi:weather-pouring",
        "device_class": None,
        "value_fn": lambda d: _first_hourly(d, "precipitation_probability"),
    },
    "precipitation_total": {
        "name": "Suma opadów (deszcz+śnieg)",
        "unit": UnitOfPrecipitationDepth.MILLIMETERS,
        "icon": "mdi:cup-water",
        "device_class": "precipitation",
        # spójnie z _first_hourly
        "value_fn": lambda d: (_first_hourly(d, "precipitation") or 0)
                              + (_first_hourly(d, "snowfall") or 0),
    },
    "wind_speed": {
        "name": "Prędkość wiatru",
        "unit": UnitOfSpeed.KILOMETERS_PER_HOUR,
        "icon": "mdi:weather-windy",
        "device_class": None,
        "value_fn": lambda d: d.get("current_weather", {}).get("windspeed"),
    },
    "wind_gust": {
        "name": "Porywy wiatru",
        "unit": UnitOfSpeed.KILOMETERS_PER_HOUR,
        "icon": "mdi:weather-windy-variant",
        "device_class": None,
        "value_fn": lambda d: _first_hourly(d, "wind_gusts_10m"),
    },
    "wind_bearing": {
        "name": "Kierunek wiatru",
        "unit": DEGREE,
        "icon": "mdi:compass",
        "device_class": None,
        "value_fn": lambda d: d.get("current_weather", {}).get("winddirection"),
    },
    "pressure": {
        "name": "Ciśnienie",
        "unit": UnitOfPressure.HPA,
        "icon": "mdi:gauge",
        "device_class": "pressure",
        "value_fn": lambda d: _first_hourly(d, "pressure_msl"),
    },
    "visibility": {
        "name": "Widzialność",
        "unit": UnitOfLength.KILOMETERS,
        "icon": "mdi:eye",
        "device_class": None,
        "value_fn": _visibility_km,
    },
    "dew_point": {
        "name": "Punkt rosy",
        "unit": UnitOfTemperature.CELSIUS,
        "icon": "mdi:water",
        "device_class": "temperature",
        "value_fn": lambda d: d.get("current", {}).get("dewpoint_2m")
        or _first_hourly(d, "dewpoint_2m"),
    },
    "location": {
        "name": "Lokalizacja",
        "unit": None,
        "icon": "mdi:map-marker",
        "device_class": None,
        "value_fn": lambda d: (
            f"{d.get('location', {}).get('latitude')}, {d.get('location', {}).get('longitude')}"
            if d.get("location", {}).get("latitude") is not None
            and d.get("location", {}).get("longitude") is not None
            else None
        ),
    },

    "sunrise": {
        "name": "Wschód słońca",
        "unit": None,
        "icon": "mdi:weather-sunset-up",
        "device_class": "timestamp",
        "value_fn": lambda d: _first_daily_dt(d, "sunrise"),
    },
    "sunset": {
        "name": "Zachód słońca",
        "unit": None,
        "icon": "mdi:weather-sunset-down",
        "device_class": "timestamp",
        "value_fn": lambda d: _first_daily_dt(d, "sunset"),
    },}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
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
        if not self.coordinator.data:
            return None
        value = SENSOR_TYPES[self._sensor_type]["value_fn"](self.coordinator.data)
        return round(value, 2) if isinstance(value, (int, float)) else value

    @property
    def native_unit_of_measurement(self):
        return SENSOR_TYPES[self._sensor_type]["unit"]

    @property
    def icon(self):
        return SENSOR_TYPES[self._sensor_type]["icon"]

    @property
    def device_class(self):
        return SENSOR_TYPES[self._sensor_type]["device_class"]

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success
