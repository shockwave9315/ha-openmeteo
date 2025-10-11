"""Weather entity for the Open-Meteo integration."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.weather import (
    ATTR_FORECAST_CONDITION,
    ATTR_FORECAST_PRECIPITATION,
    ATTR_FORECAST_PRECIPITATION_PROBABILITY,
    ATTR_FORECAST_TEMP,
    ATTR_FORECAST_TEMP_LOW,
    ATTR_FORECAST_TIME,
    ATTR_FORECAST_WIND_BEARING,
    ATTR_FORECAST_WIND_SPEED,
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
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
from homeassistant.util import slugify
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import async_generate_entity_id

from .const import (
    ATTRIBUTION,
    CONDITION_MAP,
    CONF_AREA_NAME_OVERRIDE,
    CONF_ENTITY_ID,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_MIN_TRACK_INTERVAL,
    CONF_MODE,
    CONF_TRACKED_ENTITY_ID,
    CONF_USE_PLACE_AS_DEVICE_NAME,
    DEFAULT_MIN_TRACK_INTERVAL,
    DOMAIN,
    MODE_STATIC,
    MODE_TRACK,
)
from .coordinator import OpenMeteoDataUpdateCoordinator
from .helpers import (
    hourly_at_now as _hourly_at_now,
    hourly_index_at_now as _hourly_index_at_now,
    maybe_update_device_name,
)

_LOGGER = logging.getLogger(__name__)


def _legacy_weather_object_ids(
    config_entry: ConfigEntry, entry: er.RegistryEntry | None
) -> set[str]:
    """Return slugified legacy object_ids derived from titles/names."""

    candidates: set[str] = set()
    for candidate in (
        config_entry.title,
        (config_entry.data or {}).get(CONF_AREA_NAME_OVERRIDE),
        (config_entry.options or {}).get(CONF_AREA_NAME_OVERRIDE),
    ):
        if candidate:
            slug = slugify(str(candidate))
            if slug:
                candidates.add(slug)
    if entry and entry.original_name:
        slug = slugify(str(entry.original_name))
        if slug:
            candidates.add(slug)
    return candidates


def _should_normalize_weather_entity_id(
    config_entry: ConfigEntry, entry: er.RegistryEntry
) -> bool:
    """Detect whether entity_id should be normalized to weather.open_meteo."""

    if getattr(entry, "preferred_object_id", None):
        return False

    object_id = entry.entity_id.split(".", 1)[1] if "." in entry.entity_id else entry.entity_id
    if object_id == "open_meteo":
        return False

    legacy_slugs = _legacy_weather_object_ids(config_entry, entry)
    if not legacy_slugs:
        return False

    return object_id in legacy_slugs


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Open-Meteo weather entity from a config entry."""

    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    # Jednorazowa migracja istniejącej encji pogody do stabilnego schematu
    ent_reg = er.async_get(hass)
    # Pre-create registry entry with stable object_id so first add picks it up
    try:
        reg_entry = ent_reg.async_get_or_create(
            domain="weather",
            platform=DOMAIN,
            unique_id=f"{config_entry.entry_id}-weather",
            suggested_object_id="open_meteo",
            config_entry=config_entry,
        )
        if _should_normalize_weather_entity_id(config_entry, reg_entry):
            desired = async_generate_entity_id("weather.{}", "open_meteo", hass, ent_reg)
            if reg_entry.entity_id != desired:
                _LOGGER.debug(
                    "[openmeteo] Pre-create: renaming weather entity_id %s -> %s",
                    reg_entry.entity_id,
                    desired,
                )
                ent_reg.async_update_entity(reg_entry.entity_id, new_entity_id=desired)
    except Exception as ex:
        _LOGGER.debug("[openmeteo] Pre-create weather entity failed: %s", ex)

    for entry in list(
        er.async_entries_for_config_entry(ent_reg, config_entry.entry_id)
    ):
        if entry.platform == DOMAIN and entry.domain == "weather":
            try:
                _LOGGER.debug(
                    "[openmeteo] Weather migration check: entity_id=%s, unique_id=%s",
                    entry.entity_id,
                    entry.unique_id,
                )
                await async_migrate_weather_entry(hass, config_entry, entry)  # type: ignore[arg-type]
            except Exception as ex:
                # Bezpiecznie ignorujemy pojedyncze błędy migracji
                _LOGGER.debug("[openmeteo] Weather migration error for %s: %s", entry.entity_id, ex)
                pass

    async_add_entities([OpenMeteoWeather(coordinator, config_entry)])


async def async_migrate_weather_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, entry: er.RegistryEntry
) -> bool:
    """Migrate old unique_id/entity_id of weather entity to stable scheme.

    Docelowo:
    - unique_id: "<entry_id>-weather"
    - entity_id: "weather.open_meteo"
    """
    if entry.domain != "weather" or entry.platform != DOMAIN:
        return False

    old_uid = entry.unique_id or ""
    ent_id = entry.entity_id

    new_uid = f"{config_entry.entry_id}-weather"

    updates: dict[str, Any] = {}
    if old_uid != new_uid:
        updates["new_unique_id"] = new_uid

    if _should_normalize_weather_entity_id(config_entry, entry):
        reg = er.async_get(hass)
        desired = async_generate_entity_id("weather.{}", "open_meteo", hass, reg)
        if ent_id != desired:
            updates["new_entity_id"] = desired

    if not updates:
        return False

    _LOGGER.debug(
        "[openmeteo] Weather migrating entity: %s -> %s (unique_id: %s -> %s)",
        ent_id,
        updates.get("new_entity_id", ent_id),
        old_uid or "",
        new_uid,
    )
    er.async_get(hass).async_update_entity(ent_id, **updates)
    return True


def _map_condition(weather_code: int | None, is_day: int | None = 1) -> str | None:
    """Map Open-Meteo weather code to Home Assistant condition."""

    if weather_code is None:
        return None
    if weather_code in (0, 1) and is_day == 0:
        return "clear-night"
    return CONDITION_MAP.get(weather_code)


class OpenMeteoWeather(CoordinatorEntity[OpenMeteoDataUpdateCoordinator], WeatherEntity):
    """Representation of the Open-Meteo weather entity."""

    _attr_attribution = ATTRIBUTION
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_precipitation_unit = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_native_visibility_unit = UnitOfLength.KILOMETERS
    _attr_native_pressure_unit = UnitOfPressure.HPA

    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_DAILY | WeatherEntityFeature.FORECAST_HOURLY
    )
    try:
        _attr_supported_features |= WeatherEntityFeature.HOURLY_PRECIPITATION
    except AttributeError:  # pragma: no cover - older HA versions
        pass

    def __init__(
        self, coordinator: OpenMeteoDataUpdateCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._config_entry = config_entry
        # Ważne: has_entity_name=False, aby entity_id było "weather.open_meteo" bez prefiksu miejscowości
        self._attr_has_entity_name = False
        self._attr_unique_id = f"{config_entry.entry_id}-weather"
        self._attr_suggested_object_id = "open_meteo"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            name=config_entry.title,
            manufacturer="Open-Meteo",
        )

        data = {**config_entry.data, **config_entry.options}
        mode = data.get(CONF_MODE)
        if not mode:
            mode = (
                MODE_TRACK
                if data.get(CONF_ENTITY_ID) or data.get(CONF_TRACKED_ENTITY_ID)
                else MODE_STATIC
            )
        self._mode = mode
        self._min_track_interval = int(
            data.get(CONF_MIN_TRACK_INTERVAL, DEFAULT_MIN_TRACK_INTERVAL)
        )
        self._provider = coordinator.provider

    def _default_device_name(self):
        """Deprecated: device name is stable from config_entry.title."""
        return self._config_entry.title or "Open-Meteo"

    def _derive_object_id(self) -> str:
        """Deprecated: object id is fixed via suggested_object_id."""
        return "open_meteo"

    def _update_device_name(self) -> None:
        """Device name is stable; no-op."""
        return

    def _update_friendly_name(self) -> None:
        """Set friendly name to location name without impacting entity_id generation."""
        if (data := self.coordinator.data) and (loc := data.get("location_name")):
            self._attr_name = str(loc)

    async def _maybe_update_device_registry_name(self) -> None:
        """Synchronize device name (Device Registry) with current location,
        unless the user has manually overridden it in the UI."""
        loc = (self.coordinator.data or {}).get("location_name")
        new_name = str(loc) if loc else None
        try:
            await maybe_update_device_name(self.hass, self._config_entry, new_name)
        except Exception as ex:
            _LOGGER.debug("[openmeteo] Device name sync skipped: %s", ex)

    async def _maybe_update_entry_title(self) -> None:
        """Update the Config Entry title to current place (mirrors device name)."""
        loc = (self.coordinator.data or {}).get("location_name")
        new_title = str(loc) if loc else None
        try:
            if new_title and self._config_entry.title != new_title:
                self.coordinator.async_update_entry_no_reload(title=new_title)
        except Exception as ex:
            _LOGGER.debug("[openmeteo] Entry title sync skipped: %s", ex)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._update_device_name()
        # Ustawiamy przyjazną nazwę po dodaniu, by nie wpływać na entity_id
        self._update_friendly_name()
        # Wymuś stabilny entity_id: weather.open_meteo (z ewentualnym sufiksem, jeśli zajęte)
        try:
            reg = er.async_get(self.hass)
            reg_entry = reg.async_get(self.entity_id)
            if reg_entry and _should_normalize_weather_entity_id(self._config_entry, reg_entry):
                desired = async_generate_entity_id(
                    "weather.{}", "open_meteo", self.hass, reg
                )
                if self.entity_id != desired:
                    _LOGGER.debug(
                        "[openmeteo] Normalizing weather entity_id %s -> %s",
                        self.entity_id,
                        desired,
                    )
                    reg.async_update_entity(self.entity_id, new_entity_id=desired)
        except Exception as ex:
            _LOGGER.debug("[openmeteo] Could not update entity_id: %s", ex)
            
        # Initial sync of device name and entry title with current location
        try:
            self.hass.async_create_task(self._maybe_update_device_registry_name())
            self.hass.async_create_task(self._maybe_update_entry_title())
        except Exception as ex:
            _LOGGER.debug(
                "[openmeteo] Could not update device registry or entry title: %s", 
                ex,
                exc_info=True
            )

    def _handle_coordinator_update(self) -> None:
        self._update_friendly_name()
        self.async_write_ha_state()
        try:
            self.hass.async_create_task(self._maybe_update_device_registry_name())
            self.hass.async_create_task(self._maybe_update_entry_title())
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # Helpers for forecasts and values (centralized in helpers.py)
    # -------------------------------------------------------------------------

    def _map_daily_forecast(self) -> list[dict[str, Any]]:
        daily = (self.coordinator.data or {}).get("daily") or {}
        times = daily.get("time", [])
        if not isinstance(times, list):
            return []

        temp_max = daily.get("temperature_2m_max", [])
        temp_min = daily.get("temperature_2m_min", [])
        wcodes = daily.get("weathercode", [])
        precip_sum = daily.get("precipitation_sum", [])
        ws_max = daily.get("wind_speed_10m_max", [])
        wd_dom = daily.get("wind_direction_10m_dominant", [])
        pop = daily.get("precipitation_probability_max", [])

        result: list[dict[str, Any]] = []
        for idx, dt in enumerate(times):
            forecast = {
                ATTR_FORECAST_TIME: dt,
                ATTR_FORECAST_TEMP: temp_max[idx] if idx < len(temp_max) else None,
                ATTR_FORECAST_TEMP_LOW: temp_min[idx] if idx < len(temp_min) else None,
                ATTR_FORECAST_CONDITION: _map_condition(wcodes[idx])
                if idx < len(wcodes)
                else None,
                ATTR_FORECAST_PRECIPITATION: precip_sum[idx]
                if idx < len(precip_sum)
                else None,
                ATTR_FORECAST_WIND_SPEED: ws_max[idx] if idx < len(ws_max) else None,
                ATTR_FORECAST_WIND_BEARING: wd_dom[idx] if idx < len(wd_dom) else None,
                ATTR_FORECAST_PRECIPITATION_PROBABILITY: pop[idx]
                if idx < len(pop)
                else None,
            }
            result.append(forecast)
        return result

    # -------------------------------------------------------------------------
    # Entity properties
    # -------------------------------------------------------------------------
    # Nazwę ustawiamy poprzez _attr_name w _update_friendly_name(),
    # aby nie wpływała na generowanie entity_id przy pierwszym dodaniu.

    @property
    def available(self) -> bool:
        return bool(self.coordinator.data) and self.coordinator.last_update_success

    @property
    def native_temperature(self) -> float | None:
        current_weather = (self.coordinator.data or {}).get("current_weather", {})
        temp = current_weather.get("temperature")
        return round(temp, 1) if isinstance(temp, (int, float)) else None

    @property
    def native_pressure(self) -> float | None:
        val = _hourly_at_now(self.coordinator.data or {}, "pressure_msl")
        return round(val, 1) if isinstance(val, (int, float)) else None

    @property
    def native_wind_speed(self) -> float | None:
        current_weather = (self.coordinator.data or {}).get("current_weather", {})
        wind_speed = current_weather.get("windspeed")
        return round(wind_speed, 1) if isinstance(wind_speed, (int, float)) else None

    @property
    def wind_bearing(self) -> float | None:
        current_weather = (self.coordinator.data or {}).get("current_weather", {})
        wind_dir = current_weather.get("winddirection")
        return round(wind_dir, 1) if isinstance(wind_dir, (int, float)) else None

    @property
    def native_visibility(self) -> float | None:
        visibility = _hourly_at_now(self.coordinator.data or {}, "visibility")
        return round(visibility / 1000, 2) if isinstance(visibility, (int, float)) else None

    @property
    def humidity(self) -> int | None:
        hum = _hourly_at_now(self.coordinator.data or {}, "relative_humidity_2m")
        return round(hum) if isinstance(hum, (int, float)) else None

    @property
    def native_dew_point(self) -> float | None:
        current = (self.coordinator.data or {}).get("current", {})
        dew = current.get("dewpoint_2m")
        if isinstance(dew, (int, float)):
            return round(dew, 1)
        val = _hourly_at_now(self.coordinator.data or {}, "dewpoint_2m")
        return round(val, 1) if isinstance(val, (int, float)) else None

    @property
    def condition(self) -> str | None:
        current_weather = (self.coordinator.data or {}).get("current_weather", {})
        weather_code = current_weather.get("weathercode")
        is_day = current_weather.get("is_day")
        return _map_condition(weather_code, is_day)

    @property
    def forecast_daily(self) -> list[dict[str, Any]]:
        return self._map_daily_forecast()

    async def async_forecast_daily(self) -> list[dict[str, Any]]:
        return self.forecast_daily

    async def async_forecast_hourly(self) -> list[dict[str, Any]]:
        hourly = (self.coordinator.data or {}).get("hourly") or {}
        times = hourly.get("time") or []
        if not isinstance(times, list) or not times:
            _LOGGER.debug("Hourly forecast: 0 entries")
            return []

        start_idx = _hourly_index_at_now(self.coordinator.data or {}) or 0
        end_idx = min(len(times), start_idx + 72)

        result: list[dict[str, Any]] = []
        for idx in range(start_idx, end_idx):
            ts = times[idx]
            dt = dt_util.parse_datetime(ts)
            if not dt:
                continue
            dt_local = dt_util.as_local(dt)
            item: dict[str, Any] = {"datetime": dt_local.isoformat()}
            for out_key, src_key in {
                "temperature": "temperature_2m",
                "dew_point": "dewpoint_2m",
                "humidity": "relative_humidity_2m",
                "pressure": "pressure_msl",
                "wind_speed": "wind_speed_10m",
                "wind_bearing": "wind_direction_10m",
                "wind_gust_speed": "wind_gusts_10m",
                "precipitation": "precipitation",
                "precipitation_probability": "precipitation_probability",
                "cloud_coverage": "cloud_cover",
            }.items():
                arr = hourly.get(src_key)
                item[out_key] = arr[idx] if isinstance(arr, list) and idx < len(arr) else None

            wcodes = hourly.get("weathercode")
            if isinstance(wcodes, list) and idx < len(wcodes):
                is_day_arr = hourly.get("is_day", [])
                is_day_val = (
                    is_day_arr[idx]
                    if isinstance(is_day_arr, list) and idx < len(is_day_arr)
                    else 1
                )
                item["condition"] = _map_condition(wcodes[idx], is_day_val)
            else:
                item["condition"] = None

            result.append(item)

        missing = sorted({key for entry in result for key, value in entry.items() if value is None})
        if result:
            _LOGGER.debug(
                "Hourly forecast: %d entries from %s to %s; missing fields: %s",
                len(result),
                result[0]["datetime"],
                result[-1]["datetime"],
                ", ".join(missing) if missing else "none",
            )
        else:
            _LOGGER.debug("Hourly forecast: 0 entries")
        return result

    @property
    def sunrise(self) -> datetime | None:
        val = (self.coordinator.data or {}).get("daily", {}).get("sunrise", [None])[0]
        if isinstance(val, str):
            dt = dt_util.parse_datetime(val)
        else:
            dt = val
        if not dt:
            return None
        if dt.tzinfo is None:
            tz = dt_util.get_time_zone(self.hass.config.time_zone) or dt_util.UTC
            dt = dt.replace(tzinfo=tz)
        return dt_util.as_utc(dt)

    @property
    def sunset(self) -> datetime | None:
        val = (self.coordinator.data or {}).get("daily", {}).get("sunset", [None])[0]
        if isinstance(val, str):
            dt = dt_util.parse_datetime(val)
        else:
            dt = val
        if not dt:
            return None
        if dt.tzinfo is None:
            tz = dt_util.get_time_zone(self.hass.config.time_zone) or dt_util.UTC
            dt = dt.replace(tzinfo=tz)
        return dt_util.as_utc(dt)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "location_name": (self.coordinator.data or {}).get("location_name"),
            "mode": self._mode,
            "min_track_interval": self._min_track_interval,
            "last_location_update": (self.coordinator.data or {}).get(
                "last_location_update"
            ),
            "provider": self._provider,
        }
        dew = self.native_dew_point
        if dew is not None:
            attrs["dew_point"] = dew
        return attrs
