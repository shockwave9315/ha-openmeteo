# SPDX-License-Identifier: Apache-2.0
# SPDX-License-Identifier: Apache-2.0
"""The Open-Meteo integration."""
from __future__ import annotations

from typing import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant

from .const import (
    CONF_API_PROVIDER,
    CONF_ENTITY_ID,
    CONF_MIN_TRACK_INTERVAL,
    CONF_MODE,
    CONF_TRACKED_ENTITY_ID,
    CONF_UNITS,
    CONF_UPDATE_INTERVAL,
    CONF_USE_PLACE_AS_DEVICE_NAME,
    CONF_AREA_NAME_OVERRIDE,
    DEFAULT_API_PROVIDER,
    DEFAULT_MIN_TRACK_INTERVAL,
    DEFAULT_UNITS,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_USE_PLACE_AS_DEVICE_NAME,
    DOMAIN,
    MODE_STATIC,
    MODE_TRACK,
    PLATFORMS,
)
from .coordinator import OpenMeteoDataUpdateCoordinator, async_reverse_geocode


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


async def build_title(
    hass: HomeAssistant, entry: ConfigEntry, lat: float, lon: float
) -> str:
    """Build a title for the entry based on coordinates."""
    override = entry.options.get(CONF_AREA_NAME_OVERRIDE)
    if override is None:
        override = entry.data.get(CONF_AREA_NAME_OVERRIDE)
    geocode = entry.options.get("geocode_name", entry.data.get("geocode_name", True))
    store = _entry_store(hass, entry)
    if override:
        store["place_name"] = override
        store["place"] = override
        return override
    if geocode:
        name = await async_reverse_geocode(hass, lat, lon)
        if name:
            store["place_name"] = name
            store["place"] = name
            return name
    store["place_name"] = None
    store["place"] = None
    return f"{lat:.5f},{lon:.5f}"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Open-Meteo from a config entry."""
    mode = entry.options.get(CONF_MODE, entry.data.get(CONF_MODE))
    if mode == MODE_STATIC:
        data = dict(entry.data)
        opts = dict(entry.options)
        changed = False
        if opts.pop(CONF_USE_PLACE_AS_DEVICE_NAME, None) is not None:
            changed = True
        if data.pop(CONF_USE_PLACE_AS_DEVICE_NAME, None) is not None:
            changed = True
        if changed:
            hass.config_entries.async_update_entry(entry, data=data, options=opts)
    else:
        if CONF_USE_PLACE_AS_DEVICE_NAME not in entry.options:
            use_place = entry.data.pop(
                CONF_USE_PLACE_AS_DEVICE_NAME, DEFAULT_USE_PLACE_AS_DEVICE_NAME
            )
            hass.config_entries.async_update_entry(
                entry,
                data=entry.data,
                options={
                    **entry.options,
                    CONF_USE_PLACE_AS_DEVICE_NAME: use_place,
                },
            )
    coordinator = OpenMeteoDataUpdateCoordinator(hass, entry)
    store = _entry_store(hass, entry)
    store["coordinator"] = coordinator
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator


    lat, lon, _src = await resolve_coords(hass, entry)
    title = await build_title(hass, entry, lat, lon)
    if title != entry.title:
        hass.config_entries.async_update_entry(entry, title=title)

    await coordinator.async_config_entry_first_refresh()
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
    coordinator = store.get("coordinator")
    if coordinator:
        coordinator._unsub_entity = None
        coordinator._unsub_refresh = None
        await coordinator.async_shutdown()
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        domain_data = hass.data.get(DOMAIN, {})
        entries = domain_data.get("entries", {})
        store.clear()
        entries.pop(entry.entry_id, None)
        if not entries and DOMAIN in hass.data:
            hass.data.pop(DOMAIN)
    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old entry to new version."""
    data = {**entry.data}
    options = {**entry.options}

    mode = data.get(CONF_MODE) or options.get(CONF_MODE)
    if not mode:
        if data.get(CONF_ENTITY_ID) or options.get(CONF_ENTITY_ID) or data.get(CONF_TRACKED_ENTITY_ID):
            data[CONF_MODE] = MODE_TRACK
        else:
            data[CONF_MODE] = MODE_STATIC

    if CONF_MIN_TRACK_INTERVAL not in data and CONF_MIN_TRACK_INTERVAL not in options:
        data[CONF_MIN_TRACK_INTERVAL] = DEFAULT_MIN_TRACK_INTERVAL
    if CONF_UPDATE_INTERVAL not in data and CONF_UPDATE_INTERVAL not in options:
        data[CONF_UPDATE_INTERVAL] = DEFAULT_UPDATE_INTERVAL
    if CONF_UNITS not in data and CONF_UNITS not in options:
        data[CONF_UNITS] = DEFAULT_UNITS
    if CONF_API_PROVIDER not in data and CONF_API_PROVIDER not in options:
        data[CONF_API_PROVIDER] = DEFAULT_API_PROVIDER

    entry.version = 2
    hass.config_entries.async_update_entry(entry, data=data, options=options)
    return True


async def _options_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    data = hass.data.get(DOMAIN, {}).get("entries", {}).get(entry.entry_id)
    if data and data.get("coordinator"):
        await data["coordinator"].async_options_updated()
        await data["coordinator"].async_request_refresh()
    else:
        await hass.config_entries.async_reload(entry.entry_id)

