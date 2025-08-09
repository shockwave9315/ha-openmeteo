"""Support for Open-Meteo weather service."""
from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.components.weather import (
    ATTR_FORECAST_CONDITION,
    ATTR_FORECAST_PRECIPITATION,
    ATTR_FORECAST_PRECIPITATION_PROBABILITY,
    ATTR_FORECAST_TEMP,
    ATTR_FORECAST_TEMP_LOW,
    ATTR_FORECAST_TIME,
    ATTR_FORECAST_WIND_SPEED,
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
from homeassistant.util import dt as dt_util

from . import OpenMeteoDataUpdateCoordinator
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities):
    """Set up Open-Meteo weather from a config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([OpenMeteoWeather(coordinator, config_entry)])

class OpenMeteoWeather(WeatherEntity):
    """Representation of Open-Meteo weather."""

    _attr_name = "Open-Meteo"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_precipitation_unit = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_native_visibility_unit = UnitOfLength.KILOMETERS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_supported_features = WeatherEntityFeature.FORECAST_DAILY | WeatherEntityFeature.FORECAST_HOURLY

    def __init__(self, coordinator: OpenMeteoDataUpdateCoordinator, config_entry: ConfigEntry) -> None:
        """Initialize the Open-Meteo weather."""
        self.coordinator = coordinator
        self.config_entry = config_entry
        self._attr_unique_id = f"{config_entry.entry_id}-weather"
        self._attr_attribution = "Data provided by open-meteo.com"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
            "name": "Open-Meteo",
            "manufacturer": "Open-Meteo",
        }

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success and bool(self.coordinator.data)

    @property
    def condition(self) -> str | None:
        """Return the weather condition."""
        if not self.available:
            return None
        return self.coordinator.data.get("current_weather", {}).get("weathercode")

    @property
    def native_temperature(self) -> float | None:
        """Return the temperature."""
        if not self.available:
            return None
        return self.coordinator.data.get("current_weather", {}).get("temperature")

    @property
    def native_pressure(self) -> float | None:
        """Return the pressure."""
        if not self.available or "hourly" not in self.coordinator.data:
            return None
        arr = self.coordinator.data["hourly"].get("surface_pressure", [])
        return arr[0] if isinstance(arr, list) and arr else None

    @property
    def native_wind_speed(self) -> float | None:
        """Return the wind speed."""
        if not self.available:
            return None
        return self.coordinator.data.get("current_weather", {}).get("windspeed")

    @property
    def wind_bearing(self) -> float | None:
        """Return the wind bearing."""
        if not self.available:
            return None
        return self.coordinator.data.get("current_weather", {}).get("winddirection")

    @property
    def humidity(self) -> float | None:
        """Return the humidity."""
        if not self.available or "hourly" not in self.coordinator.data:
            return None
        arr = self.coordinator.data["hourly"].get("relativehumidity_2m", [])
        return arr[0] if isinstance(arr, list) and arr else None

    @property
    def native_apparent_temperature(self) -> float | None:
        """Return the apparent temperature."""
        if not self.available or "hourly" not in self.coordinator.data:
            return None
        arr = self.coordinator.data["hourly"].get("apparent_temperature", [])
        return arr[0] if isinstance(arr, list) and arr else None

    @property
    def native_visibility(self) -> float | None:
        """Return the visibility (km)."""
        if not self.available or "hourly" not in self.coordinator.data:
            return None
        v = self.coordinator.data.get("hourly", {}).get("visibility", [None])[0]
        return v / 1000 if isinstance(v, (int, float)) else None

    @property
    def forecast_daily(self) -> list[dict[str, Any]]:
        """Return the daily forecast in the format required by the UI."""
        if not self.available or "daily" not in self.coordinator.data:
            return []
        daily = self.coordinator.data["daily"]
        time_entries = daily.get("time", [])
        if not time_entries:
            return []

        forecast_data = []
        for i, time_entry in enumerate(time_entries):
            item: dict[str, Any] = {"datetime": time_entry}
            for key, arr in daily.items():
                if key == "time":
                    continue
                if isinstance(arr, list) and i < len(arr):
                    item[key] = arr[i]
            forecast_data.append(item)
        return forecast_data

    @property
    def forecast_hourly(self) -> list[dict[str, Any]]:
        """Return the hourly forecast for the UI."""
        if not self.available or "hourly" not in self.coordinator.data:
            return []
        hourly = self.coordinator.data["hourly"]
        time_entries = hourly.get("time", [])
        if not time_entries:
            return []

        forecast_data = []
        for i, time_entry in enumerate(time_entries):
            item: dict[str, Any] = {"datetime": time_entry}
            for key, arr in hourly.items():
                if key == "time":
                    continue
                if isinstance(arr, list) and i < len(arr):
                    item[key] = arr[i]
            forecast_data.append(item)
        return forecast_data

    async def async_update(self) -> None:
        """Update via coordinator."""
        await self.coordinator.async_request_refresh()

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )
