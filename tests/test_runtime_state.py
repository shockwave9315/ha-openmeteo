from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

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
async def test_sensor_setup_entry_uses_runtime_coordinator_helper() -> None:
    text = Path("custom_components/openmeteo/sensor.py").read_text(encoding="utf-8")
    assert "get_entry_coordinator(hass, config_entry.entry_id)" in text
    assert 'stored.get("coordinator") if isinstance(stored, dict) else stored' not in text
