from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.openmeteo import async_migrate_entry
from custom_components.openmeteo.const import CONF_ENTITY_ID, CONF_MODE, DOMAIN, MODE_TRACK
from custom_components.openmeteo.identity import CONF_SOURCE_KEY


@pytest.mark.asyncio
async def test_v3_tracking_entry_gets_stable_source_key(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Lotte, DE",
        data={CONF_MODE: MODE_TRACK, CONF_ENTITY_ID: "device_tracker.poco_x8"},
        version=3,
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry)
    assert entry.version == 4
    assert entry.data[CONF_SOURCE_KEY] == "poco_x8"
