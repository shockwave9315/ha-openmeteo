"""Typed runtime state for Open-Meteo v2."""
from __future__ import annotations

from dataclasses import dataclass
import json
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
    config_signature: str


def config_signature(entry: ConfigEntry) -> str:
    """Return a stable fingerprint of reload-relevant config.

    Entry title is intentionally excluded: the current place is presentation state
    and may change while tracking without requiring a reload.
    """
    return json.dumps(
        {
            "data": dict(entry.data or {}),
            "options": dict(entry.options or {}),
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def get_runtime_data(entry: ConfigEntry) -> OpenMeteoRuntimeData | None:
    runtime = getattr(entry, "runtime_data", None)
    return runtime if isinstance(runtime, OpenMeteoRuntimeData) else None


def get_entry_coordinator(hass: HomeAssistant, entry_id: str) -> Any | None:
    """Return the coordinator through ConfigEntry.runtime_data."""
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None:
        return None
    runtime = get_runtime_data(entry)
    return runtime.coordinator if runtime is not None else None
