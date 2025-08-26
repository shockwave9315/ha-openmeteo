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
from homeassistant.util import dt as dt_util

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
    CONF_SHOW_PLACE_NAME,
    CONF_GEOCODER_PROVIDER,
    DEFAULT_API_PROVIDER,
    DEFAULT_MIN_TRACK_INTERVAL,
    DEFAULT_UNITS,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_USE_PLACE_AS_DEVICE_NAME,
    DEFAULT_SHOW_PLACE_NAME,
    DEFAULT_GEOCODER_PROVIDER,
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
    show_place = entry.options.get(
        CONF_SHOW_PLACE_NAME, entry.data.get(CONF_SHOW_PLACE_NAME, DEFAULT_SHOW_PLACE_NAME)
    )
    provider = entry.options.get(CONF_GEOCODER_PROVIDER, DEFAULT_GEOCODER_PROVIDER)
    store = _entry_store(hass, entry)
    if override:
        store["place_name"] = override
        store["place"] = override
        return override
    if show_place:
        name = await async_reverse_geocode(hass, lat, lon, provider)
        if name:
            store["place_name"] = name
            store["place"] = name
            store["location_name"] = name
            store["geocode_provider"] = provider
            store["geocode_last_success"] = dt_util.utcnow().isoformat()
            return name
    store["place_name"] = None
    store["place"] = None
    store["location_name"] = None
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
    # Ensure required options exist to avoid None values during setup
    option_updates: dict[str, Any] = {}
    if CONF_SHOW_PLACE_NAME not in entry.options:
        option_updates[CONF_SHOW_PLACE_NAME] = DEFAULT_SHOW_PLACE_NAME
    if option_updates:
        hass.config_entries.async_update_entry(
            entry, options={**entry.options, **option_updates}
        )

    coordinator = OpenMeteoDataUpdateCoordinator(hass, entry)
    store = _entry_store(hass, entry)
    store["coordinator"] = coordinator
    store["options_snapshot"] = dict(entry.options)

    lat, lon, _src = await resolve_coords(hass, entry)
    coordinator.latitude = lat
    coordinator.longitude = lon
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


async def _options_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    data = hass.data.get(DOMAIN, {}).get("entries", {}).get(entry.entry_id)
    if data:
        data["options_snapshot"] = dict(entry.options)
        coord = data.get("coordinator")
        if coord:
            hass.async_create_task(coord.async_options_updated())
            hass.async_create_task(coord.async_request_refresh())
            return
    hass.async_create_task(hass.config_entries.async_reload(entry.entry_id))

