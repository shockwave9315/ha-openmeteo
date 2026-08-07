from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.openmeteo.const import (
    CONF_ENABLED_AQ_SENSORS,
    CONF_ENABLED_SENSORS,
    CONF_ENABLED_WEATHER_SENSORS,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_MODE,
    DOMAIN,
    MODE_STATIC,
)
from custom_components.openmeteo.coordinator import OpenMeteoDataUpdateCoordinator


class FakeStore:
    async def async_save(self, data) -> None:
        return None


def _entry(data: dict) -> MockConfigEntry:
    return MockConfigEntry(domain=DOMAIN, title="Test", version=4, data=data)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("selection", "expected"),
    [
        ({CONF_ENABLED_WEATHER_SENSORS: ["temperature"], CONF_ENABLED_AQ_SENSORS: []}, False),
        ({CONF_ENABLED_WEATHER_SENSORS: ["temperature"], CONF_ENABLED_AQ_SENSORS: ["pm10"]}, True),
        ({CONF_ENABLED_SENSORS: ["temperature"]}, False),
        ({CONF_ENABLED_SENSORS: ["temperature", "pm10"]}, True),
        ({}, True),
    ],
)
async def test_air_quality_endpoint_policy(hass, selection: dict, expected: bool) -> None:
    data = {
        CONF_MODE: MODE_STATIC,
        CONF_LATITUDE: 51.0,
        CONF_LONGITUDE: 7.0,
        **selection,
    }
    entry = _entry(data)
    entry.add_to_hass(hass)
    coordinator = OpenMeteoDataUpdateCoordinator(
        hass,
        entry,
        FakeStore(),
        {"latitude": 51.0, "longitude": 7.0, "location_name": "Test, DE"},
    )
    assert coordinator._air_quality_enabled() is expected
    await coordinator.async_shutdown()


@pytest.mark.asyncio
async def test_update_skips_air_quality_request_when_disabled(hass) -> None:
    entry = _entry(
        {
            CONF_MODE: MODE_STATIC,
            CONF_LATITUDE: 51.0,
            CONF_LONGITUDE: 7.0,
            CONF_ENABLED_WEATHER_SENSORS: ["temperature"],
            CONF_ENABLED_AQ_SENSORS: [],
        }
    )
    entry.add_to_hass(hass)
    coordinator = OpenMeteoDataUpdateCoordinator(
        hass,
        entry,
        FakeStore(),
        {"latitude": 51.0, "longitude": 7.0, "location_name": "Test, DE"},
    )
    coordinator._client.async_weather = AsyncMock(
        return_value={"current": {}, "hourly": {}, "daily": {}}
    )
    coordinator._client.async_air_quality = AsyncMock(return_value={"hourly": {}})

    await coordinator._async_update_data()

    coordinator._client.async_weather.assert_awaited_once_with(51.0, 7.0)
    coordinator._client.async_air_quality.assert_not_awaited()
    await coordinator.async_shutdown()
