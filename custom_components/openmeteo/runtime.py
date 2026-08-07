"""Typed runtime state for Open-Meteo."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store


@dataclass(slots=True)
class OpenMeteoRuntimeData:
    """Runtime objects owned by one config entry."""

    coordinator: Any
    store: Store[dict[str, Any]]
    source_key: str
    metadata: dict[str, Any] = field(default_factory=dict)


def get_runtime_data(entry: ConfigEntry) -> OpenMeteoRuntimeData | None:
    runtime = getattr(entry, "runtime_data", None)
    return runtime if isinstance(runtime, OpenMeteoRuntimeData) else None


def get_entry_coordinator(hass: HomeAssistant, entry_id: str) -> Any | None:
    """Compatibility helper while v2 removes hass.data based storage."""
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is not None:
        runtime = get_runtime_data(entry)
        if runtime is not None:
            return runtime.coordinator

    # Temporary compatibility with v1 tests/partially migrated code.
    domain_store = hass.data.get("openmeteo")
    if isinstance(domain_store, dict):
        value = domain_store.get(entry_id)
        if isinstance(value, dict):
            return value.get("coordinator")
        return value
    return None


def get_entry_runtime_store(hass: HomeAssistant, entry_id: str) -> dict[str, Any] | None:
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is not None:
        runtime = get_runtime_data(entry)
        if runtime is not None:
            return runtime.metadata
    return None


def get_or_create_entry_runtime_store(hass: HomeAssistant, entry_id: str) -> dict[str, Any]:
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is not None:
        runtime = get_runtime_data(entry)
        if runtime is not None:
            return runtime.metadata

    # Compatibility fallback only; new v2 code should never need this path.
    domain_store = hass.data.setdefault("openmeteo", {})
    entries = domain_store.setdefault("entries", {})
    return entries.setdefault(entry_id, {})
