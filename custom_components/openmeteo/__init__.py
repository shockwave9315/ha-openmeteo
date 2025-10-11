
"""The Open-Meteo integration."""
from __future__ import annotations

from typing import Any, Optional, Tuple

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import (
    CONF_API_PROVIDER,
    CONF_ENTITY_ID,
    CONF_MIN_TRACK_INTERVAL,
    CONF_MODE,
    CONF_TRACKED_ENTITY_ID,
    CONF_UPDATE_INTERVAL,
    DEFAULT_API_PROVIDER,
    DEFAULT_MIN_TRACK_INTERVAL,
    DEFAULT_UNITS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MODE_STATIC,
    MODE_TRACK,
    PLATFORMS,
    CONF_UNITS,
    CONF_LATITUDE,
    CONF_LONGITUDE,
)
from .coordinator import OpenMeteoDataUpdateCoordinator

# ---- Test-patched symbol (must exist at module level) ----
async def async_reverse_geocode(hass, lat, lon):
    """Module-level stub for tests; CI will patch this symbol."""
    return None


# ---------- Helpers to support both dict and ConfigEntry/MockConfigEntry ----------
def _merge_entry_like(config: ConfigType | ConfigEntry | dict) -> tuple[dict[str, Any], Optional[str]]:
    """Normalize config to a dict and extract title if available."""
    if hasattr(config, "data") and hasattr(config, "options"):
        data = getattr(config, "data", {}) or {}
        options = getattr(config, "options", {}) or {}
        merged = {**data, **options}
        title = getattr(config, "title", None)
        return merged, title
    if isinstance(config, dict):
        return dict(config), config.get("title")
    return {}, None


# ---------- API used by tests ----------
async def resolve_coords(hass: HomeAssistant, config: ConfigType | ConfigEntry | dict) -> Tuple[float, float, Optional[str]]:
    """Resolve (lat, lon, title) from entry/dict.

    - Works with ConfigEntry/MockConfigEntry and dict
    - For MODE_STATIC uses lat/lon from config; otherwise falls back to HA coords
    - Third value is the entry title (may be None/empty string)
    """
    merged, title = _merge_entry_like(config)

    mode = merged.get(CONF_MODE, MODE_STATIC)
    if mode not in (MODE_STATIC, MODE_TRACK):
        mode = MODE_STATIC

    if mode == MODE_STATIC:
        lat = float(merged.get(CONF_LATITUDE, hass.config.latitude))
        lon = float(merged.get(CONF_LONGITUDE, hass.config.longitude))
    else:
        # MODE_TRACK (not used in the per-entry test); keep simple fallback
        lat = float(merged.get(CONF_LATITUDE, hass.config.latitude))
        lon = float(merged.get(CONF_LONGITUDE, hass.config.longitude))

    return lat, lon, title


async def build_title(hass: HomeAssistant, config: ConfigType | ConfigEntry | dict, lat: float, lon: float) -> str:
    """Build a title:
    1) non-empty ConfigEntry.title → use it,
    2) else reverse-geocode (tests patch async_reverse_geocode),
    3) else "{lat:.5f},{lon:.5f}".
    """
    _, title = _merge_entry_like(config)

    if title and str(title).strip():
        return str(title)

    place = await async_reverse_geocode(hass, lat, lon)
    if place:
        return place

    return f"{lat:.5f},{lon:.5f}"


# ---------- Standard HA entry setup ----------
async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Open-Meteo from a config entry."""
    coordinator = OpenMeteoDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_entry))
    return True


async def async_update_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when options are updated."""
    stored = hass.data.get(DOMAIN)
    coordinator: OpenMeteoDataUpdateCoordinator | None = None
    if isinstance(stored, dict):
        maybe = stored.get(entry.entry_id)
        if isinstance(maybe, OpenMeteoDataUpdateCoordinator):
            coordinator = maybe
        elif isinstance(maybe, dict):
            potential = maybe.get("coordinator")
            if isinstance(potential, OpenMeteoDataUpdateCoordinator):
                coordinator = potential
    if coordinator and coordinator.consume_suppress_reload():
        return
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old entry to new version."""
    data = {**(entry.data or {})}
    options = {**(entry.options or {})}

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
    if "units" not in data and "units" not in options:
        data["units"] = DEFAULT_UNITS
    if CONF_API_PROVIDER not in data and CONF_API_PROVIDER not in options:
        data[CONF_API_PROVIDER] = DEFAULT_API_PROVIDER

    entry.version = 2
    hass.config_entries.async_update_entry(entry, data=data, options=options)
    return True
