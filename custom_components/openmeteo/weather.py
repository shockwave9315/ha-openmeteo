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
    ATTR_FORECAST_WIND_BEARING,
    ATTR_FORECAST_WIND_SPEED,
    ATTR_CONDITION_CLEAR_NIGHT, # Ten import został przeniesiony tutaj
    WeatherEntity,
    WeatherEntityFeature,
    Forecast,
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
from homeassistant.util import dt as dt_util

from . import OpenMeteoDataUpdateCoordinator
from .const import CONDITION_MAP, DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Open-Meteo weather entity based on a config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([OpenMeteoWeather(coordinator, config_entry)])

class OpenMeteoWeather(WeatherEntity):
    """Implementation of an Open-Meteo weather entity."""

    _attr_attribution = "Weather data provided by Open-Meteo"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_pressure_unit = UnitOfPressure.HPA
    _attr_visibility_unit = UnitOfLength.KILOMETERS
    _attr_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_precipitation_unit = UnitOfPrecipitationDepth.MILLIMETERS
    
    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_HOURLY
        | WeatherEntityFeature.FORECAST_DAILY
        | WeatherEntityFeature.WIND_SPEED
        | WeatherEntityFeature.WIND_BEARING
    )

    def __init__(
        self,
        coordinator: OpenMeteoDataUpdateCoordinator,
        config_entry: ConfigEntry
    ) -> None:
        """Initialize the Open-Meteo weather entity."""
        self.coordinator = coordinator
        self._attr_name = config_entry.data.get("name", "Open-Meteo")
        self._attr_unique_id = config_entry.entry_id
        
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
            "name": "Open-Meteo",
            "manufacturer": "Open-Meteo",
        }

    @property
    def condition(self) -> str | None:
        """Return the current condition."""
        weather_code = self.coordinator.data.get("current_weather", {}).get("weathercode")
        if weather_code is None:
            return None
        
        is_day = self.coordinator.data.get("current_weather", {}).get("is_day") == 1
        return self.get_condition(weather_code, is_day)

    def get_condition(self, weather_code: int, is_day: bool) -> str | None:
        """Map weather code to Home Assistant condition."""
        if weather_code in (0, 1) and not is_day:
            return ATTR_CONDITION_CLEAR_NIGHT
        return CONDITION_MAP.get(weather_code)

    @property
    def native_temperature(self) -> float | None:
        """Return the current temperature."""
        return self.coordinator.data.get("current_weather", {}).get("temperature")

    @property
    def native_pressure(self) -> float | None:
        """Return the current pressure."""
        return self.coordinator.data.get("hourly", {}).get("surface_pressure", [None])[0]

    @property
    def native_humidity(self) -> float | None:
        """Return the current humidity."""
        return self.coordinator.data.get("hourly", {}).get("relativehumidity_2m", [None])[0]

    @property
    def native_visibility(self) -> float | None:
        """Return the current visibility in kilometers."""
        v = self.coordinator.data.get("hourly", {}).get("visibility", [None])[0]
        return v / 1000 if isinstance(v, (int, float)) else None

    @property
    def native_wind_speed(self) -> float | None:
        """Return the current wind speed."""
        return self.coordinator.data.get("current_weather", {}).get("windspeed")

    @property
    def wind_bearing(self) -> float | None:
        """Return the current wind bearing."""
        return self.coordinator.data.get("current_weather", {}).get("winddirection")

    @property
    def forecast_hourly(self) -> list[Forecast] | None:
        """Return the hourly forecast."""
        if not self.coordinator.data:
            return None

        hourly = self.coordinator.data.get("hourly")
        forecast_data = []

        if hourly and "time" in hourly:
            for i, time_entry in enumerate(hourly["time"]):
                weather_code = hourly["weathercode"][i]
                is_day = hourly["is_day"][i] == 1
                
                forecast = {
                    ATTR_FORECAST_TIME: time_entry,
                    ATTR_FORECAST_CONDITION: self.get_condition(weather_code, is_day),
                    ATTR_FORECAST_TEMP: hourly["temperature_2m"][i],
                    ATTR_FORECAST_PRECIPITATION: hourly["precipitation"][i],
                }

                if "windspeed_10m" in hourly:
                    forecast[ATTR_FORECAST_WIND_SPEED] = hourly["windspeed_10m"][i]
                if "winddirection_10m" in hourly:
                    forecast[ATTR_FORECAST_WIND_BEARING] = hourly["winddirection_10m"][i]
                if "precipitation_probability" in hourly:
                    forecast[ATTR_FORECAST_PRECIPITATION_PROBABILITY] = hourly["precipitation_probability"][i]
                
                forecast_data.append(forecast)

        return forecast_data
    
    @property
    def forecast_daily(self) -> list[Forecast] | None:
        """Return the daily forecast."""
        if not self.coordinator.data:
            return None

        daily = self.coordinator.data.get("daily")
        forecast_data = []

        if daily and "time" in daily:
            for i, time_entry in enumerate(daily["time"]):
                weather_code = daily["weathercode"][i]
                
                forecast = {
                    ATTR_FORECAST_TIME: time_entry,
                    ATTR_FORECAST_CONDITION: self.get_condition(weather_code, True),
                    ATTR_FORECAST_TEMP: daily["temperature_2m_max"][i],
                    ATTR_FORECAST_TEMP_LOW: daily["temperature_2m_min"][i],
                    ATTR_FORECAST_PRECIPITATION: daily["precipitation_sum"][i],
                }

                if "windspeed_10m_max" in daily:
                    forecast[ATTR_FORECAST_WIND_SPEED] = daily["windspeed_10m_max"][i]
                if "winddirection_10m_dominant" in daily:
                    forecast[ATTR_FORECAST_WIND_BEARING] = daily["winddirection_10m_dominant"][i]

                forecast_data.append(forecast)

        return forecast_data

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Connect to dispatcher listening for entity data notifications."""
        self.async_on_remove(self.coordinator.async_add_listener(self._handle_coordinator_update))