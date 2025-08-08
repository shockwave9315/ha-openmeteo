"""Support for Open-Meteo weather service."""
from __future__ import annotations

from datetime import datetime, timezone
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
        """Return daily forecast with proper local dates (no repeated weekday labels)."""
        if not self.available or "daily" not in self.coordinator.data:
            return []
        daily = self.coordinator.data["daily"]
        times = daily.get("time", []) or []
        if not times:
            return []

        tz = dt_util.get_time_zone(self.hass.config.time_zone)
        parsed = []
        for t in times:
            try:
                if isinstance(t, (int, float)):
                    dtv = datetime.fromtimestamp(t, tz=timezone.utc).astimezone(tz)
                else:
                    if "T" in t:
                        dtv = dt_util.parse_datetime(t) or datetime.fromisoformat(t.replace("Z","+00:00"))
                    else:
                        dtv = dt_util.parse_datetime(f"{t}T12:00:00")
                    if dtv is None:
                        continue
                    if dtv.tzinfo is None:
                        dtv = dtv.replace(tzinfo=tz)
                    dtv = dtv.astimezone(tz)
                dtv = dtv.replace(hour=12, minute=0, second=0, microsecond=0)
                parsed.append(dtv)
            except Exception:
                continue

        if not parsed:
            return []
        max_days = min(len(parsed), 7)
        out = []
        for i in range(max_days):
            fc = {
                ATTR_FORECAST_TIME: parsed[i],
                ATTR_FORECAST_CONDITION: self._get_condition(daily.get("weathercode", [None]*len(parsed))[i], is_day=True),
                ATTR_FORECAST_TEMP: daily.get("temperature_2m_max", [None]*len(parsed))[i],
                ATTR_FORECAST_TEMP_LOW: daily.get("temperature_2m_min", [None]*len(parsed))[i],
                ATTR_FORECAST_PRECIPITATION: daily.get("precipitation_sum", [0]*len(parsed))[i],
            }
            if "windspeed_10m_max" in daily:
                fc[ATTR_FORECAST_WIND_SPEED] = daily["windspeed_10m_max"][i]
            if "winddirection_10m_dominant" in daily:
                fc[ATTR_FORECAST_WIND_BEARING] = daily["winddirection_10m_dominant"][i]
            if "precipitation_probability_max" in daily:
                fc[ATTR_FORECAST_PRECIPITATION_PROBABILITY] = daily["precipitation_probability_max"][i]
            out.append(fc)
        return out


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
        """Return the hourly forecast starting from current/next hour."""
        if not self.available or "hourly" not in self.coordinator.data:
            return []
        hourly = self.coordinator.data["hourly"]
        times = hourly.get("time", []) or []
        if not times:
            return []

        tz = dt_util.get_time_zone(self.hass.config.time_zone)
        parsed_times = []
        for t in times:
            try:
                if isinstance(t, (int, float)):
                    dtv = datetime.fromtimestamp(t, tz=timezone.utc).astimezone(tz)
                else:
                    dtv = dt_util.parse_datetime(t) or datetime.fromisoformat(t.replace("Z","+00:00"))
                    if dtv.tzinfo is None:
                        dtv = dtv.replace(tzinfo=tz)
                    dtv = dtv.astimezone(tz)
                parsed_times.append(dtv)
            except Exception:
                continue
        if not parsed_times:
            return []

        now_local = dt_util.now(tz)
        start_idx = 0
        for i, dtv in enumerate(parsed_times):
            if dtv >= now_local:
                start_idx = i
                break

        def _slice(key):
            arr = hourly.get(key, []) or []
            return arr[start_idx:] if isinstance(arr, list) else []

        is_day_arr = _slice("is_day")
        code_arr = _slice("weathercode")
        temp_arr = _slice("temperature_2m")
        precip_arr = _slice("precipitation")
        prob_arr = _slice("precipitation_probability")
        wind_arr = _slice("windspeed_10m")
        wdir_arr = _slice("winddirection_10m")
        times_arr = parsed_times[start_idx:]

        lens = [len(times_arr), len(temp_arr), len(code_arr)]
        min_len = min([l for l in lens if l > 0]) if any(lens) else 0
        horizon = 48
        max_len = min(min_len, horizon)
        if max_len <= 0:
            return []

        out = []
        for i in range(max_len):
            try:
                t = times_arr[i]
                is_day = bool(is_day_arr[i]) if i < len(is_day_arr) else True
                code = code_arr[i] if i < len(code_arr) else None
                forecast = {
                    ATTR_FORECAST_TIME: t,
                    ATTR_FORECAST_CONDITION: self._get_condition(code, is_day),
                    ATTR_FORECAST_TEMP: temp_arr[i] if i < len(temp_arr) else None,
                    ATTR_FORECAST_PRECIPITATION: precip_arr[i] if i < len(precip_arr) else None,
                }
                if i < len(prob_arr):
                    forecast[ATTR_FORECAST_PRECIPITATION_PROBABILITY] = prob_arr[i]
                if i < len(wind_arr):
                    forecast[ATTR_FORECAST_WIND_SPEED] = wind_arr[i]
                if i < len(wdir_arr):
                    forecast[ATTR_FORECAST_WIND_BEARING] = wdir_arr[i]
                out.append(forecast)
            except Exception:
                continue
        return out


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