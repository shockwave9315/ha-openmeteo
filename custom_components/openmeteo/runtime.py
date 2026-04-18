# SPDX-License-Identifier: Apache-2.0
"""Runtime access helpers for Open-Meteo hass.data state."""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .const import DOMAIN


EntryStore = dict[str, Any]


def _get_domain_store(hass: HomeAssistant) -> dict[str, Any]:
    """Return Open-Meteo domain store as a dict."""
    store = hass.data.get(DOMAIN)
    return store if isinstance(store, dict) else {}


def get_entry_coordinator(hass: HomeAssistant, entry_id: str) -> Any | None:
    """Return coordinator for an entry, supporting legacy wrapped storage shape."""
    domain_store = _get_domain_store(hass)
    value = domain_store.get(entry_id)
    if isinstance(value, dict):
        return value.get("coordinator")
    return value


def get_entry_runtime_store(hass: HomeAssistant, entry_id: str) -> EntryStore | None:
    """Return runtime metadata store for an entry or None when unavailable."""
    entries = _get_domain_store(hass).get("entries")
    if not isinstance(entries, dict):
        return None
    store = entries.get(entry_id)
    return store if isinstance(store, dict) else None


def get_or_create_entry_runtime_store(hass: HomeAssistant, entry_id: str) -> EntryStore:
    """Return runtime metadata store for an entry and create it when missing."""
    domain_store = hass.data.setdefault(DOMAIN, {})
    entries = domain_store.setdefault("entries", {})
    store = entries.setdefault(entry_id, {})
    return store
