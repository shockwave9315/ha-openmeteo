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
    CONCENTRATION_PARTS_PER_MILLION,
    DEGREE,
    PERCENTAGE,
    UV_INDEX,
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
from homeassistant.util import dt as dt_util
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import async_generate_entity_id
from .helpers import (
    hourly_at_now as _hourly_at_now, 
    hourly_sum_last_n as _hourly_sum_last_n, 
    extra_attrs as _extra_attrs,
    aq_hour_value as _aq_hour_value,
)
import logging

from .coordinator import OpenMeteoDataUpdateCoordinator
from .const import (
    ALL_SENSOR_KEYS,
    AQ_HOURLY_KEYS,
    ATTRIBUTION,
    CONF_ENABLED_AQ_SENSORS,
    CONF_ENABLED_SENSORS,
    CONF_ENABLED_WEATHER_SENSORS,
    CONF_MODE,
    CONF_USE_PLACE_AS_DEVICE_NAME,
    DEFAULT_USE_PLACE_AS_DEVICE_NAME,
    DOMAIN,
    MODE_STATIC,
)

# Conversion factor for carbon monoxide concentration reported in µg/m³.
# 24.45 is the molar volume of air at 25°C and 1 atm, and 28.01 is the molar
# mass of carbon monoxide in g/mol. Dividing by 1000 converts µg to mg.
CO_MOLAR_MASS = 28.01  # g/mol
CO_UGM3_TO_PPM_FACTOR = 24.45 / (CO_MOLAR_MASS * 1000)

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
    "weather_code": "pogoda",
    "weather_condition": "stan_pogody",
    "precipitation_sum": "suma_opadow",
    "snowfall": "opady_sniegu",
    "snow_depth": "pokrywa_sniezna",
    "sunrise": "wschod_slonca",
    "sunset": "zachod_slonca",
    "uv_index": "promieniowanie_uv",
    "uv_index_max": "maksymalne_promieniowanie_uv",
    "wind_speed_max": "maksymalna_predkosc_wiatru",
    "temperature_min": "temperatura_minimalna",
    "temperature_max": "temperatura_maksymalna",
    "apparent_temperature_min": "odczuwalna_temperatura_minimalna",
    "apparent_temperature_max": "odczuwalna_temperatura_maksymalna",
}


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




def _first_daily_value(d: dict, key: str):
    try:
        arr = ((d.get('daily', {}) or {}).get(key)) or []
        return arr[0] if isinstance(arr, list) and arr else None
    except Exception:
        return None

@dataclass(frozen=True, kw_only=True)
class OpenMeteoSensorDescription(SensorEntityDescription):
    """Extended description with custom value/attr functions."""
    value_fn: Callable[[dict[str, Any]], Any] | None = None
    attr_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None





def _visibility_km(d: dict) -> float | None:
    """Return visibility in kilometers using hourly_at_now('visibility')."""
    try:
        vis = _hourly_at_now(d, "visibility")
        if isinstance(vis, (int, float)):
            return round(vis / 1000, 2)
        return None
    except Exception:
        return None
_LOGGER = logging.getLogger(__name__)

SENSOR_TYPES: dict[str, OpenMeteoSensorDescription] = {
    "temperature": OpenMeteoSensorDescription(
        key="temperature",
        translation_key="temperature",
        name="Temperatura",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=lambda d: d.get("current_weather", {}).get("temperature"),
    ),
    "humidity": OpenMeteoSensorDescription(
        key="humidity",
        translation_key="humidity",
        name="Wilgotność",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:water-percent",
        device_class=SensorDeviceClass.HUMIDITY,
        value_fn=lambda d: _hourly_at_now(d, "relative_humidity_2m"),
    ),
    "apparent_temperature": OpenMeteoSensorDescription(
        key="apparent_temperature",
        translation_key="apparent_temperature",
        name="Temperatura odczuwalna",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        icon="mdi:thermometer-alert",
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=lambda d: _hourly_at_now(d, "apparent_temperature"),
    ),
    "precipitation_probability": OpenMeteoSensorDescription(
        key="precipitation_probability",
        translation_key="precipitation_probability",
        name="Prawdopodobieństwo opadów",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:umbrella-outline",
        device_class=None,
        value_fn=lambda d: _hourly_at_now(d, "precipitation_probability"),
    ),
    "precipitation_sum": OpenMeteoSensorDescription(
        key="precipitation_sum",
        translation_key="precipitation_sum",
        name="Opad (bieżąca godzina)",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        icon="mdi:cup-water",
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (_hourly_at_now(d, "precipitation") or 0)
        + (_hourly_at_now(d, "snowfall") or 0),
    ),


    "precipitation_daily_sum": OpenMeteoSensorDescription(
        key="precipitation_daily_sum",
        translation_key="precipitation_daily_sum",
        name="Suma opadów (dzienna)",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        icon="mdi:weather-pouring",
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda d: _first_daily_value(d, "precipitation_sum"),
    ),
    "precipitation_last_3h": OpenMeteoSensorDescription(
        key="precipitation_last_3h",
        translation_key="precipitation_last_3h",
        name="Opad (ostatnie 3h)",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        icon="mdi:weather-pouring",
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _hourly_sum_last_n(d, ["precipitation", "snowfall"], 3),
    ),
    "wind_speed": OpenMeteoSensorDescription(
        key="wind_speed",
        translation_key="wind_speed",
        name="Prędkość wiatru",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        icon="mdi:weather-windy",
        device_class=None,
        value_fn=lambda d: d.get("current_weather", {}).get("windspeed"),
    ),
    "wind_gust": OpenMeteoSensorDescription(
        key="wind_gust",
        translation_key="wind_gust",
        name="Porywy wiatru",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        icon="mdi:weather-windy-variant",
        device_class=None,
        value_fn=lambda d: _hourly_at_now(d, "wind_gusts_10m"),
    ),
    "wind_bearing": OpenMeteoSensorDescription(
        key="wind_bearing",
        translation_key="wind_bearing",
        name="Kierunek wiatru",
        native_unit_of_measurement=DEGREE,
        icon="mdi:compass",
        device_class=None,
        value_fn=lambda d: d.get("current_weather", {}).get("winddirection"),
    ),
    "pressure": OpenMeteoSensorDescription(
        key="pressure",
        translation_key="pressure",
        name="Ciśnienie",
        native_unit_of_measurement=UnitOfPressure.HPA,
        icon="mdi:gauge",
        device_class=SensorDeviceClass.PRESSURE,
        value_fn=lambda d: _hourly_at_now(d, "pressure_msl"),
    ),
    "visibility": OpenMeteoSensorDescription(
        key="visibility",
        translation_key="visibility",
        name="Widzialność",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        icon="mdi:eye",
        device_class=None,
        value_fn=_visibility_km,
    ),
    "dew_point": OpenMeteoSensorDescription(
        key="dew_point",
        translation_key="dew_point",
        name="Punkt rosy",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        icon="mdi:water",
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=lambda d: (d.get("current", {}) or {}).get("dewpoint_2m")
        or _hourly_at_now(d, "dewpoint_2m"),
    ),
    "location": OpenMeteoSensorDescription(
        key="location",
        translation_key="location",
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
        translation_key="sunrise",
        name="Wschód słońca",
        native_unit_of_measurement=None,
        icon="mdi:weather-sunset-up",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: _first_daily_dt(d, "sunrise"),
    ),
    "sunset": OpenMeteoSensorDescription(
        key="sunset",
        translation_key="sunset",
        name="Zachód słońca",
        native_unit_of_measurement=None,
        icon="mdi:weather-sunset-down",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: _first_daily_dt(d, "sunset"),
    ),
    # UV: osobna klasa OpenMeteoUvIndexSensor
}

# Air Quality Sensors
AQ_SENSORS: dict[str, OpenMeteoSensorDescription] = {
    "pm2_5": OpenMeteoSensorDescription(
        key="pm2_5",
        translation_key="pm2_5",
        name="PM2.5",
        native_unit_of_measurement="µg/m³",
        icon="mdi:blur",
        device_class=SensorDeviceClass.PM25,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "pm10": OpenMeteoSensorDescription(
        key="pm10",
        translation_key="pm10",
        name="PM10",
        native_unit_of_measurement="µg/m³",
        icon="mdi:blur",
        device_class=SensorDeviceClass.PM10,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "co": OpenMeteoSensorDescription(
        key="co",
        translation_key="carbon_monoxide",
        name="Tlenek węgla",
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
        icon="mdi:molecule",
        device_class=SensorDeviceClass.CO,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "no2": OpenMeteoSensorDescription(
        key="no2",
        translation_key="nitrogen_dioxide",
        name="Dwutlenek azotu",
        native_unit_of_measurement="µg/m³",
        icon="mdi:molecule",
        device_class=SensorDeviceClass.NITROGEN_DIOXIDE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "so2": OpenMeteoSensorDescription(
        key="so2",
        translation_key="sulphur_dioxide",
        name="Dwutlenek siarki",
        native_unit_of_measurement="µg/m³",
        icon="mdi:molecule",
        device_class=SensorDeviceClass.SULPHUR_DIOXIDE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "o3": OpenMeteoSensorDescription(
        key="o3",
        translation_key="ozone",
        name="Ozon",
        native_unit_of_measurement="µg/m³",
        icon="mdi:chemical-weapon",
        device_class=SensorDeviceClass.OZONE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "aqi_us": OpenMeteoSensorDescription(
        key="aqi_us",
        translation_key="us_aqi",
        name="US AQI",
        native_unit_of_measurement=None,
        icon="mdi:gauge",
        device_class=None,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "aqi_eu": OpenMeteoSensorDescription(
        key="aqi_eu",
        translation_key="european_aqi",
        name="European AQI",
        native_unit_of_measurement=None,
        icon="mdi:gauge",
        device_class=None,
        state_class=SensorStateClass.MEASUREMENT,
    ),
}


async def async_migrate_entry(hass, config_entry, entry: er.RegistryEntry) -> bool:
    """Migrate old unique_id/entity_id to the new scheme."""
    if entry.domain != "sensor" or entry.platform != "openmeteo":
        return False

    old_uid = entry.unique_id or ""
    ent_id = entry.entity_id

    key_guess = None
    for key, slug in OBJECT_ID_PL.items():
        if ent_id.endswith(f".{slug}") or f".{slug}_" in ent_id:
            key_guess = key
            break

    if not key_guess:
        import re
        m = re.search(r":([a-z0-9_]+)$", old_uid)
        if m:
            key_guess = m.group(1)

    if not key_guess or key_guess not in OBJECT_ID_PL:
        return False

    new_uid = f"{config_entry.entry_id}:{key_guess}"

    reg = er.async_get(hass)

    slug = OBJECT_ID_PL[key_guess]
    domain = "sensor"
    new_entity_id = async_generate_entity_id(f"{domain}.{{}}", slug, hass, reg)

    _LOGGER.debug(
        "[openmeteo] Sensor migration for %s: key=%s slug=%s old_uid=%s -> new_uid=%s new_entity_id=%s",
        ent_id,
        key_guess,
        slug,
        old_uid,
        new_uid,
        new_entity_id,
    )

    # Aktualizuj entity_id zawsze, a unique_id tylko jeśli się zmienił
    if new_uid != old_uid:
        reg.async_update_entity(ent_id, new_unique_id=new_uid, new_entity_id=new_entity_id)
    else:
        reg.async_update_entity(ent_id, new_entity_id=new_entity_id)
    return True


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Open-Meteo sensor based on a config entry."""
    # Koordynator może być zapisany bezpośrednio lub pod kluczem "coordinator"
    stored = hass.data[DOMAIN][config_entry.entry_id]
    coordinator: OpenMeteoDataUpdateCoordinator = (
        stored.get("coordinator") if isinstance(stored, dict) else stored
    )

    def _as_list(source: Mapping[str, Any] | None, key: str) -> list[str] | None:
        if not source:
            return None
        value = source.get(key)
        return value if isinstance(value, list) else None

    options = config_entry.options or {}
    data = config_entry.data or {}

    enabled_weather = _as_list(options, CONF_ENABLED_WEATHER_SENSORS)
    if enabled_weather is None:
        enabled_weather = _as_list(data, CONF_ENABLED_WEATHER_SENSORS)
    enabled_aq = _as_list(options, CONF_ENABLED_AQ_SENSORS)
    if enabled_aq is None:
        enabled_aq = _as_list(data, CONF_ENABLED_AQ_SENSORS)

    if enabled_weather is None:
        enabled_weather = []
    if enabled_aq is None:
        enabled_aq = []

    if not (enabled_weather or enabled_aq):
        legacy = options.get(CONF_ENABLED_SENSORS)
        if not isinstance(legacy, list) or not legacy:
            legacy = data.get(CONF_ENABLED_SENSORS)
        if isinstance(legacy, list) and legacy:
            combined = [k for k in legacy if k in ALL_SENSOR_KEYS]
            enabled_weather = combined
            enabled_aq = []
        else:
            enabled_weather = ALL_SENSOR_KEYS[:]
            enabled_aq = []

    enabled_set = set(enabled_weather) | set(enabled_aq)

    entities = []
    for sensor_type in SENSOR_TYPES:
        if sensor_type not in enabled_set:
            continue
        entities.append(OpenMeteoSensor(coordinator, config_entry, sensor_type))

    if "uv_index" in enabled_set:
        # Add UV sensor (not in SENSOR_TYPES to avoid duplication)
        entities.append(OpenMeteoUvIndexSensor(coordinator, config_entry))

    for sensor_type in AQ_SENSORS:
        if sensor_type not in enabled_set:
            continue
        entities.append(OpenMeteoAqSensor(coordinator, config_entry, sensor_type))

    # One-time migration of existing entities
    ent_reg = er.async_get(hass)
    for entry in list(ent_reg.entities.values()):
        if entry.platform == "openmeteo" and entry.domain == "sensor" and entry.config_entry_id == config_entry.entry_id:
            try:
                _LOGGER.debug(
                    "[openmeteo] Sensor migration check: entity_id=%s unique_id=%s",
                    entry.entity_id,
                    entry.unique_id,
                )
                await async_migrate_entry(hass, config_entry, entry)  # type: ignore[arg-type]
            except Exception:
                continue

    async_add_entities(entities, True)


class OpenMeteoSensor(CoordinatorEntity[OpenMeteoDataUpdateCoordinator], SensorEntity):
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

        # Set entity attributes
        # Ważne: has_entity_name=False, aby entity_id NIE zawierało prefiksu nazwy urządzenia (miejscowości)
        self._attr_has_entity_name = False
        self._attr_suggested_object_id = OBJECT_ID_PL.get(sensor_type, sensor_type) or (sensor_type or "open_meteo_sensor")
        self._attr_unique_id = f"{config_entry.entry_id}:{sensor_type}"

        # Set device info
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
            value = self._value_fn(self.coordinator.data)
            return value if value is None or isinstance(value, (int, float)) else value
        except (IndexError, KeyError):
            return None

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
                attrs["source"] = src
        except Exception:  # pylint: disable=broad-except
            pass
        return attrs

    def _handle_place_update(self, *_) -> None:
        """Handle place name update."""
        pass  # Place name is now handled by the entity registry

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        store = (
            self.hass.data.get(DOMAIN, {})
            .get("entries", {})
            .setdefault(self._config_entry.entry_id, {})
        )
        store.setdefault("entities", []).append(self)

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        store = (
            self.hass.data.get(DOMAIN, {})
            .get("entries", {})
            .get(self._config_entry.entry_id)
        )
        if store and self in store.get("entities", []):
            store["entities"].remove(self)
        await super().async_will_remove_from_hass()


class OpenMeteoUvIndexSensor(CoordinatorEntity[OpenMeteoDataUpdateCoordinator], SensorEntity):
    """UV Index sensor for the current hour."""

    def __init__(
        self,
        coordinator: OpenMeteoDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._config_entry = config_entry

        # Set entity attributes
        # Ważne: has_entity_name=False, aby entity_id było "sensor.promieniowanie_uv" bez prefiksu miejscowości
        self._attr_has_entity_name = False
        self._attr_suggested_object_id = OBJECT_ID_PL.get("uv_index", "promieniowanie_uv")
        self._attr_unique_id = f"{config_entry.entry_id}:uv_index"
        self._attr_native_unit_of_measurement = UV_INDEX
        self._attr_icon = "mdi:weather-sunny-alert"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_class = getattr(SensorDeviceClass, "UV_INDEX", None)
        self._attr_translation_key = "uv_index"
        # Explicit name to avoid blank label when has_entity_name is False
        self._attr_name = "Indeks UV"

        # Set device info
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

        # Try current_weather first, fall back to hourly
        uv = (self.coordinator.data.get("current_weather") or {}).get("uv_index")
        if uv is not None:
            return uv

        return _hourly_at_now(self.coordinator.data, "uv_index")

    @property
    def extra_state_attributes(self):
        attrs = _extra_attrs(self.coordinator.data or {})
        attrs["attribution"] = ATTRIBUTION
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


class OpenMeteoAqSensor(CoordinatorEntity[OpenMeteoDataUpdateCoordinator], SensorEntity):
    """Air Quality sensor for Open-Meteo integration."""

    def __init__(
        self,
        coordinator: OpenMeteoDataUpdateCoordinator,
        config_entry: ConfigEntry,
        sensor_type: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._sensor_type = sensor_type
        self._config_entry = config_entry
        self.entity_description = AQ_SENSORS[sensor_type]
        
        # Set entity attributes
        self._attr_has_entity_name = False
        self._attr_suggested_object_id = f"{sensor_type}_aq"
        self._attr_unique_id = f"{config_entry.entry_id}:{sensor_type}_aq"
        self._attr_state_class = SensorStateClass.MEASUREMENT
        
        # Set device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            name=config_entry.title,
            manufacturer="Open-Meteo",
        )

    @property
    def native_value(self) -> float | int | None:
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
            
        value = _aq_hour_value(self.coordinator.data, AQ_HOURLY_KEYS[self._sensor_type])
        
        # Round AQI values to integers
        if value is None:
            return None

        if self._sensor_type in ("aqi_us", "aqi_eu"):
            try:
                return round(float(value))
            except (TypeError, ValueError):
                return None

        if self._sensor_type == "co":
            try:
                return round(float(value) * CO_UGM3_TO_PPM_FACTOR, 3)
            except (TypeError, ValueError):
                return None

        return value

    @property
    def available(self) -> bool:
        """Return True if entity is available and has valid data."""
        if not self.coordinator.last_update_success:
            return False
            
        # Check if we have AQ data and the specific key exists
        aq_data = (self.coordinator.data or {}).get("aq", {})
        hourly = aq_data.get("hourly", {})
        return AQ_HOURLY_KEYS.get(self._sensor_type, "") in hourly

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attrs = _extra_attrs(self.coordinator.data or {})
        attrs["attribution"] = ATTRIBUTION
        return attrs

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        store = (
            self.hass.data.get(DOMAIN, {})
            .get("entries", {})
            .setdefault(self._config_entry.entry_id, {})
        )
        store.setdefault("entities", []).append(self)

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        store = (
            self.hass.data.get(DOMAIN, {})
            .get("entries", {})
            .get(self._config_entry.entry_id)
        )
        if store and self in store.get("entities", []):
            store["entities"].remove(self)
        await super().async_will_remove_from_hass()