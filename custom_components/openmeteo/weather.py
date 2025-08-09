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
            return "clear-night"  # zwracamy string zamiast importować stałą
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
        d = self.coordinator.data.get("daily", {}) or {}
        t = d.get("time", [])
        wcode = d.get("weathercode", [])
        tmax = d.get("temperature_2m_max", [])
        tmin = d.get("temperature_2m_min", [])
        ws_max = d.get("windspeed_10m_max", [])
        wd_dom = d.get("winddirection_10m_dominant", [])
        precip_sum = d.get("precipitation_sum", [])
        precip_prob_max = d.get("precipitation_probability_max", [])
        cloudcover = d.get("cloudcover", []) or d.get("cloudcover_mean", [])
        uv_max = d.get("uv_index_max", [])

        out: list[dict[str, Any]] = []
        for i, dt in enumerate(t):
            item: dict[str, Any] = {"datetime": dt}
            if i < len(wcode):
                item["condition"] = CONDITION_MAP.get(wcode[i])
            if i < len(tmax):
                item["temperature"] = tmax[i]
            if i < len(tmin):
                item["templow"] = tmin[i]          # << klucz wymagany przez HA
            if i < len(ws_max):
                item["wind_speed"] = ws_max[i]
            if i < len(wd_dom):
                item["wind_bearing"] = wd_dom[i]
            if i < len(precip_sum):
                item["precipitation"] = precip_sum[i]
            if i < len(precip_prob_max):
                item["precipitation_probability"] = precip_prob_max[i]
            if i < len(cloudcover):
                item["cloud_coverage"] = cloudcover[i]
            if i < len(uv_max):
                item["uv_index"] = uv_max[i]
            out.append(item)
        return out

    def _map_hourly_forecast(self) -> list[dict[str, Any]]:
        h = self.coordinator.data.get("hourly", {}) or {}
        t = h.get("time", [])
        temp = h.get("temperature_2m", [])
        wcode = h.get("weathercode", [])
        ws = h.get("windspeed_10m", [])
        wd = h.get("winddirection_10m", [])
        precip = h.get("precipitation", [])
        precip_prob = h.get("precipitation_probability", [])
        press = h.get("surface_pressure", [])
        hum = h.get("relativehumidity_2m", [])
        cloud = h.get("cloudcover", [])
        uvi = h.get("uv_index", [])

        out: list[dict[str, Any]] = []
        for i, dt in enumerate(t):
            item: dict[str, Any] = {"datetime": dt}
            if i < len(temp):
                item["temperature"] = temp[i]
            if i < len(wcode):
                item["condition"] = CONDITION_MAP.get(wcode[i])
            if i < len(ws):
                item["wind_speed"] = ws[i]
            if i < len(wd):
                item["wind_bearing"] = wd[i]
            if i < len(precip):
                item["precipitation"] = precip[i]
            if i < len(precip_prob):
                item["precipitation_probability"] = precip_prob[i]
            if i < len(press):
                item["pressure"] = press[i]
            if i < len(hum):
                item["humidity"] = hum[i]
            if i < len(cloud):
                item["cloud_coverage"] = cloud[i]
            if i < len(uvi):
                item["uv_index"] = uvi[i]
            out.append(item)
        return out

    # Właściwości (mogą być używane przez UI/stare miejsca)
    @property
    def forecast_daily(self) -> list[dict[str, Any]]:
        return self._map_daily_forecast()

    @property
    def forecast_hourly(self) -> list[dict[str, Any]]:
        return self._map_hourly_forecast()

    # Metody wymagane przez nowe API pogody
    async def async_forecast_daily(self) -> list[dict[str, Any]] | None:
        return self._map_daily_forecast()

    async def async_forecast_hourly(self) -> list[dict[str, Any]] | None:
        return self._map_hourly_forecast()
