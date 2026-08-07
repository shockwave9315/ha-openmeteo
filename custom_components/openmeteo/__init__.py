"""Open-Meteo integration v2."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    AQ_SENSOR_KEYS,
    CONF_ENABLED_AQ_SENSORS,
    CONF_ENABLED_SENSORS,
    CONF_ENABLED_WEATHER_SENSORS,
    CONF_ENTITY_ID,
    CONF_MIN_TRACK_INTERVAL,
    CONF_MODE,
    CONF_TRACKED_ENTITY_ID,
    CONF_UPDATE_INTERVAL,
    CONF_UPDATE_INTERVAL_MIN,
    DEFAULT_MIN_TRACK_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MODE_STATIC,
    MODE_TRACK,
    PLATFORMS,
    WEATHER_SENSOR_KEYS,
)
from .coordinator import OpenMeteoDataUpdateCoordinator
from .identity import CONF_SOURCE_KEY, derive_source_key
from .runtime import (
    OpenMeteoRuntimeData,
    config_signature,
    get_runtime_data,
)

STORAGE_VERSION = 1
CONFIG_ENTRY_VERSION = 4

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
    """Unload platforms and release tracker/timer subscriptions."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        runtime = get_runtime_data(entry)
        if runtime is not None:
            await runtime.coordinator.async_shutdown()
    return unload_ok


def _pop_legacy(mapping: dict[str, Any], *keys: str) -> None:
    for key in keys:
        mapping.pop(key, None)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Canonicalize v1-v3 entries for the v2 runtime model."""
    data = dict(entry.data or {})
    options = dict(entry.options or {})
    merged = {**data, **options}

    mode = merged.get(CONF_MODE)
    legacy_tracking_mode = merged.get("tracking_mode")
    tracked = merged.get(CONF_ENTITY_ID) or merged.get(CONF_TRACKED_ENTITY_ID)
    if mode not in (MODE_STATIC, MODE_TRACK):
        mode = MODE_TRACK if tracked or legacy_tracking_mode == "device" else MODE_STATIC
    data[CONF_MODE] = mode

    if mode == MODE_TRACK and not (data.get(CONF_ENTITY_ID) or options.get(CONF_ENTITY_ID)):
        if tracked:
            data[CONF_ENTITY_ID] = tracked

    if CONF_MIN_TRACK_INTERVAL not in data and CONF_MIN_TRACK_INTERVAL not in options:
        data[CONF_MIN_TRACK_INTERVAL] = DEFAULT_MIN_TRACK_INTERVAL

    if CONF_UPDATE_INTERVAL_MIN not in data and CONF_UPDATE_INTERVAL_MIN not in options:
        raw_seconds = merged.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        try:
            minutes = max(1, int(raw_seconds) // 60)
        except (TypeError, ValueError):
            minutes = max(1, DEFAULT_UPDATE_INTERVAL // 60)
        data[CONF_UPDATE_INTERVAL_MIN] = minutes

    if (
        CONF_ENABLED_WEATHER_SENSORS not in data
        and CONF_ENABLED_WEATHER_SENSORS not in options
        and CONF_ENABLED_AQ_SENSORS not in data
        and CONF_ENABLED_AQ_SENSORS not in options
    ):
        legacy_sensors = merged.get(CONF_ENABLED_SENSORS)
        if isinstance(legacy_sensors, list):
            selected = {str(item) for item in legacy_sensors}
            data[CONF_ENABLED_WEATHER_SENSORS] = [
                key for key in WEATHER_SENSOR_KEYS if key in selected
            ]
            data[CONF_ENABLED_AQ_SENSORS] = [
                key for key in AQ_SENSOR_KEYS if key in selected
            ]

    for mapping in (data, options):
        for key in list(mapping):
            if str(key).startswith("pv_"):
                mapping.pop(key, None)
        _pop_legacy(
            mapping,
            CONF_TRACKED_ENTITY_ID,
            CONF_ENABLED_SENSORS,
            CONF_UPDATE_INTERVAL,
            "tracking_mode",
            "units",
            "api_provider",
            "api_key",
            "use_place_as_device_name",
            "options_save_cooldown_min",
            "options_save_cooldown_sec",
            "scan_interval",
            "daily_variables",
            "hourly_variables",
        )

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
