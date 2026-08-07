"""Sensor platform for Open-Meteo v2."""
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    DEGREE,
    PERCENTAGE,
    UV_INDEX,
    UnitOfLength,
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfRatio,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    AQ_HOURLY_KEYS,
    ATTRIBUTION,
    CONF_ENABLED_AQ_SENSORS,
    CONF_ENABLED_SENSORS,
    CONF_ENABLED_WEATHER_SENSORS,
    DOMAIN,
)
from .coordinator import OpenMeteoDataUpdateCoordinator
from .helpers import aq_hour_value, hourly_at_now, hourly_sum_last_n
from .identity import sensor_object_id, sensor_unique_id
from .runtime import get_entry_coordinator, get_runtime_data

CO_MOLAR_MASS = 28.01
CO_UGM3_TO_PPM_FACTOR = 24.45 / (CO_MOLAR_MASS * 1000)

SENSOR_SLUGS: dict[str, str] = {
    "temperature": "temperatura",
    "apparent_temperature": "temperatura_odczuwalna",
    "humidity": "wilgotnosc",
    "pressure": "cisnienie",
    "dew_point": "punkt_rosy",
    "wind_speed": "wiatr",
    "wind_gust": "porywy_wiatru",
    "wind_bearing": "kierunek_wiatru",
    "precipitation_sum": "opad_biezaca_godzina",
    "rain_current_hour": "deszcz_biezaca_godzina",
    "snow_current_hour": "snieg_biezaca_godzina",
    "precipitation_daily_sum": "suma_opadow_dzienna",
    "precipitation_last_3h": "opad_ostatnie_3h",
    "precipitation_probability": "prawdopodobienstwo_opadow",
    "visibility": "widocznosc",
    "sunrise": "wschod_slonca",
    "sunset": "zachod_slonca",
    "uv_index": "indeks_uv",
    "uv_index_max": "maksymalny_indeks_uv",
    "location": "lokalizacja",
    "pm2_5": "pm2_5",
    "pm10": "pm10",
    "co": "tlenek_wegla",
    "no2": "dwutlenek_azotu",
    "so2": "dwutlenek_siarki",
    "o3": "ozon",
    "aqi_us": "us_aqi",
    "aqi_eu": "european_aqi",
}


def _current(data: Mapping[str, Any], key: str) -> Any:
    current = data.get("current")
    return current.get(key) if isinstance(current, Mapping) else None


def _daily_first(data: Mapping[str, Any], key: str) -> Any:
    daily = data.get("daily")
    if not isinstance(daily, Mapping):
        return None
    values = daily.get(key)
    return values[0] if isinstance(values, list) and values else None


def _timestamp(data: Mapping[str, Any], key: str) -> datetime | None:
    raw = _daily_first(data, key)
    if isinstance(raw, datetime):
        value = raw
    elif isinstance(raw, str):
        value = dt_util.parse_datetime(raw)
    else:
        return None
    if value is None:
        return None
    if value.tzinfo is None:
        timezone = dt_util.get_time_zone(str(data.get("timezone") or "")) or dt_util.UTC
        value = value.replace(tzinfo=timezone)
    return value


def _co_ppm(data: Mapping[str, Any]) -> float | None:
    raw = aq_hour_value(data, AQ_HOURLY_KEYS["co"])
    try:
        return round(float(raw) * CO_UGM3_TO_PPM_FACTOR, 3) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _aq_value(key: str) -> Callable[[Mapping[str, Any]], Any]:
    def _value(data: Mapping[str, Any]) -> Any:
        raw = aq_hour_value(data, AQ_HOURLY_KEYS[key])
        if raw is None:
            return None
        if key in ("aqi_us", "aqi_eu"):
            try:
                return round(float(raw))
            except (TypeError, ValueError):
                return None
        return raw

    return _value


def _location_attributes(data: Mapping[str, Any]) -> dict[str, Any]:
    location = data.get("location")
    if not isinstance(location, Mapping):
        location = {}
    return {
        "latitude": location.get("latitude"),
        "longitude": location.get("longitude"),
        "last_location_update": data.get("last_location_update"),
        "mode": data.get("mode"),
    }


@dataclass(frozen=True, kw_only=True)
class OpenMeteoSensorDescription(SensorEntityDescription):
    """Sensor metadata plus a pure value extractor."""

    value_fn: Callable[[Mapping[str, Any]], Any]
    attributes_fn: Callable[[Mapping[str, Any]], dict[str, Any]] | None = None
    air_quality: bool = False


SENSORS: dict[str, OpenMeteoSensorDescription] = {
    "temperature": OpenMeteoSensorDescription(
        key="temperature",
        name="Temperatura",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
        value_fn=lambda d: _current(d, "temperature_2m"),
    ),
    "apparent_temperature": OpenMeteoSensorDescription(
        key="apparent_temperature",
        name="Temperatura odczuwalna",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-alert",
        value_fn=lambda d: _current(d, "apparent_temperature")
        if _current(d, "apparent_temperature") is not None
        else hourly_at_now(d, "apparent_temperature"),
    ),
    "humidity": OpenMeteoSensorDescription(
        key="humidity",
        name="Wilgotność",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-percent",
        value_fn=lambda d: _current(d, "relative_humidity_2m")
        if _current(d, "relative_humidity_2m") is not None
        else hourly_at_now(d, "relative_humidity_2m"),
    ),
    "pressure": OpenMeteoSensorDescription(
        key="pressure",
        name="Ciśnienie",
        native_unit_of_measurement=UnitOfPressure.HPA,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gauge",
        value_fn=lambda d: _current(d, "pressure_msl")
        if _current(d, "pressure_msl") is not None
        else hourly_at_now(d, "pressure_msl"),
    ),
    "dew_point": OpenMeteoSensorDescription(
        key="dew_point",
        name="Punkt rosy",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water",
        value_fn=lambda d: hourly_at_now(d, "dew_point_2m"),
    ),
    "wind_speed": OpenMeteoSensorDescription(
        key="wind_speed",
        name="Prędkość wiatru",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-windy",
        value_fn=lambda d: _current(d, "wind_speed_10m"),
    ),
    "wind_gust": OpenMeteoSensorDescription(
        key="wind_gust",
        name="Porywy wiatru",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-windy-variant",
        value_fn=lambda d: _current(d, "wind_gusts_10m"),
    ),
    "wind_bearing": OpenMeteoSensorDescription(
        key="wind_bearing",
        name="Kierunek wiatru",
        native_unit_of_measurement=DEGREE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:compass",
        value_fn=lambda d: _current(d, "wind_direction_10m"),
    ),
    "precipitation_sum": OpenMeteoSensorDescription(
        key="precipitation_sum",
        name="Opad łączny (bieżąca godzina)",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:cup-water",
        value_fn=lambda d: hourly_at_now(d, "precipitation") or 0,
    ),
    "rain_current_hour": OpenMeteoSensorDescription(
        key="rain_current_hour",
        name="Deszcz (bieżąca godzina)",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-rainy",
        value_fn=lambda d: hourly_at_now(d, "rain") or 0,
    ),
    "snow_current_hour": OpenMeteoSensorDescription(
        key="snow_current_hour",
        name="Śnieg (bieżąca godzina)",
        native_unit_of_measurement=UnitOfLength.CENTIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-snowy",
        value_fn=lambda d: hourly_at_now(d, "snowfall") or 0,
    ),
    "precipitation_daily_sum": OpenMeteoSensorDescription(
        key="precipitation_daily_sum",
        name="Suma opadów (dzienna)",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.TOTAL,
        icon="mdi:weather-pouring",
        value_fn=lambda d: _daily_first(d, "precipitation_sum"),
    ),
    "precipitation_last_3h": OpenMeteoSensorDescription(
        key="precipitation_last_3h",
        name="Opad (ostatnie 3h)",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-pouring",
        value_fn=lambda d: hourly_sum_last_n(d, ["precipitation"], 3),
    ),
    "precipitation_probability": OpenMeteoSensorDescription(
        key="precipitation_probability",
        name="Prawdopodobieństwo opadów",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:umbrella-outline",
        value_fn=lambda d: hourly_at_now(d, "precipitation_probability"),
    ),
    "visibility": OpenMeteoSensorDescription(
        key="visibility",
        name="Widzialność",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:eye",
        value_fn=lambda d: (
            round(float(value) / 1000, 2)
            if (value := hourly_at_now(d, "visibility")) is not None
            else None
        ),
    ),
    "sunrise": OpenMeteoSensorDescription(
        key="sunrise",
        name="Wschód słońca",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:weather-sunset-up",
        value_fn=lambda d: _timestamp(d, "sunrise"),
    ),
    "sunset": OpenMeteoSensorDescription(
        key="sunset",
        name="Zachód słońca",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:weather-sunset-down",
        value_fn=lambda d: _timestamp(d, "sunset"),
    ),
    "uv_index": OpenMeteoSensorDescription(
        key="uv_index",
        name="Indeks UV",
        native_unit_of_measurement=UV_INDEX,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-sunny-alert",
        value_fn=lambda d: hourly_at_now(d, "uv_index"),
    ),
    "uv_index_max": OpenMeteoSensorDescription(
        key="uv_index_max",
        name="Maksymalny indeks UV",
        native_unit_of_measurement=UV_INDEX,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-sunny-alert",
        value_fn=lambda d: _daily_first(d, "uv_index_max"),
    ),
    "location": OpenMeteoSensorDescription(
        key="location",
        name="Lokalizacja",
        icon="mdi:map-marker",
        value_fn=lambda d: d.get("location_name"),
        attributes_fn=_location_attributes,
    ),
    "pm2_5": OpenMeteoSensorDescription(
        key="pm2_5",
        name="PM2.5",
        native_unit_of_measurement="µg/m³",
        device_class=SensorDeviceClass.PM25,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:blur",
        value_fn=_aq_value("pm2_5"),
        air_quality=True,
    ),
    "pm10": OpenMeteoSensorDescription(
        key="pm10",
        name="PM10",
        native_unit_of_measurement="µg/m³",
        device_class=SensorDeviceClass.PM10,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:blur",
        value_fn=_aq_value("pm10"),
        air_quality=True,
    ),
    "co": OpenMeteoSensorDescription(
        key="co",
        name="Tlenek węgla",
        native_unit_of_measurement=UnitOfRatio.PARTS_PER_MILLION,
        device_class=SensorDeviceClass.CO,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:molecule",
        value_fn=_co_ppm,
        air_quality=True,
    ),
    "no2": OpenMeteoSensorDescription(
        key="no2",
        name="Dwutlenek azotu",
        native_unit_of_measurement="µg/m³",
        device_class=SensorDeviceClass.NITROGEN_DIOXIDE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:molecule",
        value_fn=_aq_value("no2"),
        air_quality=True,
    ),
    "so2": OpenMeteoSensorDescription(
        key="so2",
        name="Dwutlenek siarki",
        native_unit_of_measurement="µg/m³",
        device_class=SensorDeviceClass.SULPHUR_DIOXIDE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:molecule",
        value_fn=_aq_value("so2"),
        air_quality=True,
    ),
    "o3": OpenMeteoSensorDescription(
        key="o3",
        name="Ozon",
        native_unit_of_measurement="µg/m³",
        device_class=SensorDeviceClass.OZONE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:molecule",
        value_fn=_aq_value("o3"),
        air_quality=True,
    ),
    "aqi_us": OpenMeteoSensorDescription(
        key="aqi_us",
        name="US AQI",
        device_class=SensorDeviceClass.AQI,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gauge",
        value_fn=_aq_value("aqi_us"),
        air_quality=True,
    ),
    "aqi_eu": OpenMeteoSensorDescription(
        key="aqi_eu",
        name="European AQI",
        device_class=SensorDeviceClass.AQI,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gauge",
        value_fn=_aq_value("aqi_eu"),
        air_quality=True,
    ),
}

WEATHER_KEYS = [key for key, description in SENSORS.items() if not description.air_quality]
AQ_KEYS = [key for key, description in SENSORS.items() if description.air_quality]


def _configured_keys(entry: ConfigEntry) -> list[str]:
    merged = {**dict(entry.data or {}), **dict(entry.options or {})}
    weather = merged.get(CONF_ENABLED_WEATHER_SENSORS)
    air_quality = merged.get(CONF_ENABLED_AQ_SENSORS)

    if not isinstance(weather, list) and not isinstance(air_quality, list):
        legacy = merged.get(CONF_ENABLED_SENSORS)
        if isinstance(legacy, list):
            return [key for key in legacy if key in SENSORS]
        return list(SENSORS)

    selected: list[str] = []
    selected.extend(key for key in (weather or []) if key in WEATHER_KEYS)
    selected.extend(key for key in (air_quality or []) if key in AQ_KEYS)
    return selected


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = get_entry_coordinator(hass, config_entry.entry_id)
    if not isinstance(coordinator, OpenMeteoDataUpdateCoordinator):
        return
    runtime = get_runtime_data(config_entry)
    source_key = runtime.source_key if runtime is not None else config_entry.entry_id[:8]
    async_add_entities(
        [
            OpenMeteoSensor(coordinator, config_entry, source_key, key)
            for key in _configured_keys(config_entry)
        ]
    )


class OpenMeteoSensor(CoordinatorEntity[OpenMeteoDataUpdateCoordinator], SensorEntity):
    """One stable sensor backed by the shared coordinator."""

    _attr_has_entity_name = False
    _attr_attribution = ATTRIBUTION

    def __init__(
        self,
        coordinator: OpenMeteoDataUpdateCoordinator,
        config_entry: ConfigEntry,
        source_key: str,
        sensor_key: str,
    ) -> None:
        super().__init__(coordinator)
        self._sensor_key = sensor_key
        self.entity_description = SENSORS[sensor_key]
        self._attr_unique_id = sensor_unique_id(
            config_entry.entry_id,
            sensor_key,
            air_quality=self.entity_description.air_quality,
        )
        self._attr_suggested_object_id = sensor_object_id(
            source_key, SENSOR_SLUGS[sensor_key]
        )
        self._attr_name = self.entity_description.name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            name=coordinator.location_name or config_entry.title or "Open-Meteo",
            manufacturer="Open-Meteo",
            model="Forecast API",
        )

    @property
    def native_value(self) -> Any:
        try:
            return self.entity_description.value_fn(self.coordinator.data or {})
        except (IndexError, KeyError, TypeError, ValueError):
            return None

    @property
    def available(self) -> bool:
        if not self.coordinator.last_update_success:
            return False
        if self.entity_description.air_quality:
            aq = (self.coordinator.data or {}).get("aq")
            return isinstance(aq, Mapping) and isinstance(aq.get("hourly"), Mapping)
        return True

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = {"attribution": ATTRIBUTION}
        if self.entity_description.attributes_fn is not None:
            attrs.update(self.entity_description.attributes_fn(self.coordinator.data or {}))
        return attrs
