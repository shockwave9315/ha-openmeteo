from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from custom_components.openmeteo.__init__ import async_migrate_entry
from custom_components.openmeteo.const import (
    CONF_API_PROVIDER,
    CONF_MIN_TRACK_INTERVAL,
    CONF_MODE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_API_PROVIDER,
    DEFAULT_MIN_TRACK_INTERVAL,
    DEFAULT_UNITS,
    DEFAULT_UPDATE_INTERVAL,
    MODE_STATIC,
)


@pytest.mark.asyncio
async def test_migration_uses_async_update_entry_for_version() -> None:
    entry = SimpleNamespace(
        data={"pv_legacy": 1},
        options={"enabled_sensors": ["temperature", "pv_old"]},
        version=2,
    )

    def _update_entry(target, **kwargs):
        if "version" in kwargs:
            target.version = kwargs["version"]

    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_update_entry=MagicMock(side_effect=_update_entry))
    )

    result = await async_migrate_entry(hass, entry)

    assert result is True
    hass.config_entries.async_update_entry.assert_called_once()
    _, kwargs = hass.config_entries.async_update_entry.call_args
    assert kwargs["version"] == 3

    migrated_data = kwargs["data"]
    migrated_options = kwargs["options"]

    assert migrated_data[CONF_MODE] == MODE_STATIC
    assert migrated_data[CONF_MIN_TRACK_INTERVAL] == DEFAULT_MIN_TRACK_INTERVAL
    assert migrated_data[CONF_UPDATE_INTERVAL] == DEFAULT_UPDATE_INTERVAL
    assert migrated_data["units"] == DEFAULT_UNITS
    assert migrated_data[CONF_API_PROVIDER] == DEFAULT_API_PROVIDER
    assert "pv_legacy" not in migrated_data
    assert migrated_options["enabled_sensors"] == ["temperature"]
