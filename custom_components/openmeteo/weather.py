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
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_precipitation_unit = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_native_visibility_unit = UnitOfLength.KILOMETERS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_DAILY | WeatherEntityFeature.FORECAST_HOURLY
    )

    def __init__(self, coordinator: OpenMeteoDataUpdateCoordinator, config_entry: ConfigEntry) -> None:
        """Initialize the Open-Meteo weather."""
        self.coordinator = coordinator
        self._attr_name = config_entry.data.get("name", "Open-Meteo")
        self._attr_unique_id = f"{config_entry.entry_id}-weather"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
            "name": "Open-Meteo",
            "manufacturer": "Open-Meteo",
        }
        self._attr_should_poll = False

    @property
    def available(self) -> bool:
        """Return if weather data is available."""
        return self.coordinator.last_update_success

    @property
    def condition(self) -> str | None:
        """Return the current condition."""
        if not self.available or "current_weather" not in self.coordinator.data:
            return None
        
        is_day = self.coordinator.data["current_weather"].get("is_day", 1) == 1
        weather_code = self.coordinator.data["current_weather"].get("weathercode")
        return self._get_condition(weather_code, is_day)

    @property
    def native_temperature(self) -> float | None:
        """Return the temperature."""
        if not self.available or "current_weather" not in self.coordinator.data:
            return None
        return self.coordinator.data["current_weather"].get("temperature")

    @property
    def native_pressure(self) -> float | None:
        """Return the pressure."""
        if not self.available or "hourly" not in self.coordinator.data:
            return None
        return self.coordinator.data["hourly"].get("surface_pressure", [None])[0]

    @property
    def humidity(self) -> float | None:
        """Return the humidity."""
        if not self.available or "hourly" not in self.coordinator.data:
            return None
        return self.coordinator.data["hourly"].get("relativehumidity_2m", [None])[0]

    @property
    def native_wind_speed(self) -> float | None:
        """Return the wind speed."""
        if not self.available or "current_weather" not in self.coordinator.data:
            return None
        return self.coordinator.data["current_weather"].get("windspeed")

    @property
    def wind_bearing(self) -> float | None:
        """Return the wind bearing."""
        if not self.available or "current_weather" not in self.coordinator.data:
            return None
        return self.coordinator.data["current_weather"].get("winddirection")

    @property
    def native_visibility(self) -> float | None:
        """Return the visibility."""
        if not self.available or "hourly" not in self.coordinator.data:
            return None
        return self.coordinator.data["hourly"].get("visibility", [None])[0]

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
            if i >= 7:  # Limit to 7 days
                break

            # The API returns a date string, but we need a datetime object for HA.
            # We'll assume noon for the forecast time.
            forecast_time = dt_util.parse_datetime(f"{time_entry}T12:00:00")
            forecast = {
                ATTR_FORECAST_TIME: forecast_time,
                ATTR_FORECAST_CONDITION: self._get_condition(
                    daily.get("weathercode", [None] * len(time_entries))[i],
                    is_day=True  # Daily forecast always assumes day
                ),
                ATTR_FORECAST_TEMP: daily.get("temperature_2m_max", [None] * len(time_entries))[i],
                ATTR_FORECAST_TEMP_LOW: daily.get("temperature_2m_min", [None] * len(time_entries))[i],
                ATTR_FORECAST_PRECIPITATION: daily.get("precipitation_sum", [0] * len(time_entries))[i],
            }

            if "windspeed_10m_max" in daily and "winddirection_10m_dominant" in daily:
                forecast[ATTR_FORECAST_WIND_SPEED] = daily["windspeed_10m_max"][i]
                forecast[ATTR_FORECAST_WIND_BEARING] = daily["winddirection_10m_dominant"][i]

            if "precipitation_probability_max" in daily:
                forecast[ATTR_FORECAST_PRECIPITATION_PROBABILITY] = daily["precipitation_probability_max"][i]

            forecast_data.append(forecast)

        return forecast_data

    def _get_condition(self, weather_code: int | None, is_day: bool = True) -> str | None:
        """Return the condition from weather code."""
        if weather_code is None:
            return None

        # Handle the unique case for clear sky first, which has a distinct night state
        if weather_code == 0:
            return "sunny" if is_day else "clear-night"

        # For all other codes, rely on the CONDITION_MAP.
        # The frontend will handle showing the correct day/night icon automatically
        # based on the sun's state and this base condition.
        return CONDITION_MAP.get(weather_code)

    @property
    def forecast_hourly(self) -> list[dict[str, Any]]:
        """Return the hourly forecast in the format required by the UI."""
        if not self.available or "hourly" not in self.coordinator.data:
            return []

        hourly = self.coordinator.data["hourly"]
        time_entries = hourly.get("time", [])
        forecast_data = []

        for i, time_entry in enumerate(time_entries):
            if i >= 24:  # Limit to 24 hours
                break

            is_day = hourly.get("is_day", [1] * len(time_entries))[i] == 1
            weather_code = hourly.get("weathercode", [None] * len(time_entries))[i]
            
            forecast = {
                ATTR_FORECAST_TIME: dt_util.parse_datetime(time_entry),
                ATTR_FORECAST_CONDITION: self._get_condition(weather_code, is_day),
                ATTR_FORECAST_TEMP: hourly.get("temperature_2m", [None] * len(time_entries))[i],
                ATTR_FORECAST_PRECIPITATION: hourly.get("precipitation", [0] * len(time_entries))[i],
            }

            if "windspeed_10m" in hourly and "winddirection_10m" in hourly:
                forecast[ATTR_FORECAST_WIND_SPEED] = hourly["windspeed_10m"][i]
                forecast[ATTR_FORECAST_WIND_BEARING] = hourly["winddirection_10m"][i]

            if "precipitation_probability" in hourly:
                forecast[ATTR_FORECAST_PRECIPITATION_PROBABILITY] = hourly["precipitation_probability"][i]

            forecast_data.append(forecast)

        return forecast_data

    # These async forecast methods are for newer HA versions and call the properties
    async def async_forecast_daily(self) -> list[dict[str, Any]]:
        """Return the daily forecast."""
        return self.forecast_daily

    async def async_forecast_hourly(self) -> list[dict[str, Any]]:
        """Return the hourly forecast."""
        return self.forecast_hourly

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Connect to dispatcher listening for entity data notifications."""
        self.async_on_remove(
            self.coordinator.async_add_listener(self._handle_coordinator_update)
        )