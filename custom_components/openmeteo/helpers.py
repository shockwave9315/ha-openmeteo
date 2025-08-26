# SPDX-License-Identifier: Apache-2.0
"""Helper utilities for the Open-Meteo integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, CONF_MODE, MODE_STATIC, CONF_USE_PLACE_AS_DEVICE_NAME
import re


def get_place_title(hass: HomeAssistant, entry: ConfigEntry) -> str:
    """Return a displayable place title for the entry."""
    store = (
        hass.data.get(DOMAIN, {})
        .get("entries", {})
        .get(entry.entry_id, {})
    )
    if store.get("place_name"):
        return store["place_name"]
    lat = store.get("lat")
    lon = store.get("lon")
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        return f"{lat:.5f},{lon:.5f}"
    return entry.title


def _get_device(hass: HomeAssistant, entry: ConfigEntry) -> dr.DeviceEntry | None:
    """Return device registry entry for this config entry."""
    dev_reg = dr.async_get(hass)
    return dev_reg.async_get_device(identifiers={(DOMAIN, entry.entry_id)})


COORD_RE = re.compile(r"^-?\d{1,3}\.\d+,-?\d{1,3}\.\d+$")


async def maybe_update_device_name(
    hass: HomeAssistant, entry: ConfigEntry, desired: str | None
) -> None:
    """Set device name to place if allowed and not user-renamed."""
    mode = entry.options.get(CONF_MODE, entry.data.get(CONF_MODE))
    static_mode = mode == MODE_STATIC
    use_place_opt = entry.options.get(
        CONF_USE_PLACE_AS_DEVICE_NAME,
        entry.data.get(CONF_USE_PLACE_AS_DEVICE_NAME, True),
    )
    if not static_mode and not use_place_opt:
        return
    if not desired or COORD_RE.match(desired):
        return
    device = _get_device(hass, entry)
    if not device or device.name_by_user or desired == device.name:
        return
    dev_reg = dr.async_get(hass)
    dev_reg.async_update_device(device.id, name=desired)
