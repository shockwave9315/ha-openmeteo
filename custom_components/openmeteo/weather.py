"""Support for Open-Meteo weather service."""
from __future__ import annotations

from typing import Any

from homeassistant.components.weather import (
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfLength,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfPrecipitationDepth,
)
from homeassistant.core import HomeAssistant

from . import OpenMeteoDataUpdateCoordinator
from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([OpenMeteoWeather(coordinator, entry)])


class OpenMeteoWeather(WeatherEntity):
    _attr_name = "Open-Meteo"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_precipitation_unit = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_native_visibility_unit = UnitOfLength.KILOMETERS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_DAILY | WeatherEntityFeature.FORECAST_HOURLY
    )

    def __init__(self, coordinator: OpenMeteoDataUpdateCoordinator, entry: ConfigEntry):
        self.coordinator = coordinator
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}-weather"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Open-Meteo",
            "manufacturer": "Open-Meteo",
        }
        self._attr_attribution = "Powered by open-meteo.com"

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and bool(self.coordinator.data)

    @property
    def condition(self) -> str | None:
        cw = self.coordinator.data.get("current_weather") or {}
        return cw.get("weathercode")

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
        """Return the visibility."""
        if not self.available or "hourly" not in self.coordinator.data:
            return None
        v = self.coordinator.data.get("hourly", {}).get("visibility", [None])[0]
        return v / 1000 if isinstance(v, (int, float)) else None

    @property
    def forecast_daily(self) -> list[dict[str, Any]]:
        """Return the daily forecast in the format required by the UI."""
        daily = self.coordinator.data.get("daily", {})
        result = []
        times = daily.get("time", [])
        for idx, t in enumerate(times):
            item = {"datetime": t}
            for key, arr in daily.items():
                if key == "time":
                    continue
                if isinstance(arr, list) and idx < len(arr):
                    item[key] = arr[idx]
            result.append(item)
        return result

    @property
    def forecast_hourly(self) -> list[dict[str, Any]]:
        """Return the hourly forecast for the UI."""
        hourly = self.coordinator.data.get("hourly", {})
        result = []
        times = hourly.get("time", [])
        for idx, t in enumerate(times):
            item = {"datetime": t}
            for key, arr in hourly.items():
                if key == "time":
                    continue
                if isinstance(arr, list) and idx < len(arr):
                    item[key] = arr[idx]
            result.append(item)
        return result

    async def async_update(self) -> None:
        """Request coordinator to refresh."""
        await self.coordinator.async_request_refresh()

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )
