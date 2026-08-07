from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.helpers import device_registry as dr

from custom_components.openmeteo.const import (
    CONF_ENABLED_AQ_SENSORS,
    CONF_ENABLED_WEATHER_SENSORS,
    CONF_ENTITY_ID,
    CONF_MIN_TRACK_INTERVAL,
    CONF_MODE,
    CONF_REVERSE_GEOCODE_COOLDOWN_MIN,
    CONF_UPDATE_INTERVAL_MIN,
    DOMAIN,
    MODE_TRACK,
)
from custom_components.openmeteo.identity import CONF_SOURCE_KEY


pytestmark = pytest.mark.asyncio


def _weather_payload(temperature: float) -> dict:
    return {
        "timezone": "Europe/Berlin",
        "current": {
            "temperature_2m": temperature,
            "relative_humidity_2m": 70,
            "apparent_temperature": temperature - 1,
            "pressure_msl": 1023.0,
            "wind_speed_10m": 10.0,
            "wind_direction_10m": 270,
            "wind_gusts_10m": 18.0,
            "weather_code": 2,
            "cloud_cover": 40,
            "is_day": 1,
        },
        "hourly": {},
        "daily": {},
    }


async def test_full_tracking_lifecycle_keeps_entities_while_location_moves(
    hass, enable_custom_integrations
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Open-Meteo: Telefon",
        version=4,
        data={
            CONF_MODE: MODE_TRACK,
            CONF_ENTITY_ID: "device_tracker.phone",
            CONF_SOURCE_KEY: "phone",
            CONF_MIN_TRACK_INTERVAL: 60,
            CONF_UPDATE_INTERVAL_MIN: 10,
            CONF_REVERSE_GEOCODE_COOLDOWN_MIN: 15,
            CONF_ENABLED_WEATHER_SENSORS: ["temperature", "location"],
            CONF_ENABLED_AQ_SENSORS: [],
        },
    )
    entry.add_to_hass(hass)
    hass.states.async_set(
        "device_tracker.phone",
        "not_home",
        {"latitude": 51.5136, "longitude": 7.4653},
    )

    reverse_geocode = AsyncMock(side_effect=["Dortmund, DE", "Osnabrück, DE"])
    weather = AsyncMock(side_effect=[_weather_payload(15.8), _weather_payload(16.4)])
    air_quality = AsyncMock(return_value={})

    with patch(
        "custom_components.openmeteo.Store.async_load",
        new=AsyncMock(return_value={}),
    ), patch(
        "custom_components.openmeteo.Store.async_save",
        new=AsyncMock(),
    ), patch(
        "custom_components.openmeteo.coordinator.async_reverse_geocode",
        new=reverse_geocode,
    ), patch(
        "custom_components.openmeteo.api.OpenMeteoClient.async_weather",
        new=weather,
    ), patch(
        "custom_components.openmeteo.api.OpenMeteoClient.async_air_quality",
        new=air_quality,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        weather_entity_id = "weather.open_meteo_phone"
        temperature_entity_id = "sensor.open_meteo_phone_temperatura"
        location_entity_id = "sensor.open_meteo_phone_lokalizacja"

        assert hass.states.get(weather_entity_id) is not None
        assert hass.states.get(temperature_entity_id) is not None
        location_state = hass.states.get(location_entity_id)
        assert location_state is not None
        assert location_state.state == "Dortmund, DE"
        assert entry.title == "Dortmund, DE"

        registry = dr.async_get(hass)
        device = registry.async_get_device_by_identifier(
            (DOMAIN, entry.entry_id), entry.entry_id
        )
        assert device is not None
        assert device.name == "Dortmund, DE"

        original_entity_ids = {
            weather_entity_id,
            temperature_entity_id,
            location_entity_id,
        }

        # A large jump must immediately refresh the same registered entities.
        hass.states.async_set(
            "device_tracker.phone",
            "not_home",
            {"latitude": 52.2799, "longitude": 8.0472},
        )
        await hass.async_block_till_done()

        moved_location = hass.states.get(location_entity_id)
        assert moved_location is not None
        assert moved_location.state == "Osnabrück, DE"
        assert entry.title == "Osnabrück, DE"
        assert {
            entity_id for entity_id in original_entity_ids if hass.states.get(entity_id)
        } == original_entity_ids
        assert weather.await_count == 2
        assert reverse_geocode.await_count == 2

        coordinator = entry.runtime_data.coordinator
        assert coordinator._tracker_unsub is not None

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

        # HA 2026.8 preserves registry-backed states as unavailable/restored after
        # unload. The lifecycle contract is that no Open-Meteo entity remains
        # active and our tracker/timer callbacks are released.
        for entity_id in original_entity_ids:
            state = hass.states.get(entity_id)
            assert state is not None
            assert state.state == STATE_UNAVAILABLE
        assert coordinator._tracker_unsub is None
        assert coordinator._delayed_refresh_unsub is None
