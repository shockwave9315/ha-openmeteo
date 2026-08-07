from __future__ import annotations

from datetime import timedelta

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components.weather import (
    ATTR_FORECAST_NATIVE_PRECIPITATION,
    ATTR_FORECAST_NATIVE_TEMP,
    ATTR_FORECAST_NATIVE_WIND_SPEED,
    ATTR_FORECAST_TEMP,
)
from homeassistant.util import dt as dt_util

from custom_components.openmeteo.const import DOMAIN
from custom_components.openmeteo.coordinator import OpenMeteoDataUpdateCoordinator
from custom_components.openmeteo.weather import OpenMeteoWeather


class FakeStore:
    async def async_save(self, data):
        return None


@pytest.mark.asyncio
async def test_weather_forecasts_use_native_ha_2026_fields(hass) -> None:
    entry = MockConfigEntry(domain=DOMAIN, title="Dortmund, DE", data={})
    entry.add_to_hass(hass)
    coordinator = OpenMeteoDataUpdateCoordinator(hass, entry, FakeStore(), {})

    now = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    next_hour = now + timedelta(hours=1)
    tomorrow = now + timedelta(days=1)
    coordinator.data = {
        "timezone": "UTC",
        "location_name": "Dortmund, DE",
        "current": {
            "temperature_2m": 15.8,
            "apparent_temperature": 14.9,
            "pressure_msl": 1023.8,
            "relative_humidity_2m": 70,
            "wind_speed_10m": 12.0,
            "wind_gusts_10m": 20.0,
            "wind_direction_10m": 269,
            "weather_code": 2,
            "is_day": 1,
            "cloud_cover": 45,
        },
        "hourly": {
            "time": [now.isoformat(), next_hour.isoformat()],
            "temperature_2m": [15.8, 16.2],
            "apparent_temperature": [14.9, 15.3],
            "dew_point_2m": [10.0, 10.2],
            "relative_humidity_2m": [70, 68],
            "pressure_msl": [1023.8, 1023.2],
            "wind_speed_10m": [12.0, 13.0],
            "wind_direction_10m": [269, 270],
            "wind_gusts_10m": [20.0, 21.0],
            "precipitation": [0.0, 0.1],
            "precipitation_probability": [5, 10],
            "cloud_cover": [45, 50],
            "uv_index": [0.1, 0.2],
            "weather_code": [2, 2],
            "is_day": [1, 1],
            "visibility": [10000, 10000],
        },
        "daily": {
            "time": [tomorrow.date().isoformat()],
            "temperature_2m_max": [24.9],
            "temperature_2m_min": [15.1],
            "apparent_temperature_max": [24.0],
            "weather_code": [2],
            "precipitation_sum": [1.2],
            "precipitation_probability_max": [30],
            "wind_speed_10m_max": [25.0],
            "wind_direction_10m_dominant": [270],
            "uv_index_max": [5.5],
        },
    }
    coordinator.last_update_success = True

    entity = OpenMeteoWeather(coordinator, entry, "phone")
    hourly = await entity.async_forecast_hourly()
    daily = await entity.async_forecast_daily()

    assert hourly
    assert ATTR_FORECAST_NATIVE_TEMP in hourly[0]
    assert ATTR_FORECAST_NATIVE_PRECIPITATION in hourly[0]
    assert ATTR_FORECAST_NATIVE_WIND_SPEED in hourly[0]
    assert ATTR_FORECAST_TEMP not in hourly[0]

    assert daily
    assert ATTR_FORECAST_NATIVE_TEMP in daily[0]
    assert ATTR_FORECAST_NATIVE_PRECIPITATION in daily[0]
    assert ATTR_FORECAST_NATIVE_WIND_SPEED in daily[0]

    assert entity.native_temperature == 15.8
    assert entity.native_apparent_temperature == 14.9
    assert entity.native_wind_gust_speed == 20.0
    assert entity.cloud_coverage == 45

    await coordinator.async_shutdown()
