# SPDX-License-Identifier: Apache-2.0
"""Sensor platform for Open-Meteo."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
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
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import OpenMeteoDataUpdateCoordinator
from .helpers import (
    extra_attrs as _extra_attrs,
    hourly_at_now as _hourly_at_now,
    hourly_sum_last_n as _hourly_sum_last_n,
)

# Polish slugs for sensor types
OBJECT_ID_PL = {
    "temperature": "temperatura",
    "apparent_temperature": "temperatura_odczuwalna",
    "pressure": "cisnienie",
    "humidity": "wilgotnosc",
    "wind_speed": "wiatr",
    "wind_gust": "porywy_wiatru",
    "wind_bearing": "kierunek_wiatru",
    "precipitation_probability": "prawdopodobienstwo_opadow",
    "visibility": "widocznosc",
    "dew_point": "punkt_rosy",
    "sunrise": "wschod_slonca",
    "sunset": "zachod_slonca",
    "uv_index": "indeks_uv",
}


def _first_daily_dt(data: dict, key: str):
    """Safely get the first value from a daily array and parse it as datetime."""
    try:
        val = (data.get("daily", {}) or {}).get(key, [None])[0]
        if not isinstance(val, str):
            return None
        dt = dt_util.parse_datetime(val)
        if dt and dt.tzinfo is None:
            tz = dt_util.get_time_zone(data.get("timezone")) or dt_util.UTC
            dt = dt.replace(tzinfo=tz)
        return dt
    except (IndexError, TypeError, ValueError):
        return None


def _visibility_km(d: dict) -> float | None:
    """Return visibility in kilometers."""
    vis = _hourly_at_now(d, "visibility")
    return round(vis / 1000, 2) if isinstance(vis, (int, float)) else None


@dataclass(frozen=True, kw_only=True)
class OpenMeteoSensorDescription(SensorEntityDescription):
    """Extended description with a custom value function."""
    value_fn: Callable[[dict[str, Any]], Any]


SENSOR_TYPES: dict[str, OpenMeteoSensorDescription] = {
    "temperature": OpenMeteoSensorDescription(
        key="temperature", name="Temperatura",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        icon="mdi:thermometer", device_class="temperature", state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.get("current_weather", {}) or {}).get("temperature"),
    ),
    "humidity": OpenMeteoSensorDescription(
        key="humidity", name="Wilgotność",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:water-percent", device_class="humidity", state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _hourly_at_now(d, "relative_humidity_2m"),
    ),
    "apparent_temperature": OpenMeteoSensorDescription(
        key="apparent_temperature", name="Temperatura odczuwalna",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        icon="mdi:thermometer-alert", device_class="temperature", state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _hourly_at_now(d, "apparent_temperature"),
    ),
    "precipitation_probability": OpenMeteoSensorDescription(
        key="precipitation_probability", name="Prawdopodobieństwo opadów",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:umbrella-outline", state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _hourly_at_now(d, "precipitation_probability"),
    ),
    "precipitation_last_3h": OpenMeteoSensorDescription(
        key="precipitation_last_3h", name="Opad (ostatnie 3h)",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        icon="mdi:weather-pouring", device_class="precipitation", state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _hourly_sum_last_n(d, ["precipitation", "snowfall"], 3),
    ),
    "wind_speed": OpenMeteoSensorDescription(
        key="wind_speed", name="Prędkość wiatru",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        icon="mdi:weather-windy", state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.get("current_weather", {}) or {}).get("windspeed"),
    ),
    "wind_gust": OpenMeteoSensorDescription(
        key="wind_gust", name="Porywy wiatru",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        icon="mdi:weather-windy-variant", state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _hourly_at_now(d, "wind_gusts_10m"),
    ),
    "wind_bearing": OpenMeteoSensorDescription(
        key="wind_bearing", name="Kierunek wiatru",
        native_unit_of_measurement=DEGREE,
        icon="mdi:compass", state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.get("current_weather", {}) or {}).get("winddirection"),
    ),
    "pressure": OpenMeteoSensorDescription(
        key="pressure", name="Ciśnienie",
        native_unit_of_measurement=UnitOfPressure.HPA,
        icon="mdi:gauge", device_class="pressure", state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _hourly_at_now(d, "pressure_msl"),
    ),
    "visibility": OpenMeteoSensorDescription(
        key="visibility", name="Widzialność",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        icon="mdi:eye", state_class=SensorStateClass.MEASUREMENT,
        value_fn=_visibility_km,
    ),
    "dew_point": OpenMeteoSensorDescription(
        key="dew_point", name="Punkt rosy",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        icon="mdi:water", device_class="temperature", state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.get("current", {}) or {}).get("dewpoint_2m") or _hourly_at_now(d, "dewpoint_2m"),
    ),
    "sunrise": OpenMeteoSensorDescription(
        key="sunrise", name="Wschód słońca",
        icon="mdi:weather-sunset-up", device_class="timestamp",
        value_fn=lambda d: _first_daily_dt(d, "sunrise"),
    ),
    "sunset": OpenMeteoSensorDescription(
        key="sunset", name="Zachód słońca",
        icon="mdi:weather-sunset-down", device_class="timestamp",
        value_fn=lambda d: _first_daily_dt(d, "sunset"),
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Open-Meteo sensor based on a config entry."""
    coordinator: OpenMeteoDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    entities = [
        OpenMeteoSensor(coordinator, config_entry, sensor_type)
        for sensor_type in SENSOR_TYPES
    ]
    entities.append(OpenMeteoUvIndexSensor(coordinator, config_entry))

    async_add_entities(entities, True)


class OpenMeteoSensor(CoordinatorEntity[OpenMeteoDataUpdateCoordinator], SensorEntity):
    """Representation of an Open-Meteo sensor."""

    entity_description: OpenMeteoSensorDescription

    def __init__(
        self,
        coordinator: OpenMeteoDataUpdateCoordinator,
        config_entry: ConfigEntry,
        sensor_type: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = SENSOR_TYPES[sensor_type]
        self._value_fn = self.entity_description.value_fn

        self._attr_unique_id = f"{config_entry.entry_id}:{sensor_type}"
        self._attr_suggested_object_id = OBJECT_ID_PL.get(sensor_type, sensor_type)
        self._attr_has_entity_name = True

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            name=config_entry.title,
            manufacturer="Open-Meteo",
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        try:
            val = self._value_fn(self.coordinator.data)
            # Walidacja, czy wartość jest prostym typem lub None
            if isinstance(val, (int, float, str, type(None), dt_util.dt.datetime)):
                 return val
            return str(val) # Ostateczny fallback
        except (IndexError, KeyError, TypeError, ValueError):
            return None

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self):
        return _extra_attrs(self.coordinator.data or {})


class OpenMeteoUvIndexSensor(CoordinatorEntity[OpenMeteoDataUpdateCoordinator], SensorEntity):
    """UV Index sensor for the current hour."""

    _attr_has_entity_name = True
    _attr_name = "Indeks UV"
    _attr_suggested_object_id = OBJECT_ID_PL["uv_index"]
    _attr_native_unit_of_measurement = "UV Index"
    _attr_icon = "mdi:weather-sunny-alert"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: OpenMeteoDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{config_entry.entry_id}:uv_index"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            name=config_entry.title,
            manufacturer="Open-Meteo",
        )

    @property
    def native_value(self):
        """Return the UV index (prefer current, else hourly@now)."""
        if not self.coordinator.data:
            return None
        uv_now = (self.coordinator.data.get("current") or {}).get("uv_index")
        if isinstance(uv_now, (int, float)):
            return round(uv_now, 2)
        uv_hourly = _hourly_at_now(self.coordinator.data, "uv_index")
        return round(uv_hourly, 2) if isinstance(uv_hourly, (int, float)) else None

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self):
        return _extra_attrs(self.coordinator.data or {})