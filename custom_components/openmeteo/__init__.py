"""The Open-Meteo integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_API_PROVIDER,
    CONF_ENTITY_ID,
    CONF_LATITUDE,
    CONF_LONGITUDE,
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
)
from .coordinator import OpenMeteoDataUpdateCoordinator, async_reverse_geocode
from homeassistant.helpers.typing import ConfigType
from typing import Any, Optional, Tuple


async def resolve_coords(hass: HomeAssistant, config_entry: ConfigEntry) -> Tuple[float, float]:
    """Resolve coordinates from the configuration entry.
    
    Args:
        hass: Home Assistant instance
        config_entry: The config entry object.
        
    Returns:
        Tuple of (latitude, longitude)
    """
    config = {**config_entry.data, **config_entry.options}

    if config.get(CONF_MODE) == MODE_TRACK and CONF_TRACKED_ENTITY_ID in config:
        # Get coordinates from tracked entity
        state = hass.states.get(config[CONF_TRACKED_ENTITY_ID])
        if state is None:
            raise ValueError(f"Entity {config[CONF_TRACKED_ENTITY_ID]} not found")
        
        try:
            latitude = float(state.attributes.get("latitude"))
            longitude = float(state.attributes.get("longitude"))
            if latitude is None or longitude is None:
                raise ValueError("Entity does not have latitude/longitude attributes")
            return (latitude, longitude)
        except (TypeError, ValueError) as err:
            raise ValueError(f"Could not get coordinates from entity {config[CONF_TRACKED_ENTITY_ID]}: {err}")
    else:
        # Get coordinates from static configuration
        try:
            latitude = float(config[CONF_LATITUDE])
            longitude = float(config[CONF_LONGITUDE])
            return (latitude, longitude)
        except (KeyError, ValueError) as err:
            raise ValueError(f"Invalid coordinates in configuration: {err}")


async def build_title(hass: HomeAssistant, config_entry: ConfigEntry) -> str:
    """Build a title for the integration based on the configuration.
    
    Args:
        hass: Home Assistant instance
        config_entry: The config entry object
        
    Returns:
        A string title for the integration
    """
    try:
        lat, lon = await resolve_coords(hass, config_entry)
        return f"{lat:.4f}, {lon:.4f}"
    except ValueError:
        return "Open-Meteo"


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