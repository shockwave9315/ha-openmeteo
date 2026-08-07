from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.helpers import entity_registry as er

from custom_components.openmeteo import async_migrate_entry
from custom_components.openmeteo.const import DOMAIN
from custom_components.openmeteo.identity import sensor_unique_id, weather_unique_id


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


async def test_migration_moves_v1_last_position_out_of_config_entry(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Lotte, DE",
        version=3,
        data={
            "tracking_mode": "device",
            "tracked_entity_id": "device_tracker.poco_x8",
            "last_lat": 52.314,
            "last_lon": 7.872,
            "last_location_name": "Lotte, DE",
        },
        # V1 gave options precedence over data; preserve that behavior once.
        options={
            "last_lat": 52.315,
            "last_lon": 7.873,
            "last_location_name": "Lotte override, DE",
        },
    )
    entry.add_to_hass(hass)

    save = AsyncMock()
    with patch("custom_components.openmeteo.Store.async_save", new=save):
        assert await async_migrate_entry(hass, entry)

    save.assert_awaited_once_with(
        {
            "latitude": 52.315,
            "longitude": 7.873,
            "location_name": "Lotte override, DE",
        }
    )
    merged = {**dict(entry.data), **dict(entry.options)}
    assert "last_lat" not in merged
    assert "last_lon" not in merged
    assert "last_location_name" not in merged


async def test_v1_registry_ids_survive_v2_upgrade_and_location_move(
    hass, enable_custom_integrations
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Lotte, DE",
        version=3,
        data={
            "tracking_mode": "device",
            "tracked_entity_id": "device_tracker.phone",
            "update_interval": 600,
            "enabled_sensors": ["temperature", "location"],
            "last_lat": 52.314,
            "last_lon": 7.872,
            "last_location_name": "Lotte, DE",
        },
    )
    entry.add_to_hass(hass)

    registry = er.async_get(hass)

    old_weather = registry.async_get_or_create(
        "weather",
        DOMAIN,
        weather_unique_id(entry.entry_id),
        config_entry=entry,
        suggested_object_id="open_meteo_2",
    )
    old_weather = registry.async_update_entity(
        old_weather.entity_id, new_entity_id="weather.open_meteo_2"
    )

    old_temperature = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        sensor_unique_id(entry.entry_id, "temperature"),
        config_entry=entry,
        suggested_object_id="temperatura_2",
    )
    old_temperature = registry.async_update_entity(
        old_temperature.entity_id, new_entity_id="sensor.temperatura_2"
    )

    old_location = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        sensor_unique_id(entry.entry_id, "location"),
        config_entry=entry,
        suggested_object_id="lokalizacja_2",
    )
    old_location = registry.async_update_entity(
        old_location.entity_id, new_entity_id="sensor.lokalizacja_2"
    )

    legacy_ids = {
        old_weather.entity_id,
        old_temperature.entity_id,
        old_location.entity_id,
    }

    hass.states.async_set(
        "device_tracker.phone",
        "not_home",
        {"latitude": 51.5136, "longitude": 7.4653},
    )

    reverse_geocode = AsyncMock(side_effect=["Dortmund, DE", "Osnabrück, DE"])
    weather = AsyncMock(side_effect=[_weather_payload(15.8), _weather_payload(16.4)])

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
        new=AsyncMock(return_value={}),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert entry.version == 4
        for entity_id in legacy_ids:
            assert hass.states.get(entity_id) is not None

        # Fresh-v2 suggestions must not create duplicates when an old unique_id
        # already exists in the registry.
        assert hass.states.get("weather.open_meteo_phone") is None
        assert hass.states.get("sensor.open_meteo_phone_temperatura") is None
        assert hass.states.get("sensor.open_meteo_phone_lokalizacja") is None
        location_state = hass.states.get(old_location.entity_id)
        assert location_state is not None
        assert location_state.state == "Dortmund, DE"

        before_registry_ids = {
            entity.entity_id
            for entity in registry.entities.values()
            if entity.platform == DOMAIN and entity.config_entry_id == entry.entry_id
        }
        assert before_registry_ids == legacy_ids

        hass.states.async_set(
            "device_tracker.phone",
            "not_home",
            {"latitude": 52.2799, "longitude": 8.0472},
        )
        await hass.async_block_till_done()

        location_state = hass.states.get(old_location.entity_id)
        assert location_state is not None
        assert location_state.state == "Osnabrück, DE"
        after_registry_ids = {
            entity.entity_id
            for entity in registry.entities.values()
            if entity.platform == DOMAIN and entity.config_entry_id == entry.entry_id
        }
        assert after_registry_ids == legacy_ids
        assert weather.await_count == 2

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
