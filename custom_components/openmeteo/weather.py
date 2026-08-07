"""Weather entity for Open-Meteo v2."""
from __future__ import annotations

from collections.abc import Mapping
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

from .const import ATTRIBUTION, CONDITION_MAP, DOMAIN
from .coordinator import OpenMeteoDataUpdateCoordinator
from .helpers import hourly_at_now, hourly_index_at_now
from .identity import weather_object_id, weather_unique_id
from .runtime import get_entry_coordinator, get_runtime_data


def _map_condition(weather_code: int | None, is_day: int | None = 1) -> str | None:
    if weather_code is None:
        return None
    if weather_code in (0, 1) and is_day == 0:
        return "clear-night"
    return CONDITION_MAP.get(weather_code)


def _as_list(mapping: Mapping[str, Any], key: str) -> list[Any]:
    value = mapping.get(key)
    return value if isinstance(value, list) else []


def _parse_forecast_datetime(raw: Any, timezone_name: str | None) -> datetime | None:
    if isinstance(raw, datetime):
        value = raw
    elif isinstance(raw, str):
        value = dt_util.parse_datetime(raw)
    else:
        return None
    if value is None:
        return None
    if value.tzinfo is None:
        timezone = dt_util.get_time_zone(timezone_name or "") or dt_util.UTC
        value = value.replace(tzinfo=timezone)
    return value


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
    async_add_entities([OpenMeteoWeather(coordinator, config_entry, source_key)])


class OpenMeteoWeather(CoordinatorEntity[OpenMeteoDataUpdateCoordinator], WeatherEntity):
    """Stable weather entity whose display name follows the current place."""

    _attr_has_entity_name = False
    _attr_attribution = ATTRIBUTION
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_precipitation_unit = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_native_visibility_unit = UnitOfLength.KILOMETERS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_DAILY | WeatherEntityFeature.FORECAST_HOURLY
    )

    def __init__(
        self,
        coordinator: OpenMeteoDataUpdateCoordinator,
        config_entry: ConfigEntry,
        source_key: str,
    ) -> None:
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_unique_id = weather_unique_id(config_entry.entry_id)
        self._attr_suggested_object_id = weather_object_id(source_key)
        self._refresh_display_name()
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            name=coordinator.location_name or config_entry.title or "Open-Meteo",
            manufacturer="Open-Meteo",
            model="Forecast API",
        )

    def _refresh_display_name(self) -> None:
        self._attr_name = (
            (self.coordinator.data or {}).get("location_name")
            or self.coordinator.location_name
            or self._config_entry.title
            or "Open-Meteo"
        )

    def _handle_coordinator_update(self) -> None:
        self._refresh_display_name()
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and bool(self.coordinator.data)

    @property
    def native_temperature(self) -> float | None:
        current = (self.coordinator.data or {}).get("current") or {}
        value = current.get("temperature_2m") if isinstance(current, Mapping) else None
        return round(float(value), 1) if isinstance(value, (int, float)) else None

    @property
    def native_pressure(self) -> float | None:
        current = (self.coordinator.data or {}).get("current") or {}
        value = current.get("pressure_msl") if isinstance(current, Mapping) else None
        if not isinstance(value, (int, float)):
            value = hourly_at_now(self.coordinator.data or {}, "pressure_msl")
        return round(float(value), 1) if isinstance(value, (int, float)) else None

    @property
    def native_wind_speed(self) -> float | None:
        current = (self.coordinator.data or {}).get("current") or {}
        value = current.get("wind_speed_10m") if isinstance(current, Mapping) else None
        return round(float(value), 1) if isinstance(value, (int, float)) else None

    @property
    def wind_bearing(self) -> float | None:
        current = (self.coordinator.data or {}).get("current") or {}
        value = current.get("wind_direction_10m") if isinstance(current, Mapping) else None
        return round(float(value), 1) if isinstance(value, (int, float)) else None

    @property
    def native_visibility(self) -> float | None:
        value = hourly_at_now(self.coordinator.data or {}, "visibility")
        return round(float(value) / 1000, 2) if isinstance(value, (int, float)) else None

    @property
    def humidity(self) -> int | None:
        current = (self.coordinator.data or {}).get("current") or {}
        value = current.get("relative_humidity_2m") if isinstance(current, Mapping) else None
        if not isinstance(value, (int, float)):
            value = hourly_at_now(self.coordinator.data or {}, "relative_humidity_2m")
        return round(float(value)) if isinstance(value, (int, float)) else None

    @property
    def native_dew_point(self) -> float | None:
        value = hourly_at_now(self.coordinator.data or {}, "dew_point_2m")
        return round(float(value), 1) if isinstance(value, (int, float)) else None

    @property
    def condition(self) -> str | None:
        current = (self.coordinator.data or {}).get("current") or {}
        if not isinstance(current, Mapping):
            return None
        code = current.get("weather_code")
        is_day = current.get("is_day", 1)
        try:
            return _map_condition(int(code), int(is_day)) if code is not None else None
        except (TypeError, ValueError):
            return None

    async def async_forecast_daily(self) -> list[dict[str, Any]]:
        data = self.coordinator.data or {}
        daily = data.get("daily") or {}
        if not isinstance(daily, Mapping):
            return []

        times = _as_list(daily, "time")
        max_temp = _as_list(daily, "temperature_2m_max")
        min_temp = _as_list(daily, "temperature_2m_min")
        codes = _as_list(daily, "weather_code")
        precipitation = _as_list(daily, "precipitation_sum")
        probability = _as_list(daily, "precipitation_probability_max")
        wind_speed = _as_list(daily, "wind_speed_10m_max")
        wind_bearing = _as_list(daily, "wind_direction_10m_dominant")

        result: list[dict[str, Any]] = []
        for index, raw_time in enumerate(times):
            dt = _parse_forecast_datetime(raw_time, str(data.get("timezone") or ""))
            if dt is None:
                continue
            item: dict[str, Any] = {ATTR_FORECAST_TIME: dt.isoformat()}
            item[ATTR_FORECAST_TEMP] = max_temp[index] if index < len(max_temp) else None
            item[ATTR_FORECAST_TEMP_LOW] = min_temp[index] if index < len(min_temp) else None
            item[ATTR_FORECAST_PRECIPITATION] = (
                precipitation[index] if index < len(precipitation) else None
            )
            item[ATTR_FORECAST_PRECIPITATION_PROBABILITY] = (
                probability[index] if index < len(probability) else None
            )
            item[ATTR_FORECAST_WIND_SPEED] = (
                wind_speed[index] if index < len(wind_speed) else None
            )
            item[ATTR_FORECAST_WIND_BEARING] = (
                wind_bearing[index] if index < len(wind_bearing) else None
            )
            item[ATTR_FORECAST_CONDITION] = (
                _map_condition(codes[index]) if index < len(codes) else None
            )
            result.append(item)
        return result

    async def async_forecast_hourly(self) -> list[dict[str, Any]]:
        data = self.coordinator.data or {}
        hourly = data.get("hourly") or {}
        if not isinstance(hourly, Mapping):
            return []
        times = _as_list(hourly, "time")
        if not times:
            return []

        start_index = hourly_index_at_now(data) or 0
        end_index = min(len(times), start_index + 72)
        timezone_name = str(data.get("timezone") or "")

        field_map = {
            "temperature": "temperature_2m",
            "dew_point": "dew_point_2m",
            "humidity": "relative_humidity_2m",
            "pressure": "pressure_msl",
            "wind_speed": "wind_speed_10m",
            "wind_bearing": "wind_direction_10m",
            "wind_gust_speed": "wind_gusts_10m",
            "precipitation": "precipitation",
            "precipitation_probability": "precipitation_probability",
            "cloud_coverage": "cloud_cover",
        }

        result: list[dict[str, Any]] = []
        for index in range(start_index, end_index):
            dt = _parse_forecast_datetime(times[index], timezone_name)
            if dt is None:
                continue
            item: dict[str, Any] = {"datetime": dt.isoformat()}
            for output_key, source_key in field_map.items():
                values = _as_list(hourly, source_key)
                item[output_key] = values[index] if index < len(values) else None

            codes = _as_list(hourly, "weather_code")
            days = _as_list(hourly, "is_day")
            code = codes[index] if index < len(codes) else None
            is_day = days[index] if index < len(days) else 1
            try:
                item["condition"] = (
                    _map_condition(int(code), int(is_day)) if code is not None else None
                )
            except (TypeError, ValueError):
                item["condition"] = None
            result.append(item)
        return result

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        location = data.get("location") if isinstance(data.get("location"), Mapping) else {}
        return {
            "location_name": data.get("location_name"),
            "latitude": location.get("latitude"),
            "longitude": location.get("longitude"),
            "last_location_update": data.get("last_location_update"),
            "mode": data.get("mode"),
            "provider": self.coordinator.provider,
        }
