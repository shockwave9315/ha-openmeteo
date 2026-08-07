from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.openmeteo import async_migrate_entry
from custom_components.openmeteo.const import (
    CONF_ENABLED_AQ_SENSORS,
    CONF_ENABLED_WEATHER_SENSORS,
    CONF_ENTITY_ID,
    CONF_MODE,
    CONF_UPDATE_INTERVAL_MIN,
    DOMAIN,
    MODE_TRACK,
)
from custom_components.openmeteo.identity import CONF_SOURCE_KEY


@pytest.mark.asyncio
async def test_v3_tracking_entry_is_canonicalized_without_city_identity(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Lotte, DE",
        data={
            "tracking_mode": "device",
            "tracked_entity_id": "device_tracker.poco_x8",
            "update_interval": 600,
            "units": "imperial",
            "api_provider": "open_meteo",
            "use_place_as_device_name": True,
            "enabled_sensors": ["temperature", "humidity", "co", "aqi_eu"],
            "pv_old_dead_key": 1,
        },
        options={"options_save_cooldown_sec": 60},
        version=3,
        minor_version=1,
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry)

    assert entry.version == 3
    assert entry.minor_version == 2
    assert entry.title == "Lotte, DE"
    assert entry.data[CONF_MODE] == MODE_TRACK
    assert entry.data[CONF_ENTITY_ID] == "device_tracker.poco_x8"
    assert entry.data[CONF_SOURCE_KEY] == "poco_x8"
    assert entry.data[CONF_UPDATE_INTERVAL_MIN] == 10
    assert entry.data[CONF_ENABLED_WEATHER_SENSORS] == ["temperature", "humidity"]
    assert entry.data[CONF_ENABLED_AQ_SENSORS] == ["co", "aqi_eu"]

    merged = {**dict(entry.data), **dict(entry.options)}
    for removed in (
        "tracking_mode",
        "tracked_entity_id",
        "update_interval",
        "units",
        "api_provider",
        "use_place_as_device_name",
        "enabled_sensors",
        "options_save_cooldown_sec",
        "pv_old_dead_key",
    ):
        assert removed not in merged
