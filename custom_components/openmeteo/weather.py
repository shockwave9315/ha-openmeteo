# SPDX-License-Identifier: Apache-2.0
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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from datetime import datetime
from homeassistant.util import dt as dt_util

from .coordinator import OpenMeteoDataUpdateCoordinator
from .const import (
    CONDITION_MAP,
    DOMAIN,
    CONF_MODE,
    CONF_MIN_TRACK_INTERVAL,
    CONF_API_PROVIDER,
    CONF_ENTITY_ID,
    CONF_TRACKED_ENTITY_ID,
    MODE_STATIC,
    MODE_TRACK,
    DEFAULT_MIN_TRACK_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][config_entry.entry_id]["coordinator"]
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
        data = {**config_entry.data, **config_entry.options}
        mode = data.get(CONF_MODE)
        if not mode:
            mode = (
                MODE_TRACK
                if data.get(CONF_ENTITY_ID) or data.get(CONF_TRACKED_ENTITY_ID)
                else MODE_STATIC
            )
        self._mode = mode
        self._min_track_interval = int(
            data.get(CONF_MIN_TRACK_INTERVAL, DEFAULT_MIN_TRACK_INTERVAL)
        )
        self._provider = coordinator.provider

    @property
    def available(self) -> bool:
        return bool(self.coordinator.data) and getattr(self.coordinator, "last_update_success", True)

    @property
    def name(self) -> str | None:
        base = self._attr_name or "Open-Meteo"
        data = self.coordinator.data or {}
        loc_name = data.get("location_name")
        if loc_name:
            return f"{base} — {loc_name}"
        loc = data.get("location") or {}
        lat = loc.get("latitude")
        lon = loc.get("longitude")
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            return f"{base} — {lat:.5f},{lon:.5f}"
        return base

    @property
    def native_temperature(self) -> float | None:
        """Return the current temperature."""
        cw = self.coordinator.data.get("current_weather", {})
        temp = cw.get("temperature")
        return round(temp, 1) if isinstance(temp, (int, float)) else None

    @property
    def native_pressure(self) -> float | None:
        """Return the current pressure."""
        val = self._hourly_value("pressure_msl")
        return round(val, 1) if isinstance(val, (int, float)) else None

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
        vis = self._hourly_value("visibility")
        return round(vis / 1000, 2) if isinstance(vis, (int, float)) else None

    @property
    def humidity(self) -> int | None:
        """Return the current humidity."""
        hum = self._hourly_value("relative_humidity_2m")
        return round(hum) if isinstance(hum, (int, float)) else None

    @property
    def native_dew_point(self) -> float | None:
        """Return the current dew point."""
        current_dp = self.coordinator.data.get("current", {}).get("dewpoint_2m")
        if isinstance(current_dp, (int, float)):
            return round(current_dp, 1)
        val = self._hourly_value("dewpoint_2m")
        return round(val, 1) if isinstance(val, (int, float)) else None

    @property
    def condition(self) -> str | None:
        """Return the current weather condition."""
        cw = self.coordinator.data.get("current_weather", {})
        weather_code = cw.get("weathercode")
        is_day = cw.get("is_day")
        return _map_condition(weather_code, is_day) if weather_code is not None else None
    
    def _current_hour_index(self) -> int:
        times = self.coordinator.data.get("hourly", {}).get("time") or []
        if not isinstance(times, list):
            return 0
        now = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
        for i, ts in enumerate(times):
            dt = dt_util.parse_datetime(ts)
            if dt and dt_util.as_utc(dt) >= now:
                return i
        return max(len(times) - 1, 0)

    def _hourly_value(self, key: str, idx: int | None = None) -> float | None:
        arr = self.coordinator.data.get("hourly", {}).get(key)
        if not isinstance(arr, list) or not arr:
            return None
        if idx is None:
            idx = self._current_hour_index()
        if idx < len(arr):
            return arr[idx]
        return None

    def _map_daily_forecast(self) -> list[dict[str, Any]]:
        if not (daily := self.coordinator.data.get("daily")):
            return []
        
        times = daily.get("time", [])
        temp_max = daily.get("temperature_2m_max", [])
        temp_min = daily.get("temperature_2m_min", [])
        wcodes = daily.get("weathercode", [])
        precip_sum = daily.get("precipitation_sum", [])
        ws_max = daily.get("wind_speed_10m_max", [])
        wd_dom = daily.get("wind_direction_10m_dominant", [])
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


    @property
    def forecast_daily(self) -> list[dict[str, Any]]:
        return self._map_daily_forecast()

    async def async_forecast_daily(self) -> list[dict[str, Any]]:
        return self.forecast_daily

    async def async_forecast_hourly(self) -> list[dict[str, Any]]:
        hourly = self.coordinator.data.get("hourly") or {}
        times = hourly.get("time") or []
        if not isinstance(times, list) or not times:
            _LOGGER.debug("Hourly forecast: 0 entries")
            return []

        idx = self._current_hour_index()
        end = min(len(times), idx + 72)
        result: list[dict[str, Any]] = []
        for i in range(idx, end):
            ts = times[i]
            dt = dt_util.parse_datetime(ts)
            if not dt:
                continue
            dt_local = dt_util.as_local(dt)
            item: dict[str, Any] = {"datetime": dt_local.isoformat()}
            for out_key, src_key in {
                "temperature": "temperature_2m",
                "dew_point": "dewpoint_2m",
                "humidity": "relative_humidity_2m",
                "pressure": "pressure_msl",
                "wind_speed": "wind_speed_10m",
                "wind_bearing": "wind_direction_10m",
                "wind_gust_speed": "wind_gusts_10m",
                "precipitation": "precipitation",
                "precipitation_probability": "precipitation_probability",
                "cloud_coverage": "cloud_cover",
            }.items():
                arr = hourly.get(src_key)
                item[out_key] = arr[i] if isinstance(arr, list) and i < len(arr) else None
            wcodes = hourly.get("weathercode")
            if isinstance(wcodes, list) and i < len(wcodes):
                is_day_arr = hourly.get("is_day", [])
                is_day_val = is_day_arr[i] if isinstance(is_day_arr, list) and i < len(is_day_arr) else 1
                item["condition"] = _map_condition(wcodes[i], is_day_val)
            else:
                item["condition"] = None
            result.append(item)

        missing = sorted({k for f in result for k, v in f.items() if v is None})
        if result:
            _LOGGER.debug(
                "Hourly forecast: %d entries from %s to %s; missing fields: %s",
                len(result),
                result[0]["datetime"],
                result[-1]["datetime"],
                ", ".join(missing) if missing else "none",
            )
        else:
            _LOGGER.debug("Hourly forecast: 0 entries")
        return result

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.coordinator.async_add_listener(self._handle_coordinator_update))

    @property
    def sunrise(self) -> datetime | None:
        val = self.coordinator.data.get("daily", {}).get("sunrise", [None])[0]
        if isinstance(val, str):
            dt = dt_util.parse_datetime(val)
        else:
            dt = val
        if not dt:
            return None
        if dt.tzinfo is None:
            tz = dt_util.get_time_zone(self.hass.config.time_zone) or dt_util.UTC
            dt = dt.replace(tzinfo=tz)
        return dt_util.as_utc(dt)

    @property
    def sunset(self) -> datetime | None:
        val = self.coordinator.data.get("daily", {}).get("sunset", [None])[0]
        if isinstance(val, str):
            dt = dt_util.parse_datetime(val)
        else:
            dt = val
        if not dt:
            return None
        if dt.tzinfo is None:
            tz = dt_util.get_time_zone(self.hass.config.time_zone) or dt_util.UTC
            dt = dt.replace(tzinfo=tz)
        return dt_util.as_utc(dt)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = dict(super().extra_state_attributes or {})
        data = self.coordinator.data or {}
        loc = data.get("location") or {}
        attrs.update(
            {
                "location_name": data.get("location_name"),
                "mode": self._mode,
                "min_track_interval": self._min_track_interval,
                "last_location_update": data.get("last_location_update"),
                "provider": self._provider,
            }
        )
        dp = self.native_dew_point
        if dp is not None:
            attrs["dew_point"] = dp
        if "latitude" not in attrs:
            attrs["latitude"] = loc.get("latitude")
        if "longitude" not in attrs:
            attrs["longitude"] = loc.get("longitude")
        return attrs
