# SPDX-License-Identifier: Apache-2.0
"""Helper utilities for the Open-Meteo integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, CONF_USE_PLACE_AS_DEVICE_NAME


def get_place_title(hass: HomeAssistant, entry: ConfigEntry) -> str:
    """Return the preferred place title for a config entry."""
    override = entry.options.get("name_override") or entry.data.get("name_override")
    if override:
        return override
    store = (
        hass.data.get(DOMAIN, {})
        .get("entries", {})
        .get(entry.entry_id, {})
    )
    place = store.get("place")
    if place:
        return place
    lat = store.get("lat")
    lon = store.get("lon")
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        return f"{lat:.5f},{lon:.5f}"
    return entry.title


def get_device_for_entry(hass: HomeAssistant, entry: ConfigEntry) -> dr.DeviceEntry | None:
    """Return the device registry entry for a config entry."""
    dev_reg = dr.async_get(hass)
    return dev_reg.async_get_device(identifiers={(DOMAIN, entry.entry_id)})


async def maybe_update_device_name(
    hass: HomeAssistant, entry: ConfigEntry, place: str | None
) -> None:
    """Update device name with place if allowed and not user-renamed."""
    use_place = entry.options.get(
        CONF_USE_PLACE_AS_DEVICE_NAME,
        entry.data.get(CONF_USE_PLACE_AS_DEVICE_NAME, True),
    )
    if not use_place:
        return
    device = get_device_for_entry(hass, entry)
    if not device:
        return
    if device.name_by_user:
        return
    desired = (
        entry.options.get("name_override")
        or entry.data.get("name_override")
        or place
    )
    if not desired or device.name == desired:
        return
    dev_reg = dr.async_get(hass)
    dev_reg.async_update_device(device.id, name=desired)
