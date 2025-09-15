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
from homeassistant.helpers import device_registry as dr
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
from .helpers import hourly_at_now as _hourly_at_now, hourly_index_at_now

from .coordinator import OpenMeteoDataUpdateCoordinator
from .helpers import maybe_update_device_name
from .const import (
    CONDITION_MAP,
    DOMAIN,
    CONF_MODE,
    CONF_MIN_TRACK_INTERVAL,
    CONF_API_PROVIDER,
    CONF_ENTITY_ID,
    CONF_TRACKED_ENTITY_ID,
    CONF_USE_PLACE_AS_DEVICE_NAME,
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
        
    def _update_device_name(self) -> None:
        """Update the device name based on location if enabled in options."""
        if not hasattr(self, 'hass') or not hasattr(self, '_config_entry'):
            return
        if not self._config_entry.options.get(CONF_USE_PLACE_AS_DEVICE_NAME, True):
            return
        loc = (self.coordinator.data or {}).get("location_name")
        if loc:
            self.hass.async_create_task(
                maybe_update_device_name(self.hass, self._config_entry, loc)
            )
        
    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self._update_device_name()
        
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_device_name()
        self.async_write_ha_state()


    def __init__(
        self, coordinator: OpenMeteoDataUpdateCoordinator, config_entry: ConfigEntry
    ) -> None:
        """Initialize the weather entity."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        # Stabilne entity_id przy pierwszym utworzeniu (np. weather.pogoda)
        self._attr_suggested_object_id = "pogoda"
        self._attr_unique_id = f"{config_entry.entry_id}-weather"
        self._attr_has_entity_name = True
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
    def name(self) -> str:
        """Return the display name of the weather entity (location).

        Order of preference:
        1) user-defined device name,
        2) reverse-geocoded place name (from coordinator.data["location_name"]),
        3) device name,
        4) entry title,
        5) fallback.
        This matches tests that expect Radłów even before device rename has propagated.
        """
        try:
            dev = dr.async_get(self.hass).async_get_device(
                identifiers={(DOMAIN, self._config_entry.entry_id)}
            )
            if dev:
                return (
                    dev.name_by_user
                    or (self.coordinator.data or {}).get("location_name")
                    or dev.name
                    or self._config_entry.title
                    or getattr(self, "_attr_name", None)
                    or "Open-Meteo"
                )
        except Exception:
            pass
        return (
            (self.coordinator.data or {}).get("location_name")
            or self._config_entry.title
            or getattr(self, "_attr_name", None)
            or "Open-Meteo"
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.data:
            return False
        return self.coordinator.last_update_success

    @property
    def native_temperature(self) -> float | None:
        """Return the current temperature."""
        cw = self.coordinator.data.get("current_weather", {})
        temp = cw.get("temperature")
        return round(temp, 1) if isinstance(temp, (int, float)) else None

    @property
    def native_pressure(self) -> float | None:
        """Return the current pressure."""
        val = _hourly_at_now(self.coordinator.data, "pressure_msl")
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
        vis = _hourly_at_now(self.coordinator.data, "visibility")
        return round(vis / 1000, 2) if isinstance(vis, (int, float)) else None

    @property
    def humidity(self) -> int | None:
        """Return the current humidity."""
        hum = _hourly_at_now(self.coordinator.data, "relative_humidity_2m")
        return round(hum) if isinstance(hum, (int, float)) else None

    @property
    def native_dew_point(self) -> float | None:
        """Return the current dew point."""
        current_dp = self.coordinator.data.get("current", {}).get("dewpoint_2m")
        if isinstance(current_dp, (int, float)):
            return round(current_dp, 1)
        val = _hourly_at_now(self.coordinator.data, "dewpoint_2m")
        return round(val, 1) if isinstance(val, (int, float)) else None

    @property
    def condition(self) -> str | None:
        """Return the current weather condition."""
        cw = self.coordinator.data.get("current_weather", {})
        weather_code = cw.get("weathercode")
        is_day = cw.get("is_day")
        return _map_condition(weather_code, is_day) if weather_code is not None else None

def 
_map_daily_forecast(self) -> list[dict[str, Any]]:
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

        idx = hourly_index_at_now(self.coordinator.data)
        if idx is None:
            _LOGGER.debug("Hourly forecast: index not found")
            return []
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
        """Return additional state attributes."""
        attrs = {
            "location_name": self.coordinator.data.get("location_name"),
            "mode": self._mode,
            "min_track_interval": self._min_track_interval,
            "last_location_update": self.coordinator.data.get("last_location_update"),
            "provider": self._provider,
        }
        dp = self.native_dew_point
        if dp is not None:
            attrs["dew_point"] = dp
        return attrs
