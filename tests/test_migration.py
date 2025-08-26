from pathlib import Path
import sys

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.mark.asyncio
@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_entity_registry_migration(expected_lingering_timers):
    from pytest_homeassistant_custom_component.common import (
        MockConfigEntry,
        async_test_home_assistant,
    )
    from homeassistant.helpers import entity_registry as er
    from custom_components.openmeteo import _migrate_entity_registry
    from custom_components.openmeteo.const import DOMAIN, CONF_MODE, MODE_STATIC
    from homeassistant.util import dt as dt_util
    from unittest.mock import patch

    with patch("homeassistant.util.dt.get_time_zone", return_value=dt_util.UTC):
        async with async_test_home_assistant() as hass:
            entry = MockConfigEntry(
                domain=DOMAIN,
                data={CONF_MODE: MODE_STATIC},
                options={},
                title="X",
            )
            entry.add_to_hass(hass)
            registry = er.async_get(hass)
            sensor_entry = registry.async_get_or_create(
                "sensor",
                DOMAIN,
                "legacy_uv",
                suggested_object_id="indeks_uv_castrop_rauxel_de",
                config_entry=entry,
            )
            weather_entry = registry.async_get_or_create(
                "weather",
                DOMAIN,
                "legacy_weather",
                suggested_object_id="open_meteo_castrop_rauxel_de",
                config_entry=entry,
            )
            old_sensor_id = sensor_entry.id
            old_weather_id = weather_entry.id

            await _migrate_entity_registry(hass, entry)

            new_sensor = registry.async_get("sensor.open_meteo_uv_index")
            assert new_sensor is not None
            assert new_sensor.id == old_sensor_id
            assert new_sensor.unique_id == f"{entry.entry_id}_uv_index"
            new_weather = registry.async_get("weather.open_meteo")
            assert new_weather is not None
            assert new_weather.id == old_weather_id
            assert new_weather.unique_id == f"{entry.entry_id}_weather"
            await hass.async_stop()
