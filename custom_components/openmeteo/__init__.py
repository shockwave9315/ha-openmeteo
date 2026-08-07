"""Open-Meteo integration v2."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, PLATFORMS
from .coordinator import OpenMeteoDataUpdateCoordinator
from .identity import CONF_SOURCE_KEY, derive_source_key
from .runtime import OpenMeteoRuntimeData, config_signature, get_runtime_data

STORAGE_VERSION = 1

type OpenMeteoConfigEntry = ConfigEntry[OpenMeteoRuntimeData]


def _merged(entry: ConfigEntry) -> dict[str, Any]:
    return {**dict(entry.data or {}), **dict(entry.options or {})}


async def async_setup_entry(
    hass: HomeAssistant, entry: OpenMeteoConfigEntry
) -> bool:
    """Set up one static or tracked Open-Meteo source."""
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
        config_signature=config_signature(entry),
    )

    await coordinator.async_config_entry_first_refresh()
    await coordinator.async_start_tracking()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Entity setup creates/links the service device. Do one final presentation
    # sync afterwards so platform setup order cannot overwrite an explicit UI name.
    await coordinator._sync_presentation(coordinator.presentation_name)
    entry.async_on_unload(entry.add_update_listener(async_update_entry))
    return True


async def async_update_entry(
    hass: HomeAssistant, entry: OpenMeteoConfigEntry
) -> None:
    """Reload only when data/options changed.

    A tracked city name is stored in the config-entry title for presentation, but
    title-only changes must not reload the integration.
    """
    runtime = get_runtime_data(entry)
    if runtime is not None and runtime.config_signature == config_signature(entry):
        return
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant, entry: OpenMeteoConfigEntry
) -> bool:
    """Unload platforms.

    DataUpdateCoordinator registers its async_shutdown callback on the config
    entry itself, so Home Assistant owns coordinator shutdown after this returns.
    """
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
