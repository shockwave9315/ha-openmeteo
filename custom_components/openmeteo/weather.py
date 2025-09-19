# SPDX-License-Identifier: Apache-2.0
"""Weather entity for the Open-Meteo integration."""
from __future__ import annotations

import logging
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
from .helpers import hourly_at_now as _hourly_at_now, hourly_index_at_now

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Open-Meteo weather entity from a config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([OpenMeteoWeather(coordinator, config_entry)])


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

    def __init__(
        self, coordinator: OpenMeteoDataUpdateCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._config_entry = config_entry

        # Ustawienie stabilnego ID i unikalnego ID
        self._attr_unique_id = f"{config_entry.entry_id}-weather"
        self._attr_suggested_object_id = "pogoda"
        self._attr_has_entity_name = True

        # Urządzenie ma stabilną nazwę opartą na tytule wpisu konfiguracyjnego
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            name=config_entry.title,
            manufacturer="Open-Meteo",
        )

    @property
    def name(self) -> str:
        """Zwraca dynamiczną, przyjazną nazwę encji (aktualna lokalizacja)."""
        location_name = (self.coordinator.data or {}).get("location_name")
        if location_name:
            return location_name
        
        # Fallback do stabilnej nazwy urządzenia (tytułu wpisu)
        return self._config_entry.title

    @property
    def available(self) -> bool:
        return bool(self.coordinator.data) and self.coordinator.last_update_success

    @property
    def native_temperature(self) -> float | None:
        temp = (self.coordinator.data or {}).get("current_weather", {}).get("temperature")
        return round(temp, 1) if isinstance(temp, (int, float)) else None

    @property
    def native_pressure(self) -> float | None:
        val = _hourly_at_now(self.coordinator.data or {}, "pressure_msl")
        return round(val, 1) if isinstance(val, (int, float)) else None

    @property
    def native_wind_speed(self) -> float | None:
        wind_speed = (self.coordinator.data or {}).get("current_weather", {}).get("windspeed")
        return round(wind_speed, 1) if isinstance(wind_speed, (int, float)) else None

    @property
    def wind_bearing(self) -> float | None:
        wind_dir = (self.coordinator.data or {}).get("current_weather", {}).get("winddirection")
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
        dew = (self.coordinator.data or {}).get("current", {}).get("dewpoint_2m")
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

    async def async_forecast_daily(self) -> list[dict[str, Any]]:
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

    async def async_forecast_hourly(self) -> list[dict[str, Any]]:
        hourly = (self.coordinator.data or {}).get("hourly") or {}
        times = hourly.get("time") or []
        if not isinstance(times, list) or not times:
            return []

        start_idx = hourly_index_at_now(self.coordinator.data or {})
        if start_idx is None:
            return []

        end_idx = min(len(times), start_idx + 72)

        result: list[dict[str, Any]] = []
        for idx in range(start_idx, end_idx):
            ts = times[idx]
            dt = dt_util.parse_datetime(ts)
            if not dt:
                continue
            
            item: dict[str, Any] = {"datetime": dt.isoformat()}
            
            for out_key, src_key in {
                "temperature": "temperature_2m", "humidity": "relative_humidity_2m",
                "pressure": "pressure_msl", "wind_speed": "wind_speed_10m",
                "wind_bearing": "wind_direction_10m", "precipitation": "precipitation",
                "precipitation_probability": "precipitation_probability",
                "cloud_coverage": "cloud_cover",
            }.items():
                arr = hourly.get(src_key)
                item[out_key] = arr[idx] if isinstance(arr, list) and idx < len(arr) else None

            wcodes = hourly.get("weathercode")
            if isinstance(wcodes, list) and idx < len(wcodes):
                is_day_arr = hourly.get("is_day", [])
                is_day_val = is_day_arr[idx] if isinstance(is_day_arr, list) and idx < len(is_day_arr) else 1
                item["condition"] = _map_condition(wcodes[idx], is_day_val)
            else:
                item["condition"] = None
            
            result.append(item)

        return result