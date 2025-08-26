# SPDX-License-Identifier: Apache-2.0
# SPDX-License-Identifier: Apache-2.0
"""The Open-Meteo integration."""
from __future__ import annotations

# Changelog:
# 1.3.33 - Standardize entity IDs and migrate legacy unique IDs.
# 1.3.35 - Stable entry-based IDs; dynamic names with reverse geocoding and caching.
# 1.3.36 - add legacy sensors (precipitation_probability, sunrise, sunset, location); stable IDs; dynamic names; correct icons & device_class for all sensors.
# 1.3.37 - stałe entity_id bez miejscowości; domyślnie w nazwach dopisek lokalizacji; ikony i device_class uzupełnione.

from typing import Callable, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant

from .const import (
    CONF_ENTITY_ID,
    CONF_TRACKED_ENTITY_ID,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import OpenMeteoDataUpdateCoordinator


CONFIG_ENTRY_VERSION = 2


def _entry_store(hass: HomeAssistant, entry: ConfigEntry) -> dict:
    """Return the per-entry storage."""
    from .const import DOMAIN as _DOMAIN

    return hass.data.setdefault(_DOMAIN, {}).setdefault("entries", {}).setdefault(
        entry.entry_id, {}
    )


def _register_unsub(
    hass: HomeAssistant, entry: ConfigEntry, fn: Callable[[], None]
) -> None:
    """Register an unsubscribe callback for the entry."""
    store = _entry_store(hass, entry)
    store.setdefault("unsubs", []).append(fn)


async def resolve_coords(
    hass: HomeAssistant, entry: ConfigEntry
) -> tuple[float, float, str]:
    """Resolve coordinates for a given entry."""
    data = {**entry.data, **entry.options}
    lat = data.get(CONF_LATITUDE)
    lon = data.get(CONF_LONGITUDE)
    src = "static"

    track_entity = (
        data.get(CONF_ENTITY_ID) or data.get(CONF_TRACKED_ENTITY_ID)
    )
    if track_entity:
        st = hass.states.get(track_entity)
        if st:
            attrs = st.attributes
            ent_lat = attrs.get("latitude")
            ent_lon = attrs.get("longitude")
            if isinstance(ent_lat, (int, float)) and isinstance(ent_lon, (int, float)):
                lat = float(ent_lat)
                lon = float(ent_lon)
                src = (
                    "device_tracker"
                    if track_entity.split(".")[0] == "device_tracker"
                    else "entity"
                )

    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        lat = float(hass.config.latitude)
        lon = float(hass.config.longitude)

    store = _entry_store(hass, entry)
    store["coords"] = (lat, lon)
    store["source"] = src
    store["lat"] = lat
    store["lon"] = lon
    store["src"] = src
    return lat, lon, src


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entry to the latest version."""
    version = getattr(entry, "version", 1)
    if version >= CONFIG_ENTRY_VERSION:
        return True

    data = dict(entry.data)
    options = dict(entry.options)
    changed = False

    if version < 2:
        # Remove legacy keys and merge old aliases
        for k in ("use_place_as_device_name",):
            if k in data:
                data.pop(k)
                changed = True
            if k in options:
                options.pop(k)
                changed = True
        for old in ("track_entity", "track_entity_id"):
            if old in options and "entity_id" not in options:
                options["entity_id"] = options.pop(old)
                changed = True
            else:
                options.pop(old, None)
        options.setdefault("show_place_name", True)
        entry.version = 2

    if changed:
        hass.config_entries.async_update_entry(entry, data=data, options=options)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Open-Meteo from a config entry."""
    coordinator = OpenMeteoDataUpdateCoordinator(hass, entry)
    store = _entry_store(hass, entry)
    store["coordinator"] = coordinator

    lat, lon, _src = await resolve_coords(hass, entry)
    coordinator.latitude = lat
    coordinator.longitude = lon

    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        pass
    await coordinator._resubscribe_tracked_entity(entry.options.get("entity_id"))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_options_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    store = _entry_store(hass, entry)
    for fn in store.get("unsubs", []):
        try:
            fn()
        except Exception:
            pass
    store["unsubs"] = []
    for task in store.get("tasks", []):
        task.cancel()
    store["tasks"] = []
    coordinator = store.get("coordinator")
    if coordinator:
        await coordinator.async_unload()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        domain_data = hass.data.get(DOMAIN, {})
        entries = domain_data.get("entries", {})
        store.clear()
        entries.pop(entry.entry_id, None)
        if not entries and DOMAIN in hass.data:
            hass.data.pop(DOMAIN)
    return unload_ok


async def _options_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    coord = (
        hass.data.get(DOMAIN, {})
        .get("entries", {})
        .get(entry.entry_id, {})
        .get("coordinator")
    )
    if coord:
        hass.async_create_task(coord.async_options_updated())


