"""Support for Open-Meteo weather service."""
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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import OpenMeteoDataUpdateCoordinator
from .const import CONDITION_MAP, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([OpenMeteoWeather(coordinator, config_entry)])


def _map_condition(weather_code: int | None, is_day: int | None = 1) -> str | None:
    """Map Open-Meteo weather code to Home Assistant condition."""
    if weather_code is None:
        return None
    if weather_code in (0, 1) and is_day == 0:
        return "clear-night"
    return CONDITION_MAP.get(weather_code)


class OpenMeteoWeather(CoordinatorEntity, WeatherEntity):
    """Implementation of an Open-Meteo weather entity."""

    _attr_attribution = "Weather data provided by Open-Meteo"
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_precipitation_unit = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_native_visibility_unit = UnitOfLength.KILOMETERS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    
    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_DAILY
        | WeatherEntityFeature.FORECAST_HOURLY
    )
    try:
        _attr_supported_features |= WeatherEntityFeature.HOURLY_PRECIPITATION
    except AttributeError:
        pass


    def __init__(
        self, coordinator: OpenMeteoDataUpdateCoordinator, config_entry: ConfigEntry
    ) -> None:
        """Initialize the weather entity."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_name = config_entry.data.get("name", "Open-Meteo")
        self._attr_unique_id = f"{config_entry.entry_id}-weather"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
            "name": "Open-Meteo",
            "manufacturer": "Open-Meteo",
        }

    @property
    def available(self) -> bool:
        return bool(self.coordinator.data) and getattr(self.coordinator, "last_update_success", True)

    @property
    def native_temperature(self) -> float | None:
        """Return the current temperature."""
        cw = self.coordinator.data.get("current_weather", {})
        temp = cw.get("temperature")
        return round(temp, 1) if isinstance(temp, (int, float)) else None

    @property
    def native_pressure(self) -> float | None:
        """Return the current pressure."""
        return self._first_hourly_value("surface_pressure")

    @property
    def native_wind_speed(self) -> float | None:
        """Return the current wind speed."""
        cw = self.coordinator.data.get("current_weather", {})
        ws = cw.get("windspeed")
        return round(ws, 1) if isinstance(ws, (int, float)) else None

    @property
    def wind_bearing(self) -> float | None:
        """Return the current wind bearing."""
        cw = self.coordinator.data.get("current_weather", {})
        wb = cw.get("winddirection")
        return round(wb, 1) if isinstance(wb, (int, float)) else None

    @property
    def native_visibility(self) -> float | None:
        """Return the current visibility."""
        vis = self._first_hourly_value("visibility")
        return round(vis / 1000, 2) if isinstance(vis, (int, float)) else None

    @property
    def humidity(self) -> int | None:
        """Return the current humidity."""
        hum = self._first_hourly_value("relativehumidity_2m")
        return round(hum) if isinstance(hum, (int, float)) else None

    @property
    def native_dew_point(self) -> float | None:
        """Return the current dew point."""
        dew = self._first_hourly_value("dewpoint_2m")
        return round(dew, 1) if isinstance(dew, (int, float)) else None

    @property
    def condition(self) -> str | None:
        """Return the current weather condition."""
        cw = self.coordinator.data.get("current_weather", {})
        weather_code = cw.get("weathercode")
        is_day = cw.get("is_day")
        return _map_condition(weather_code, is_day) if weather_code is not None else None
    
    def _first_hourly_value(self, key: str) -> float | None:
        arr = self.coordinator.data.get("hourly", {}).get(key)
        if isinstance(arr, list) and arr:
            return arr[0]
        return None

    def _map_daily_forecast(self) -> list[dict[str, Any]]:
        if not (daily := self.coordinator.data.get("daily")):
            return []
        
        times = daily.get("time", [])
        temp_max = daily.get("temperature_2m_max", [])
        temp_min = daily.get("temperature_2m_min", [])
        wcodes = daily.get("weathercode", [])
        precip_sum = daily.get("precipitation_sum", [])
        ws_max = daily.get("windspeed_10m_max", [])
        wd_dom = daily.get("winddirection_10m_dominant", [])
        pop = daily.get("precipitation_probability_max", [])
        
        out = []
        for i, dt in enumerate(times):
            forecast = {
                ATTR_FORECAST_TIME: dt,
                ATTR_FORECAST_TEMP: temp_max[i] if i < len(temp_max) else None,
                ATTR_FORECAST_TEMP_LOW: temp_min[i] if i < len(temp_min) else None,
                ATTR_FORECAST_CONDITION: _map_condition(wcodes[i]) if i < len(wcodes) else None,
                ATTR_FORECAST_PRECIPITATION: precip_sum[i] if i < len(precip_sum) else None,
                ATTR_FORECAST_WIND_SPEED: ws_max[i] if i < len(ws_max) else None,
                ATTR_FORECAST_WIND_BEARING: wd_dom[i] if i < len(wd_dom) else None,
                ATTR_FORECAST_PRECIPITATION_PROBABILITY: pop[i] if i < len(pop) else None,
            }
            out.append(forecast)
        return out

    def _map_hourly_forecast(self) -> list[dict[str, Any]]:
        if not (hourly := self.coordinator.data.get("hourly")):
            return []

        time_entries = hourly.get("time", [])
        temp = hourly.get("temperature_2m", [])
        wcode = hourly.get("weathercode", [])
        ws = hourly.get("windspeed_10m", [])
        wd = hourly.get("winddirection_10m", [])
        precip = hourly.get("precipitation", [])
        precip_prob = hourly.get("precipitation_probability", [])
        press = hourly.get("surface_pressure", [])
        hum = hourly.get("relativehumidity_2m", [])
        cloud = hourly.get("cloudcover", [])
        uvi = hourly.get("uv_index", [])

        out: list[dict[str, Any]] = []
        for i, dt in enumerate(time_entries):
            item: dict[str, Any] = {
                ATTR_FORECAST_TIME: dt,
                ATTR_FORECAST_TEMP: temp[i] if i < len(temp) else None,
                ATTR_FORECAST_CONDITION: _map_condition(wcode[i]) if i < len(wcode) else None,
                ATTR_FORECAST_WIND_SPEED: ws[i] if i < len(ws) else None,
                ATTR_FORECAST_WIND_BEARING: wd[i] if i < len(wd) else None,
                ATTR_FORECAST_PRECIPITATION: precip[i] if i < len(precip) else None,
                ATTR_FORECAST_PRECIPITATION_PROBABILITY: precip_prob[i] if i < len(precip_prob) else None,
            }
            if i < len(press): item["pressure"] = press[i]
            if i < len(hum): item["humidity"] = hum[i]
            if i < len(cloud): item["cloud_coverage"] = cloud[i]
            if i < len(uvi): item["uv_index"] = uvi[i]
            out.append(item)
        return out
        

    @property
    def forecast_daily(self) -> list[dict[str, Any]]:
        return self._map_daily_forecast()

    @property
    def forecast_hourly(self) -> list[dict[str, Any]]:
        return self._map_hourly_forecast()

    async def async_forecast_daily(self) -> list[dict[str, Any]]:
        return self.forecast_daily

    async def async_forecast_hourly(self) -> list[dict[str, Any]]:
        return self.forecast_hourly

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.coordinator.async_add_listener(self._handle_coordinator_update))