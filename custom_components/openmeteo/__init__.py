"""Open-Meteo integration v2 architecture."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    CONF_API_PROVIDER,
    CONF_ENTITY_ID,
    CONF_MIN_TRACK_INTERVAL,
    CONF_MODE,
    CONF_TRACKED_ENTITY_ID,
    CONF_UPDATE_INTERVAL,
    DEFAULT_API_PROVIDER,
    DEFAULT_MIN_TRACK_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MODE_STATIC,
    MODE_TRACK,
    PLATFORMS,
)
from .coordinator import OpenMeteoDataUpdateCoordinator
from .identity import CONF_SOURCE_KEY, derive_source_key
from .runtime import OpenMeteoRuntimeData, get_runtime_data

STORAGE_VERSION = 1
CONFIG_ENTRY_VERSION = 4

type OpenMeteoConfigEntry = ConfigEntry[OpenMeteoRuntimeData]


def _merged(entry: ConfigEntry) -> dict[str, Any]:
    return {**dict(entry.data or {}), **dict(entry.options or {})}


async def async_setup_entry(
    hass: HomeAssistant, entry: OpenMeteoConfigEntry
) -> bool:
    """Set up one Open-Meteo source."""
    merged = _merged(entry)
    source_key = str(
        merged.get(CONF_SOURCE_KEY)
        or derive_source_key(entry_id=entry.entry_id, title=entry.title, data=merged)
    )

    store: Store[dict[str, Any]] = Store(
        hass,
        STORAGE_VERSION,
        f"{DOMAIN}.{entry.entry_id}.runtime",
    )
    restored = await store.async_load() or {}

    coordinator = OpenMeteoDataUpdateCoordinator(hass, entry, store, restored)
    entry.runtime_data = OpenMeteoRuntimeData(
        coordinator=coordinator,
        store=store,
        source_key=source_key,
    )

    await coordinator.async_config_entry_first_refresh()
    await coordinator.async_start_tracking()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_entry))
    return True


async def async_update_entry(
    hass: HomeAssistant, entry: OpenMeteoConfigEntry
) -> None:
    """Reload on user option changes, not on internal title refreshes."""
    runtime = get_runtime_data(entry)
    if runtime is not None and runtime.coordinator.consume_internal_update():
        return
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant, entry: OpenMeteoConfigEntry
) -> bool:
    """Unload platforms and all event subscriptions."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        runtime = get_runtime_data(entry)
        if runtime is not None:
            await runtime.coordinator.async_shutdown()
    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate all v1-v3 entries to the v2 identity/runtime model."""
    data = dict(entry.data or {})
    options = dict(entry.options or {})
    merged = {**data, **options}

    mode = merged.get(CONF_MODE)
    if mode not in (MODE_STATIC, MODE_TRACK):
        tracked = merged.get(CONF_ENTITY_ID) or merged.get(CONF_TRACKED_ENTITY_ID)
        mode = MODE_TRACK if tracked else MODE_STATIC
        data[CONF_MODE] = mode

    if mode == MODE_TRACK and not data.get(CONF_ENTITY_ID):
        tracked = options.get(CONF_ENTITY_ID) or merged.get(CONF_TRACKED_ENTITY_ID)
        if tracked:
            data[CONF_ENTITY_ID] = tracked

    if CONF_MIN_TRACK_INTERVAL not in data and CONF_MIN_TRACK_INTERVAL not in options:
        data[CONF_MIN_TRACK_INTERVAL] = DEFAULT_MIN_TRACK_INTERVAL
    if CONF_UPDATE_INTERVAL not in data and "update_interval_min" not in merged:
        data[CONF_UPDATE_INTERVAL] = DEFAULT_UPDATE_INTERVAL
    if CONF_API_PROVIDER not in data and CONF_API_PROVIDER not in options:
        data[CONF_API_PROVIDER] = DEFAULT_API_PROVIDER

    for mapping in (data, options):
        for key in list(mapping):
            if str(key).startswith("pv_"):
                mapping.pop(key, None)

    merged_after_cleanup = {**data, **options}
    if not data.get(CONF_SOURCE_KEY):
        data[CONF_SOURCE_KEY] = derive_source_key(
            entry_id=entry.entry_id,
            title=entry.title,
            data=merged_after_cleanup,
        )

    hass.config_entries.async_update_entry(
        entry,
        data=data,
        options=options,
        version=CONFIG_ENTRY_VERSION,
    )
    return True
