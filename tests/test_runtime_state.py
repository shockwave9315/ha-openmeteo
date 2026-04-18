from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.openmeteo import async_update_entry
from custom_components.openmeteo.const import DOMAIN
from custom_components.openmeteo.runtime import (
    get_entry_coordinator,
    get_entry_runtime_store,
    get_or_create_entry_runtime_store,
)


@pytest.mark.asyncio
async def test_get_entry_coordinator_supports_canonical_and_wrapped_shape() -> None:
    hass = SimpleNamespace(data={DOMAIN: {"entry_a": "coord_a", "entry_b": {"coordinator": "coord_b"}}})

    assert get_entry_coordinator(hass, "entry_a") == "coord_a"
    assert get_entry_coordinator(hass, "entry_b") == "coord_b"


@pytest.mark.asyncio
async def test_runtime_store_create_and_read_consistent() -> None:
    hass = SimpleNamespace(data={})

    store = get_or_create_entry_runtime_store(hass, "entry_a")
    store["src"] = "forecast"

    resolved = get_entry_runtime_store(hass, "entry_a")

    assert resolved is store
    assert resolved == {"src": "forecast"}


@pytest.mark.asyncio
async def test_async_update_entry_uses_wrapped_coordinator_without_reload() -> None:
    coordinator = SimpleNamespace(consume_suppress_reload=lambda: True)
    entry = SimpleNamespace(entry_id="entry_wrapped")
    hass = SimpleNamespace(
        data={DOMAIN: {"entry_wrapped": {"coordinator": coordinator}}},
        config_entries=SimpleNamespace(async_reload=AsyncMock()),
    )

    await async_update_entry(hass, entry)

    hass.config_entries.async_reload.assert_not_called()
