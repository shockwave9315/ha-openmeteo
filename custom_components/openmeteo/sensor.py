"""Sensor platform for Open-Meteo."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    DEGREE,
    PERCENTAGE,
    UnitOfLength,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfPrecipitationDepth,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import (
    ATTRIBUTION,
    DOMAIN,
    CONF_SHOW_PLACE_NAME,
    DEFAULT_SHOW_PLACE_NAME,
    CONF_EXTRA_SENSORS,
    DEFAULT_EXTRA_SENSORS,
)
from .coordinator import OpenMeteoDataUpdateCoordinator


def _first_hourly(data: dict[str, Any], key: str) -> Any:
    arr = data.get("hourly", {}).get(key)
    if isinstance(arr, list) and arr:
        return arr[0]
    return None


def _visibility_km(data: dict[str, Any]) -> Any:
    v = _first_hourly(data, "visibility")
    return v / 1000 if isinstance(v, (int, float)) else None


def _uv_index_value(data: dict[str, Any]) -> Any:
    hourly = data.get("hourly") or {}
    times = hourly.get("time") or []
    values = hourly.get("uv_index") or []
    if not times or not values:
        return None
    tz = dt_util.get_time_zone(data.get("timezone")) or dt_util.UTC
    now = dt_util.now(tz).replace(minute=0, second=0, microsecond=0)
    for t_str, val in zip(times, values):
        dt = dt_util.parse_datetime(t_str)
        if dt and dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        if dt == now and isinstance(val, (int, float)):
            return round(val, 2)
    return None


@dataclass
class SensorSpec:
    key: str
    base_name: str
    unit: str | None
    device_class: SensorDeviceClass | str | None
    icon: str | None
    value_fn: Callable[[dict[str, Any]], Any] | None
    state_class: SensorStateClass | None = SensorStateClass.MEASUREMENT


BASE_SENSOR_KEYS = [
    "pressure",
    "uv_index",
    "wind_direction",
    "wind_gust",
    "wind_speed",
    "dew_point",
    "precipitation",
    "precipitation_probability",
    "temperature",
    "apparent_temperature",
    "visibility",
    "humidity",
    "sunrise",
    "sunset",
    "location",
]

EXTRA_SENSOR_KEYS = ["cloud_cover", "solar_radiation", "snow_depth"]


SENSOR_SPECS: dict[str, SensorSpec] = {
    "pressure": SensorSpec(
        "pressure",
        "Ciśnienie",
        UnitOfPressure.HPA,
        SensorDeviceClass.PRESSURE,
        "mdi:gauge",
        lambda d: _first_hourly(d, "pressure_msl"),
    ),
    "uv_index": SensorSpec(
        "uv_index",
        "Indeks UV",
        None,
        None,
        "mdi:weather-sunny-alert",
        _uv_index_value,
    ),
    "wind_direction": SensorSpec(
        "wind_direction",
        "Kierunek wiatru",
        DEGREE,
        None,
        "mdi:compass",
        lambda d: d.get("current_weather", {}).get("winddirection"),
    ),
    "wind_gust": SensorSpec(
        "wind_gust",
        "Porywy wiatru",
        UnitOfSpeed.KILOMETERS_PER_HOUR,
        None,
        "mdi:weather-windy",
        lambda d: _first_hourly(d, "wind_gusts_10m"),
    ),
    "wind_speed": SensorSpec(
        "wind_speed",
        "Prędkość wiatru",
        UnitOfSpeed.KILOMETERS_PER_HOUR,
        None,
        "mdi:weather-windy-variant",
        lambda d: d.get("current_weather", {}).get("windspeed"),
    ),
    "dew_point": SensorSpec(
        "dew_point",
        "Punkt rosy",
        UnitOfTemperature.CELSIUS,
        SensorDeviceClass.TEMPERATURE,
        "mdi:water-percent",
        lambda d: d.get("current", {}).get("dewpoint_2m")
        or _first_hourly(d, "dewpoint_2m"),
    ),
    "precipitation": SensorSpec(
        "precipitation",
        "Suma opadów",
        UnitOfPrecipitationDepth.MILLIMETERS,
        SensorDeviceClass.PRECIPITATION,
        "mdi:weather-rainy",
        lambda d: _first_hourly(d, "precipitation"),
    ),
    "precipitation_probability": SensorSpec(
        "precipitation_probability",
        "Prawdopodobieństwo opadów",
        PERCENTAGE,
        None,
        "mdi:weather-pouring",
        lambda d: _first_hourly(d, "precipitation_probability"),
    ),
    "temperature": SensorSpec(
        "temperature",
        "Temperatura",
        UnitOfTemperature.CELSIUS,
        SensorDeviceClass.TEMPERATURE,
        "mdi:thermometer",
        lambda d: d.get("current_weather", {}).get("temperature"),
    ),
    "apparent_temperature": SensorSpec(
        "apparent_temperature",
        "Temperatura odczuwalna",
        UnitOfTemperature.CELSIUS,
        SensorDeviceClass.TEMPERATURE,
        "mdi:thermometer-lines",
        lambda d: _first_hourly(d, "apparent_temperature"),
    ),
    "visibility": SensorSpec(
        "visibility",
        "Widzialność",
        UnitOfLength.KILOMETERS,
        None,
        "mdi:eye",
        _visibility_km,
    ),
    "humidity": SensorSpec(
        "humidity",
        "Wilgotność",
        PERCENTAGE,
        SensorDeviceClass.HUMIDITY,
        "mdi:water-percent",
        lambda d: _first_hourly(d, "relative_humidity_2m"),
    ),
    "sunrise": SensorSpec(
        "sunrise",
        "Wschód słońca",
        None,
        SensorDeviceClass.TIMESTAMP,
        "mdi:weather-sunset-up",
        lambda d: (d.get("daily", {}).get("sunrise") or [None])[0],
        state_class=None,
    ),
    "sunset": SensorSpec(
        "sunset",
        "Zachód słońca",
        None,
        SensorDeviceClass.TIMESTAMP,
        "mdi:weather-sunset-down",
        lambda d: (d.get("daily", {}).get("sunset") or [None])[0],
        state_class=None,
    ),
    "location": SensorSpec(
        "location",
        "Lokalizacja",
        None,
        None,
        "mdi:map-marker",
        None,
        state_class=None,
    ),
    "cloud_cover": SensorSpec(
        "cloud_cover",
        "Zachmurzenie",
        PERCENTAGE,
        None,
        "mdi:weather-cloudy",
        lambda d: _first_hourly(d, "cloud_cover"),
    ),
    "solar_radiation": SensorSpec(
        "solar_radiation",
        "Promieniowanie słoneczne",
        "W/m²",
        None,
        "mdi:weather-sunny",
        lambda d: _first_hourly(d, "shortwave_radiation"),
    ),
    "snow_depth": SensorSpec(
        "snow_depth",
        "Pokrywa śnieżna",
        "cm",
        None,
        "mdi:snowflake",
        lambda d: _first_hourly(d, "snow_depth"),
    ),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Open-Meteo sensors."""
    coordinator = hass.data[DOMAIN]["entries"][entry.entry_id]["coordinator"]
    opts = entry.options or {}
    keys = list(BASE_SENSOR_KEYS)
    if opts.get(CONF_EXTRA_SENSORS, DEFAULT_EXTRA_SENSORS):
        keys += EXTRA_SENSOR_KEYS

    registry = er.async_get(hass)

    def ensure_sensor_object_id(config_entry: ConfigEntry, key: str) -> str:
        base = f"open_meteo_{key}"
        suggested = base
        i = 2
        while registry.async_get_entity_id(
            "sensor", DOMAIN, f"{config_entry.entry_id}_{key}"
        ) or registry.async_get(f"sensor.{suggested}"):
            suggested = f"open_meteo_{i}_{key}"
            i += 1
        if not registry.async_get_entity_id(
            "sensor", DOMAIN, f"{config_entry.entry_id}_{key}"
        ):
            registry.async_get_or_create(
                domain="sensor",
                platform=DOMAIN,
                unique_id=f"{config_entry.entry_id}_{key}",
                suggested_object_id=suggested,
                config_entry=config_entry,
            )
        return suggested

    entities = [
        OpenMeteoSensor(
            coordinator,
            entry,
            key,
            ensure_sensor_object_id(entry, key),
        )
        for key in keys
    ]
    async_add_entities(entities)


class OpenMeteoSensor(CoordinatorEntity, SensorEntity):
    """Representation of an Open-Meteo sensor."""

    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: OpenMeteoDataUpdateCoordinator,
        entry: ConfigEntry,
        key: str,
        suggested_object_id: str,
    ) -> None:
        super().__init__(coordinator)
        self._config_entry = entry
        self._spec = SENSOR_SPECS[key]
        self._key = key
        self._base_name = self._spec.base_name
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_suggested_object_id = suggested_object_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer="Open-Meteo",
        )
        self._attr_icon = self._spec.icon
        if self._spec.state_class is not None:
            self._attr_state_class = self._spec.state_class
        else:
            self._attr_state_class = None
        if key in EXTRA_SENSOR_KEYS:
            self._attr_entity_registry_enabled_default = False

    @property
    def name(self) -> str:
        show_place = self._config_entry.options.get(
            CONF_SHOW_PLACE_NAME, DEFAULT_SHOW_PLACE_NAME
        )
        if show_place and self.coordinator.location_name:
            return f"{self._base_name} — {self.coordinator.location_name}"
        return self._base_name

    @property
    def native_value(self) -> Any:
        if not self.coordinator.data:
            return None
        if self._key == "location":
            lat = self.coordinator.latitude
            lon = self.coordinator.longitude
            if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                return f"{lat:.7f}, {lon:.7f}"
            return None
        if self._key in ("sunrise", "sunset"):
            val = self._spec.value_fn(self.coordinator.data) if self._spec.value_fn else None
            if not val:
                sun = self.hass.states.get("sun.sun")
                attr = "next_rising" if self._key == "sunrise" else "next_setting"
                if sun:
                    val = sun.attributes.get(attr)
            if isinstance(val, str):
                dt = dt_util.parse_datetime(val)
            else:
                dt = val
            if not dt:
                return None
            if dt.tzinfo is None:
                tz = dt_util.get_time_zone(self.hass.config.time_zone) or dt_util.UTC
                dt = dt.replace(tzinfo=tz)
            return dt_util.as_local(dt)
        val = self._spec.value_fn(self.coordinator.data) if self._spec.value_fn else None
        return round(val, 2) if isinstance(val, (int, float)) else val

    @property
    def native_unit_of_measurement(self) -> str | None:
        return self._spec.unit

    @property
    def device_class(self) -> SensorDeviceClass | str | None:
        return self._spec.device_class

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        store = (
            self.hass.data.get(DOMAIN, {})
            .get("entries", {})
            .get(self._config_entry.entry_id, {})
        )
        return {
            "location_name": self.coordinator.location_name,
            "latitude": self.coordinator.latitude,
            "longitude": self.coordinator.longitude,
            "geocode_provider": store.get("geocode_provider"),
            "geocode_last_success": store.get("geocode_last_success"),
            "attribution": ATTRIBUTION,
        }

    @callback
    def _handle_place_update(self) -> None:
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        signal = f"openmeteo_place_updated_{self._config_entry.entry_id}"
        self.async_on_remove(
            async_dispatcher_connect(self.hass, signal, self._handle_place_update)
        )
        self._handle_place_update()

