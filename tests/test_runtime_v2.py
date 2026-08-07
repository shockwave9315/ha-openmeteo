from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.openmeteo import async_update_entry
from custom_components.openmeteo.const import CONF_MODE, DOMAIN, MODE_TRACK
from custom_components.openmeteo.runtime import OpenMeteoRuntimeData, config_signature


class FakeStore:
    pass


@pytest.mark.asyncio
async def test_title_only_location_change_does_not_reload_entry(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Lotte, DE",
        data={CONF_MODE: MODE_TRACK},
        options={"update_interval_min": 10},
    )
    entry.add_to_hass(hass)
    entry.runtime_data = OpenMeteoRuntimeData(
        coordinator=object(),
        store=FakeStore(),
        source_key="phone",
        config_signature=config_signature(entry),
    )

    original_reload = hass.config_entries.async_reload
    hass.config_entries.async_reload = AsyncMock(return_value=True)
    try:
        hass.config_entries.async_update_entry(entry, title="Dortmund, DE")
        await async_update_entry(hass, entry)
        hass.config_entries.async_reload.assert_not_awaited()

        hass.config_entries.async_update_entry(
            entry, options={"update_interval_min": 5}
        )
        await async_update_entry(hass, entry)
        hass.config_entries.async_reload.assert_awaited_once_with(entry.entry_id)
    finally:
        hass.config_entries.async_reload = original_reload
