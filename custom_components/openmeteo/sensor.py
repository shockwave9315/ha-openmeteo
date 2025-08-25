"""Sensor platform for Open-Meteo."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from dataclasses import dataclass
from typing import Any, Callable, Mapping
import re

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
from homeassistant.helpers.entity_registry import RegistryEntry
from homeassistant.util import dt as dt_util

from .const import (
    ATTRIBUTION,
    DOMAIN,
    CONF_SHOW_PLACE_NAME,
    DEFAULT_SHOW_PLACE_NAME,
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
    value_fn: Callable[[dict[str, Any]], Any]


SENSOR_SPECS: dict[str, SensorSpec] = {
    "temperature": SensorSpec(
        "temperature",
        "Temperatura",
        UnitOfTemperature.CELSIUS,
        SensorDeviceClass.TEMPERATURE,
        lambda d: d.get("current_weather", {}).get("temperature"),
    ),
    "apparent_temperature": SensorSpec(
        "apparent_temperature",
        "Temperatura odczuwalna",
        UnitOfTemperature.CELSIUS,
        SensorDeviceClass.TEMPERATURE,
        lambda d: _first_hourly(d, "apparent_temperature"),
    ),
    "humidity": SensorSpec(
        "humidity",
        "Wilgotność",
        PERCENTAGE,
        SensorDeviceClass.HUMIDITY,
        lambda d: _first_hourly(d, "relative_humidity_2m"),
    ),
    "pressure": SensorSpec(
        "pressure",
        "Ciśnienie",
        UnitOfPressure.HPA,
        SensorDeviceClass.PRESSURE,
        lambda d: _first_hourly(d, "pressure_msl"),
    ),
    "wind_speed": SensorSpec(
        "wind_speed",
        "Prędkość wiatru",
        UnitOfSpeed.KILOMETERS_PER_HOUR,
        None,
        lambda d: d.get("current_weather", {}).get("windspeed"),
    ),
    "wind_gust": SensorSpec(
        "wind_gust",
        "Porywy wiatru",
        UnitOfSpeed.KILOMETERS_PER_HOUR,
        None,
        lambda d: _first_hourly(d, "wind_gusts_10m"),
    ),
    "wind_direction": SensorSpec(
        "wind_direction",
        "Kierunek wiatru",
        DEGREE,
        None,
        lambda d: d.get("current_weather", {}).get("winddirection"),
    ),
    "precipitation": SensorSpec(
        "precipitation",
        "Suma opadów",
        UnitOfPrecipitationDepth.MILLIMETERS,
        None,
        lambda d: _first_hourly(d, "precipitation"),
    ),
    "cloud_cover": SensorSpec(
        "cloud_cover",
        "Zachmurzenie",
        PERCENTAGE,
        None,
        lambda d: _first_hourly(d, "cloud_cover"),
    ),
    "dew_point": SensorSpec(
        "dew_point",
        "Punkt rosy",
        UnitOfTemperature.CELSIUS,
        SensorDeviceClass.TEMPERATURE,
        lambda d: d.get("current", {}).get("dewpoint_2m")
        or _first_hourly(d, "dewpoint_2m"),
    ),
    "visibility": SensorSpec(
        "visibility",
        "Widzialność",
        UnitOfLength.KILOMETERS,
        None,
        _visibility_km,
    ),
    "solar_radiation": SensorSpec(
        "solar_radiation",
        "Promieniowanie słoneczne",
        "W/m²",
        None,
        lambda d: _first_hourly(d, "shortwave_radiation"),
    ),
    "snow_depth": SensorSpec(
        "snow_depth",
        "Pokrywa śnieżna",
        "cm",
        None,
        lambda d: _first_hourly(d, "snow_depth"),
    ),
    "uv_index": SensorSpec(
        "uv_index",
        "Indeks UV",
        None,
        None,
        _uv_index_value,
    ),
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Open-Meteo sensors."""
    coordinator = hass.data[DOMAIN]["entries"][entry.entry_id]["coordinator"]
    entities = [OpenMeteoSensor(coordinator, entry, key) for key in SENSOR_SPECS]
    async_add_entities(entities)


async def async_migrate_entry(hass: HomeAssistant, entry: RegistryEntry) -> dict | None:
    """Migrate legacy unique IDs."""
    if not (
        re.search(r"\d{1,3}[._-]\d+\D+\d{1,3}[._-]\d+", entry.unique_id)
        or entry.unique_id.endswith("_none")
        or entry.unique_id.endswith("-none")
    ):
        return None

    key = None
    for k, spec in SENSOR_SPECS.items():
        if entry.unique_id.endswith(k) or entry.original_name.startswith(spec.base_name):
            key = k
            break
    if not key:
        return None
    return {"new_unique_id": f"{entry.config_entry_id}_{key}"}


class OpenMeteoSensor(CoordinatorEntity, SensorEntity):
    """Representation of an Open-Meteo sensor."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator: OpenMeteoDataUpdateCoordinator,
        entry: ConfigEntry,
        key: str,
    ) -> None:
        super().__init__(coordinator)
        self._config_entry = entry
        self._spec = SENSOR_SPECS[key]
        self._key = key
        self._base_name = self._spec.base_name
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        suggested = f"open_meteo_{key}"
        if coordinator.hass.states.get(f"sensor.{suggested}"):
            suggested = f"open_meteo_2_{key}"
        self._attr_suggested_object_id = suggested
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer="Open-Meteo",
        )

    @property
    def name(self) -> str:
        show_place = self._config_entry.options.get(
            CONF_SHOW_PLACE_NAME, DEFAULT_SHOW_PLACE_NAME
        )
        store = (
            self.hass.data.get(DOMAIN, {})
            .get("entries", {})
            .get(self._config_entry.entry_id, {})
        )
        if show_place:
            loc = store.get("location_name")
            lat = store.get("lat")
            lon = store.get("lon")
            if loc:
                return f"{self._base_name} — {loc}"
            if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                return f"{self._base_name} — {lat:.5f},{lon:.5f}"
        return self._base_name

    @property
    def native_value(self) -> Any:
        if not self.coordinator.data:
            return None
        val = self._spec.value_fn(self.coordinator.data)
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
            "location_name": store.get("location_name"),
            "latitude": store.get("lat"),
            "longitude": store.get("lon"),
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

