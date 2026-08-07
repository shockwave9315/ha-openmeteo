"""Stable identity helpers for Open-Meteo v2.

Location is presentation/runtime state. It must never become part of an entity's
identity after the entry has been created.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.util import slugify

from .const import (
    CONF_ENTITY_ID,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_MODE,
    CONF_TRACKED_ENTITY_ID,
    MODE_TRACK,
)

CONF_SOURCE_KEY = "source_key"


def _clean_source_key(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    key = slugify(value).strip("_")
    return key or None


def derive_source_key(
    *,
    entry_id: str,
    title: str | None,
    data: Mapping[str, Any],
) -> str:
    """Derive a stable source key for a config entry.

    The result is persisted once in config-entry data and is never recomputed
    from the moving location afterwards.
    """
    if key := _clean_source_key(data.get(CONF_SOURCE_KEY)):
        return key

    mode = data.get(CONF_MODE)
    tracked_entity = data.get(CONF_ENTITY_ID) or data.get(CONF_TRACKED_ENTITY_ID)
    if mode == MODE_TRACK or tracked_entity:
        if isinstance(tracked_entity, str) and tracked_entity:
            object_id = tracked_entity.split(".", 1)[-1]
            if key := _clean_source_key(object_id):
                return key

    if key := _clean_source_key(title):
        return key

    lat = data.get(CONF_LATITUDE)
    lon = data.get(CONF_LONGITUDE)
    if lat is not None and lon is not None:
        if key := _clean_source_key(f"{lat}_{lon}"):
            return key

    return f"entry_{entry_id[:8]}"


def weather_object_id(source_key: str) -> str:
    """Return the initial object id for a weather entity."""
    return f"open_meteo_{source_key}"


def sensor_object_id(source_key: str, sensor_slug: str) -> str:
    """Return the initial object id for a sensor entity."""
    return f"open_meteo_{source_key}_{sensor_slug}"


def weather_unique_id(entry_id: str) -> str:
    """Preserve the v1 registry identity to prevent duplicate weather entities."""
    return f"{entry_id}-weather"


def sensor_unique_id(entry_id: str, sensor_key: str, *, air_quality: bool = False) -> str:
    """Preserve v1 sensor registry identities during the v2 migration."""
    suffix = f"{sensor_key}_aq" if air_quality else sensor_key
    return f"{entry_id}:{suffix}"
