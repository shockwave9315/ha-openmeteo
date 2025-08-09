"""Support for Open-Meteo weather service."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.weather import (
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
from homeassistant.helpers.entity_platform import AddEntitiesCallback

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


class OpenMeteoWeather(WeatherEntity):
    """Implementation of an Open-Meteo weather entity."""

    _attr_attribution = "Weather data provided by Open-Meteo"
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_precipitation_unit = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_native_visibility_unit = UnitOfLength.KILOMETERS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_DAILY | WeatherEntityFeature.FORECAST_HOURLY
    )

    def __init__(self, coordinator: OpenMeteoDataUpdateCoordinator, config_entry: ConfigEntry) -> None:
        self.coordinator = coordinator
        self._attr_name = config_entry.data.get("name", "Open-Meteo")
        self._attr_unique_id = f"{config_entry.entry_id}-weather"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
            "name": "Open-Meteo",
            "manufacturer": "Open-Meteo",
        }

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and bool(self.coordinator.data)

    @property
    def condition(self) -> str | None:
        cw = self.coordinator.data.get("current_weather") or {}
        code = cw.get("weathercode")
        if code is None:
            return None
        is_day = cw.get("is_day", 1) == 1
        if code in (0, 1) and not is_day:
            return "clear-night"
        return CONDITION_MAP.get(code)

    @property
    def native_temperature(self) -> float | None:
        cw = self.coordinator.data.get("current_weather") or {}
        return cw.get("temperature")

    @property
    def native_pressure(self) -> float | None:
        hourly = self.coordinator.data.get("hourly", {})
        arr = hourly.get("surface_pressure", [])
        return arr[0] if isinstance(arr, list) and arr else None

    @property
    def native_wind_speed(self) -> float | None:
        cw = self.coordinator.data.get("current_weather") or {}
        return cw.get("windspeed")

    @property
    def wind_bearing(self) -> float | None:
        cw = self.coordinator.data.get("current_weather") or {}
        return cw.get("winddirection")

    @property
    def humidity(self) -> float | None:
        hourly = self.coordinator.data.get("hourly", {})
        arr = hourly.get("relativehumidity_2m", [])
        return arr[0] if isinstance(arr, list) and arr else None

    @property
    def native_apparent_temperature(self) -> float | None:
        hourly = self.coordinator.data.get("hourly", {})
        arr = hourly.get("apparent_temperature", [])
        return arr[0] if isinstance(arr, list) and arr else None

    @property
    def native_visibility(self) -> float | None:
        hourly = self.coordinator.data.get("hourly", {})
        v = (hourly.get("visibility", [None]) or [None])[0]
        return v / 1000 if isinstance(v, (int, float)) else None

    # ---------- Forecast builders (mapujemy do kluczy oczekiwanych przez HA) ----------

    def _map_daily_forecast(self) -> list[dict[str, Any]]:
        daily = self.coordinator.data.get("daily", {}) or {}
        times = daily.get("time", [])
        wcode = daily.get("weathercode", [])
        tmax = daily.get("temperature_2m_max", [])
        tmin = daily.get("temperature_2m_min", [])
        wspeed_max = daily.get("windspeed_10m_max", [])
        precip_sum = daily.get("precipitation_sum", [])

        result: list[dict[str, Any]] = []
        for i, dt in enumerate(times):
            item: dict[str, Any] = {"datetime": dt}
            # condition z mapy (dla dziennego nie rozróżniamy nocy)
            if i < len(wcode):
                item["condition"] = CONDITION_MAP.get(wcode[i])
            if i < len(tmax):
                item["temperature"] = tmax[i]
            if i < len(tmin):
                item["temperature_low"] = tmin[i]
            if i < len(wspeed_max):
                item["wind_speed"] = wspeed_max[i]
            if i < len(precip_sum):
                item["precipitation"] = precip_sum[i]
            # precipitation_probability dziennie często brak – pomijamy jeśli nie ma
            result.append(item)
        return result

    def _map_hourly_forecast(self) -> list[dict[str, Any]]:
        hourly = self.coordinator.data.get("hourly", {}) or {}
        times = hourly.get("time", [])
        temp = hourly.get("temperature_2m", [])
        wcode = hourly.get("weathercode", [])
        wspeed = hourly.get("windspeed_10m", [])
        precip = hourly.get("precipitation", [])
        precip_prob = hourly.get("precipitation_probability", [])

        result: list[dict[str, Any]] = []
        for i, dt in enumerate(times):
            item: dict[str, Any] = {"datetime": dt}
            if i < len(temp):
                item["temperature"] = temp[i]
            if i < len(wcode):
                item["condition"] = CONDITION_MAP.get(wcode[i])
            if i < len(wspeed):
                item["wind_speed"] = wspeed[i]
            if i < len(precip):
                item["precipitation"] = precip[i]
            if i < len(precip_prob):
                item["precipitation_probability"] = precip_prob[i]
            result.append(item)
        return result

    # Właściwości nadal zwracają listy (używane gdzie indziej)
    @property
    def forecast_daily(self) -> list[dict[str, Any]]:
        return self._map_daily_forecast()

    @property
    def forecast_hourly(self) -> list[dict[str, Any]]:
        return self._map_hourly_forecast()

    # Nowe API HA oczekuje tych metod asynchronicznych
    async def async_forecast_daily(self) -> list[dict[str, Any]] | None:
        return self._map_daily_forecast()

    async def async_forecast_hourly(self) -> list[dict[str, Any]] | None:
        return self._map_hourly_forecast()
