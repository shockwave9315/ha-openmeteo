"""Open-Meteo weather entity (stable entity_id, dynamic city display name)."""
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
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .coordinator import OpenMeteoDataUpdateCoordinator
from .const import (
    CONDITION_MAP,
    DOMAIN,
    CONF_MODE,
    CONF_MIN_TRACK_INTERVAL,
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
    stored = hass.data[DOMAIN][config_entry.entry_id]
    coordinator: OpenMeteoDataUpdateCoordinator = (
        stored.get("coordinator") if isinstance(stored, dict) else stored
    )
    async_add_entities([OpenMeteoWeather(coordinator, config_entry)])


def _map_condition(weather_code: int | None, is_day: int | None = 1) -> str | None:
    if weather_code is None:
        return None
    if weather_code in (0, 1) and is_day == 0:
        return "clear-night"
    return CONDITION_MAP.get(weather_code)


class OpenMeteoWeather(CoordinatorEntity[OpenMeteoDataUpdateCoordinator], WeatherEntity):
    """Open-Meteo weather entity with stable entity_id and dynamic city name."""

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
        super().__init__(coordinator)
        self._config_entry = config_entry

        # Stable entity_id base. HA will assign weather.open_meteo, weather.open_meteo_2, ...
        self._attr_suggested_object_id = "open_meteo"
        self._attr_unique_id = f"{config_entry.entry_id}-weather"
        # Do NOT derive entity_id from display name
        self._attr_has_entity_name = False

        # Device metadata
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
            "name": "Open-Meteo",
            "manufacturer": "Open-Meteo",
        }

        # Mode metadata
        opts = {**config_entry.data, **config_entry.options}
        mode = opts.get(CONF_MODE)
        if not mode:
            mode = (
                MODE_TRACK
                if opts.get(CONF_ENTITY_ID) or opts.get(CONF_TRACKED_ENTITY_ID)
                else MODE_STATIC
            )
        self._mode = mode
        self._min_track_interval = int(
            opts.get(CONF_MIN_TRACK_INTERVAL, DEFAULT_MIN_TRACK_INTERVAL)
        )

    # -------- Dynamic display name (ALWAYS city) --------
    @property
    def name(self) -> str | None:
        # 1) Prefer reverse geocode from coordinator
        place = getattr(self.coordinator, "location_name", None)
        if isinstance(place, str) and place.strip():
            return place.strip()
        # 2) Fallback to last saved name in entry options (coordinator should store it)
        opts = {**self._config_entry.data, **self._config_entry.options}
        place = opts.get("last_location_name")
        if isinstance(place, str) and place.strip():
            return place.strip()
        # 3) Fallback to the entry title or generic
        title = (self._config_entry.title or "").strip()
        return title or "Open-Meteo"

    # -------- BASIC METRICS --------
    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def native_temperature(self) -> float | None:
        cw = self.coordinator.data.get("current_weather", {}) if self.coordinator.data else {}
        temp = cw.get("temperature")
        return round(temp, 1) if isinstance(temp, (int, float)) else None

    @property
    def native_pressure(self) -> float | None:
        val = self._hourly_value("pressure_msl")
        return round(val, 1) if isinstance(val, (int, float)) else None

    @property
    def native_wind_speed(self) -> float | None:
        cw = self.coordinator.data.get("current_weather", {}) if self.coordinator.data else {}
        ws = cw.get("windspeed")
        return round(ws, 1) if isinstance(ws, (int, float)) else None

    @property
    def wind_bearing(self) -> float | None:
        cw = self.coordinator.data.get("current_weather", {}) if self.coordinator.data else {}
        wb = cw.get("winddirection")
        return round(wb, 1) if isinstance(wb, (int, float)) else None

    @property
    def native_visibility(self) -> float | None:
        vis = self._hourly_value("visibility")
        return round(vis / 1000, 2) if isinstance(vis, (int, float)) else None

    @property
    def humidity(self) -> int | None:
        hum = self._hourly_value("relative_humidity_2m")
        return round(hum) if isinstance(hum, (int, float)) else None

    @property
    def native_dew_point(self) -> float | None:
        current_dp = (self.coordinator.data or {}).get("current", {}).get("dewpoint_2m")
        if isinstance(current_dp, (int, float)):
            return round(current_dp, 1)
        val = self._hourly_value("dewpoint_2m")
        return round(val, 1) if isinstance(val, (int, float)) else None

    @property
    def condition(self) -> str | None:
        cw = self.coordinator.data.get("current_weather", {}) if self.coordinator.data else {}
        weather_code = cw.get("weathercode")
        is_day = cw.get("is_day")
        return _map_condition(weather_code, is_day) if weather_code is not None else None

    # -------- FORECAST HELPERS --------
    def _current_hour_index(self) -> int:
        hourly = (self.coordinator.data or {}).get("hourly") or {}
        times = hourly.get("time") or []
        if not isinstance(times, list) or not times:
            return 0
        now = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
        for i, ts in enumerate(times):
            dt = dt_util.parse_datetime(ts)
            if dt and dt_util.as_utc(dt) >= now:
                return i
        return max(len(times) - 1, 0)

    def _hourly_value(self, key: str, idx: int | None = None) -> float | None:
        hourly = (self.coordinator.data or {}).get("hourly") or {}
        arr = hourly.get(key)
        if not isinstance(arr, list) or not arr:
            return None
        if idx is None:
            idx = self._current_hour_index()
        if idx < len(arr):
            return arr[idx]
        return None

    def _map_daily_forecast(self) -> list[dict[str, Any]]:
        daily = (self.coordinator.data or {}).get("daily") or {}
        times = daily.get("time") or []
        if not times:
            return []

        temp_max = daily.get("temperature_2m_max", [])
        temp_min = daily.get("temperature_2m_min", [])
        wcodes = daily.get("weathercode", [])
        precip_sum = daily.get("precipitation_sum", [])
        ws_max = daily.get("wind_speed_10m_max", [])
        wd_dom = daily.get("wind_direction_10m_dominant", [])
        pop = daily.get("precipitation_probability_max", [])

        out: list[dict[str, Any]] = []
        for i, ts in enumerate(times):
            forecast = {
                ATTR_FORECAST_TIME: ts,
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

    # -------- FORECAST PROPERTIES --------
    @property
    def forecast_daily(self) -> list[dict[str, Any]]:
        return self._map_daily_forecast()

    async def async_forecast_daily(self) -> list[dict[str, Any]]:
        return self.forecast_daily

    async def async_forecast_hourly(self) -> list[dict[str, Any]]:
        hourly = (self.coordinator.data or {}).get("hourly") or {}
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

        return result

    # -------- UPDATE HANDLERS --------
    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        # update state on data refresh
        self.async_on_remove(self.coordinator.async_add_listener(self._handle_coordinator_update))
        # update name instantly when place changes (signal sent by helpers.maybe_update_device_name / coordinator)
        signal = f"openmeteo_place_updated_{self._config_entry.entry_id}"
        self.async_on_remove(async_dispatcher_connect(self.hass, signal, self._handle_coordinator_update))
