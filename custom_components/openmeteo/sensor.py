# SPDX-License-Identifier: Apache-2.0
# SPDX-License-Identifier: Apache-2.0
"""Sensor platform for Open-Meteo."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping

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
    UnitOfLength,
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify
from homeassistant.util import dt as dt_util

from .coordinator import OpenMeteoDataUpdateCoordinator
from .const import (
    DOMAIN,
    ATTRIBUTION,
    CONF_USE_PLACE_AS_DEVICE_NAME,
    DEFAULT_USE_PLACE_AS_DEVICE_NAME,
)
from .helpers import get_place_title




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


def _extra_attrs(data: dict) -> dict:
    loc = (data or {}).get("location") or {}
    return {
        "attribution": ATTRIBUTION,
        "latitude": loc.get("latitude"),
        "longitude": loc.get("longitude"),
        "model": data.get("model"),
        "source": "open-meteo",
        "last_update": (data.get("current_weather") or {}).get("time"),
    }


@dataclass(kw_only=True)
class OpenMeteoSensorDescription(SensorEntityDescription):
    key: str
    value_fn: Callable[[dict[str, Any]], Any]
    device_class: SensorDeviceClass | str | None = None
    entity_category: EntityCategory | None = None
    entity_registry_enabled_default: bool = True
    entity_registry_visible_default: bool = True
    force_update: bool = False
    icon: str | None = None
    has_entity_name: bool = False
    name: str | None = None
    translation_key: str | None = None
    translation_placeholders: Mapping[str, str] | None = None
    unit_of_measurement: str | None = None
    last_reset: datetime | None = None
    native_unit_of_measurement: str | None = None
    options: list[str] | None = None
    state_class: SensorStateClass | str | None = None
    suggested_display_precision: int | None = None
    suggested_unit_of_measurement: str | None = None
    attr_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None


SENSOR_TYPES: dict[str, OpenMeteoSensorDescription] = {
    "temperature": OpenMeteoSensorDescription(
        key="temperature",
        name="Temperatura",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        icon="mdi:thermometer",
        device_class="temperature",
        value_fn=lambda d: d.get("current_weather", {}).get("temperature"),
    ),
    "humidity": OpenMeteoSensorDescription(
        key="humidity",
        name="Wilgotność",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:water-percent",
        device_class="humidity",
        value_fn=lambda d: _first_hourly(d, "relative_humidity_2m"),
    ),
    "apparent_temperature": OpenMeteoSensorDescription(
        key="apparent_temperature",
        name="Temperatura odczuwalna",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        icon="mdi:thermometer-alert",
        device_class="temperature",
        value_fn=lambda d: _first_hourly(d, "apparent_temperature"),
    ),
    "precipitation_probability": OpenMeteoSensorDescription(
        key="precipitation_probability",
        name="Prawdopodobieństwo opadów",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:weather-pouring",
        device_class=None,
        value_fn=lambda d: _first_hourly(d, "precipitation_probability"),
    ),
    "precipitation_total": OpenMeteoSensorDescription(
        key="precipitation_total",
        name="Suma opadów",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        icon="mdi:cup-water",
        device_class="precipitation",
        value_fn=lambda d: (_first_hourly(d, "precipitation") or 0)
        + (_first_hourly(d, "snowfall") or 0),
    ),
    "wind_speed": OpenMeteoSensorDescription(
        key="wind_speed",
        name="Prędkość wiatru",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        icon="mdi:weather-windy",
        device_class=None,
        value_fn=lambda d: d.get("current_weather", {}).get("windspeed"),
    ),
    "wind_gust": OpenMeteoSensorDescription(
        key="wind_gust",
        name="Porywy wiatru",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        icon="mdi:weather-windy-variant",
        device_class=None,
        value_fn=lambda d: _first_hourly(d, "wind_gusts_10m"),
    ),
    "wind_bearing": OpenMeteoSensorDescription(
        key="wind_bearing",
        name="Kierunek wiatru",
        native_unit_of_measurement=DEGREE,
        icon="mdi:compass",
        device_class=None,
        value_fn=lambda d: d.get("current_weather", {}).get("winddirection"),
    ),
    "pressure": OpenMeteoSensorDescription(
        key="pressure",
        name="Ciśnienie",
        native_unit_of_measurement=UnitOfPressure.HPA,
        icon="mdi:gauge",
        device_class="pressure",
        value_fn=lambda d: _first_hourly(d, "pressure_msl"),
    ),
    "visibility": OpenMeteoSensorDescription(
        key="visibility",
        name="Widzialność",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        icon="mdi:eye",
        device_class=None,
        value_fn=_visibility_km,
    ),
    "dew_point": OpenMeteoSensorDescription(
        key="dew_point",
        name="Punkt rosy",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        icon="mdi:water",
        device_class="temperature",
        value_fn=lambda d: d.get("current", {}).get("dewpoint_2m")
        or _first_hourly(d, "dewpoint_2m"),
    ),
    "location": OpenMeteoSensorDescription(
        key="location",
        name="Lokalizacja",
        native_unit_of_measurement=None,
        icon="mdi:map-marker",
        device_class=None,
        value_fn=lambda d: (
            f"{d.get('location', {}).get('latitude')}, {d.get('location', {}).get('longitude')}"
            if d.get("location", {}).get("latitude") is not None
            and d.get("location", {}).get("longitude") is not None
            else None
        ),
    ),
    "sunrise": OpenMeteoSensorDescription(
        key="sunrise",
        name="Wschód słońca",
        native_unit_of_measurement=None,
        icon="mdi:weather-sunset-up",
        device_class="timestamp",
        value_fn=lambda d: _first_daily_dt(d, "sunrise"),
    ),
    "sunset": OpenMeteoSensorDescription(
        key="sunset",
        name="Zachód słońca",
        native_unit_of_measurement=None,
        icon="mdi:weather-sunset-down",
        device_class="timestamp",
        value_fn=lambda d: _first_daily_dt(d, "sunset"),
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN]["entries"][config_entry.entry_id]["coordinator"]
    entities = [OpenMeteoSensor(coordinator, config_entry, k) for k in SENSOR_TYPES]
    entities.append(OpenMeteoUvIndexSensor(coordinator, config_entry))
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
        self._config_entry = config_entry
        self.entity_description = SENSOR_TYPES[sensor_type]
        self._value_fn = self.entity_description.value_fn
        data = {**config_entry.data, **config_entry.options}
        self._use_place = data.get(
            CONF_USE_PLACE_AS_DEVICE_NAME, DEFAULT_USE_PLACE_AS_DEVICE_NAME
        )
        self._attr_has_entity_name = True
        self._attr_name = None
        if self._use_place:
            place_slug = slugify(get_place_title(coordinator.hass, config_entry))
            if place_slug:
                self._attr_suggested_object_id = f"{place_slug}_{sensor_type}"
        self._attr_unique_id = f"{config_entry.entry_id}-{sensor_type}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            manufacturer="Open-Meteo",
        )

    @property
    def native_value(self):
        if not self.coordinator.data:
            return None
        value = self._value_fn(self.coordinator.data)
        return round(value, 2) if isinstance(value, (int, float)) else value

    @property
    def native_unit_of_measurement(self):
        return self.entity_description.native_unit_of_measurement

    @property
    def icon(self):
        return self.entity_description.icon

    @property
    def device_class(self):
        return self.entity_description.device_class

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self):
        attrs = _extra_attrs(self.coordinator.data or {})
        try:
            store = (
                self.hass.data.get(DOMAIN, {})
                .get("entries", {})
                .get(self._config_entry.entry_id, {})
            )
            src = store.get("src")
            if src:
                attrs["om_source"] = src

            lat = store.get("lat", attrs.get("latitude"))
            lon = store.get("lon", attrs.get("longitude"))
            if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                attrs["om_coords_used"] = f"{float(lat):.6f},{float(lon):.6f}"

            place = (self.coordinator.data or {}).get("location_name") or store.get("place")
            if place:
                attrs["om_place_name"] = place
        except Exception:
            pass
        return attrs

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
        store = (
            self.hass.data.setdefault(DOMAIN, {})
            .setdefault("entries", {})
            .setdefault(self._config_entry.entry_id, {})
        )
        store.setdefault("entities", []).append(self)

    async def async_will_remove_from_hass(self) -> None:
        store = (
            self.hass.data.get(DOMAIN, {})
            .get("entries", {})
            .get(self._config_entry.entry_id)
        )
        if store and self in store.get("entities", []):
            store["entities"].remove(self)
        await super().async_will_remove_from_hass()


class OpenMeteoUvIndexSensor(CoordinatorEntity, SensorEntity):
    """UV Index sensor for the current hour."""

    def __init__(
        self,
        coordinator: OpenMeteoDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._config_entry = config_entry
        data = {**config_entry.data, **config_entry.options}
        self._use_place = data.get(
            CONF_USE_PLACE_AS_DEVICE_NAME, DEFAULT_USE_PLACE_AS_DEVICE_NAME
        )
        self._attr_unique_id = f"{config_entry.entry_id}-uv_index"
        self._attr_native_unit_of_measurement = "UV Index"
        self._attr_icon = "mdi:weather-sunny-alert"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_has_entity_name = True
        self._attr_name = None
        self._attr_translation_key = "uv_index"
        if self._use_place:
            place_slug = slugify(get_place_title(coordinator.hass, config_entry))
            if place_slug:
                self._attr_suggested_object_id = f"{place_slug}_uv_index"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            manufacturer="Open-Meteo",
        )

    @property
    def native_value(self):
        data = self.coordinator.data or {}
        hourly = data.get("hourly") or {}
        times = hourly.get("time") or []
        values = hourly.get("uv_index") or []
        if not times or not values:
            return None
        tz = dt_util.get_time_zone(data.get("timezone")) or dt_util.UTC
        now = dt_util.now(tz).replace(minute=0, second=0, microsecond=0)
        for t_str, val in zip(times, values):
            try:
                dt = dt_util.parse_datetime(t_str)
                if dt and dt.tzinfo is None:
                    dt = dt.replace(tzinfo=tz)
                if dt == now and isinstance(val, (int, float)):
                    return round(val, 2)
            except Exception:
                continue
        return None

    @property
    def extra_state_attributes(self):
        attrs = _extra_attrs(self.coordinator.data or {})
        try:
            store = (
                self.hass.data.get(DOMAIN, {})
                .get("entries", {})
                .get(self._config_entry.entry_id, {})
            )
            src = store.get("src")
            if src:
                attrs["om_source"] = src

            lat = store.get("lat", attrs.get("latitude"))
            lon = store.get("lon", attrs.get("longitude"))
            if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                attrs["om_coords_used"] = f"{float(lat):.6f},{float(lon):.6f}"

            place = (self.coordinator.data or {}).get("location_name") or store.get("place")
            if place:
                attrs["om_place_name"] = place
        except Exception:
            pass
        return attrs

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        signal = f"openmeteo_place_updated_{self._config_entry.entry_id}"
        self.async_on_remove(
            async_dispatcher_connect(self.hass, signal, self._handle_place_update)
        )
        self._handle_place_update()
        store = (
            self.hass.data.setdefault(DOMAIN, {})
            .setdefault("entries", {})
            .setdefault(self._config_entry.entry_id, {})
        )
        store.setdefault("entities", []).append(self)

    async def async_will_remove_from_hass(self) -> None:
        store = (
            self.hass.data.get(DOMAIN, {})
            .get("entries", {})
            .get(self._config_entry.entry_id)
        )
        if store and self in store.get("entities", []):
            store["entities"].remove(self)
        await super().async_will_remove_from_hass()

    @callback
    def _handle_place_update(self) -> None:
        self.async_write_ha_state()
