"""The Open-Meteo integration with dynamic device tracking."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback, State
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.components.device_tracker import DOMAIN as DEVICE_TRACKER_DOMAIN
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_DAILY_VARIABLES,
    CONF_HOURLY_VARIABLES,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_SCAN_INTERVAL,
    CONF_TIME_ZONE,
    CONF_NAME,
    DEFAULT_DAILY_VARIABLES,
    DEFAULT_HOURLY_VARIABLES,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_NAME,
    DOMAIN,
    URL,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["weather", "sensor"]
SIGNAL_UPDATE_ENTITIES = f"{DOMAIN}_update_entities"

class OpenMeteoInstance:
    """Represents a single OpenMeteo instance for a specific location."""
    
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, device_id: str = None):
        """Initialize the instance."""
        self.hass = hass
        self.entry = entry
        self.device_id = device_id
        self.coordinator = OpenMeteoDataUpdateCoordinator(hass, entry, device_id)
        self.entities = set()
    
    async def async_init(self) -> None:
        """Initialize the instance."""
        await self.coordinator.async_config_entry_first_refresh()
    
    async def async_unload(self) -> None:
        """Unload the instance."""
        # Unload all platforms
        for platform in PLATFORMS:
            await self.hass.config_entries.async_forward_entry_unload(self.entry, platform)
    
    def add_entity(self, entity_id: str) -> None:
        """Add an entity to this instance."""
        self.entities.add(entity_id)
    
    def remove_entity(self, entity_id: str) -> None:
        """Remove an entity from this instance."""
        self.entities.discard(entity_id)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Open-Meteo from a config entry with device tracking support."""
    hass.data.setdefault(DOMAIN, {})
    
    # Initialize the main instance (for static location)
    main_instance = OpenMeteoInstance(hass, entry)
    await main_instance.async_init()
    
    # Store the main instance and device tracking data
    hass.data[DOMAIN][entry.entry_id] = {
        "main_instance": main_instance,
        "device_instances": {},
        "tracked_devices": set(),
        "entry": entry,
    }
    
    # Set up device tracking if enabled
    if entry.data.get("track_devices", False):
        await _setup_device_tracking(hass, entry)
    
    # Set up platforms for the main instance
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Add update listener for options updates
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry and all its device instances."""
    if DOMAIN not in hass.data or entry.entry_id not in hass.data[DOMAIN]:
        return True
    
    entry_data = hass.data[DOMAIN][entry.entry_id]
    unload_ok = True
    
    # Unload all device instances
    for device_id in list(entry_data["device_instances"].keys()):
        unload_ok = unload_ok and await _unload_device_instance(hass, entry, device_id)
    
    # Unload the main instance
    if "main_instance" in entry_data:
        unload_ok = unload_ok and await entry_data["main_instance"].async_unload()
    
    # Remove from data
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
    
    return unload_ok

async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update options and reload if needed."""
    if DOMAIN not in hass.data or entry.entry_id not in hass.data[DOMAIN]:
        return
    
    entry_data = hass.data[DOMAIN][entry.entry_id]
    
    # Check if device tracking setting changed
    old_track_devices = entry_data["entry"].data.get("track_devices", False)
    new_track_devices = entry.data.get("track_devices", False)
    
    if old_track_devices != new_track_devices:
        # Device tracking setting changed, reload the entry
        await hass.config_entries.async_reload(entry.entry_id)
    else:
        # Just update the coordinator options
        entry_data["entry"] = entry
        
        # Update main instance coordinator
        if "main_instance" in entry_data:
            entry_data["main_instance"].coordinator.update_interval = timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            )
        
        # Update all device instances
        for device_id, instance in entry_data["device_instances"].items():
            instance.coordinator.update_interval = timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            )
            
        # Notify entities to update
        async_dispatcher_send(hass, SIGNAL_UPDATE_ENTITIES, entry.entry_id)

async def _setup_device_tracking(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Set up device tracking for dynamic locations."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    tracked_devices = set()
    
    # Find all device trackers with location
    for state in hass.states.async_all(DEVICE_TRACKER_DOMAIN):
        if state.attributes.get("latitude") is not None:
            tracked_devices.add(state.entity_id)
    
    # Store tracked devices
    entry_data["tracked_devices"] = tracked_devices
    
    # Set up state change listener
    entry_data["remove_listener"] = async_track_state_change_event(
        hass, tracked_devices, 
        lambda event: _handle_device_tracker_update(hass, entry, event)
    )
    
    # Create initial instances for all tracked devices
    for device_entity_id in tracked_devices:
        state = hass.states.get(device_entity_id)
        if state and state.attributes.get("latitude") is not None:
            await _create_device_instance(hass, entry, device_entity_id, state)

async def _create_device_instance(
    hass: HomeAssistant, entry: ConfigEntry, device_entity_id: str, state: State
) -> Optional[OpenMeteoInstance]:
    """Create a new OpenMeteo instance for a device."""
    lat = state.attributes.get("latitude")
    lon = state.attributes.get("longitude")
    
    if lat is None or lon is None:
        return None
    
    # Create a unique ID for this device instance
    device_id = f"{device_entity_id}"
    
    # Pobierz nazwę urządzenia z atrybutów, jeśli dostępna
    device_name = None
    device_registry = await hass.helpers.device_registry.async_get_registry()
    device_entry = device_registry.async_get_device(
        identifiers={"device_tracker": device_entity_id.split('.')[1]}
    )
    
    if device_entry and device_entry.name:
        device_name = device_entry.name
    else:
        device_name = state.name
    
    # Pobierz opcje konfiguracyjne
    use_device_names = entry.options.get(CONF_USE_DEVICE_NAMES, DEFAULT_USE_DEVICE_NAMES)
    area_overrides = entry.options.get(CONF_AREA_OVERRIDES, {})
    
    # Ustal nazwę przyjazną na podstawie konfiguracji
    friendly_name = None
    
    # Jeśli mamy nadpisaną nazwę w konfiguracji, użyj jej
    if device_entity_id in area_overrides:
        friendly_name = f"{entry.data.get(CONF_NAME, DEFAULT_NAME)} - {area_overrides[device_entity_id]}"
    # W przeciwnym razie użyj nazwy urządzenia, jeśli opcja jest włączona
    elif use_device_names and device_name:
        friendly_name = f"{entry.data.get(CONF_NAME, DEFAULT_NAME)} - {device_name}"
    # W przeciwnym razie użyj nazwy trackera
    else:
        friendly_name = f"{entry.data.get(CONF_NAME, DEFAULT_NAME)} - {state.name}"
    
    # Create a new config entry for this device
    config_data = dict(entry.data)
    config_data.update({
        CONF_LATITUDE: lat,
        CONF_LONGITUDE: lon,
        "device_id": device_id,
        "device_entity_id": device_entity_id,
        "friendly_name": friendly_name,
        "device_name": device_name,  # Przechowaj oryginalną nazwę urządzenia
    })
    
    # Create a virtual config entry
    device_entry = ConfigEntry(
        version=entry.version,
        domain=entry.domain,
        title=config_data["friendly_name"],
        data=config_data,
        source=entry.source,
        options=dict(entry.options),
        unique_id=f"{entry.unique_id}_{device_id}",
        entry_id=f"{entry.entry_id}_{device_id}",
    )
    
    # Create and initialize the instance
    instance = OpenMeteoInstance(hass, device_entry, device_id)
    await instance.async_init()
    
    # Store the instance
    hass.data[DOMAIN][entry.entry_id]["device_instances"][device_id] = instance
    
    # Set up platforms for this instance
    for platform in PLATFORMS:
        await hass.config_entries.async_forward_entry_setup(device_entry, platform)
    
    _LOGGER.debug(
        "Created OpenMeteo instance for device %s at %s, %s",
        device_entity_id, lat, lon
    )
    
    return instance

async def _unload_device_instance(
    hass: HomeAssistant, entry: ConfigEntry, device_id: str
) -> bool:
    """Unload and remove a device instance."""
    if (DOMAIN not in hass.data or 
            entry.entry_id not in hass.data[DOMAIN] or 
            device_id not in hass.data[DOMAIN][entry.entry_id]["device_instances"]):
        return True
    
    instance = hass.data[DOMAIN][entry.entry_id]["device_instances"].pop(device_id, None)
    if instance:
        await instance.async_unload()
        _LOGGER.debug("Unloaded OpenMeteo instance for device %s", device_id)
    
    return True

@callback
def _handle_device_tracker_update(
    hass: HomeAssistant, entry: ConfigEntry, event: Event
) -> None:
    """Handle device tracker state changes."""
    entity_id = event.data.get("entity_id")
    new_state = hass.states.get(entity_id)
    
    if not new_state or new_state.attributes.get("latitude") is None:
        # Device lost location, remove its instance if it exists
        hass.async_create_task(_unload_device_instance(hass, entry, entity_id))
        return
    
    # Check if we need to create or update the instance
    hass.async_create_task(_update_device_instance(hass, entry, entity_id, new_state))

async def _update_device_instance(
    hass: HomeAssistant, entry: ConfigEntry, device_entity_id: str, state: State
) -> None:
    """Update or create a device instance."""
    device_id = f"{device_entity_id}"
    entry_data = hass.data[DOMAIN][entry.entry_id]
    
    if device_id in entry_data["device_instances"]:
        # Update existing instance
        instance = entry_data["device_instances"][device_id]
        instance.coordinator.entry.data = {
            **instance.coordinator.entry.data,
            CONF_LATITUDE: state.attributes["latitude"],
            CONF_LONGITUDE: state.attributes["longitude"],
        }
        await instance.coordinator.async_refresh()
    else:
        # Create new instance
        await _create_device_instance(hass, entry, device_entity_id, state)

class OpenMeteoDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the Open-Meteo API."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        self.hass = hass
        self.entry = entry
        self._data: dict[str, Any] = {}
        
        # Pobierz interwał z konfiguracji lub użyj domyślnego
        scan_interval_seconds = entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        
        # Upewnij się, że to int
        if not isinstance(scan_interval_seconds, int):
            scan_interval_seconds = int(scan_interval_seconds)
        
        # Konwertuj na timedelta tylko dla update_interval
        update_interval = timedelta(seconds=scan_interval_seconds)
        
        super().__init__(
            hass,
            _LOGGER,
            name="OpenMeteo",
            update_interval=update_interval,
        )
        
        # Zapisz oryginalną wartość (sekundy) jako atrybut
        self.scan_interval_seconds = scan_interval_seconds

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Open-Meteo API."""
        # Pobierz dane konfiguracyjne
        latitude = self.entry.data[CONF_LATITUDE]
        longitude = self.entry.data[CONF_LONGITUDE]
        timezone = self.entry.data.get(CONF_TIME_ZONE, "auto")
        
        # Get selected variables from options or use defaults
        daily_vars = self.entry.options.get(
            CONF_DAILY_VARIABLES,
            self.entry.data.get(CONF_DAILY_VARIABLES, DEFAULT_DAILY_VARIABLES)
        )
        hourly_vars = self.entry.options.get(
            CONF_HOURLY_VARIABLES,
            self.entry.data.get(CONF_HOURLY_VARIABLES, DEFAULT_HOURLY_VARIABLES)
        )
        
        # Build query parameters
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "timezone": timezone,
            "current_weather": "true",
            "daily": daily_vars,
            "hourly": hourly_vars,
            "timeformat": "iso8601",
            "windspeed_unit": "ms",
            "precipitation_unit": "mm",
            "temperature_unit": "celsius",
        }
        
        # If this is a device instance, we don't need current weather
        if hasattr(self, 'device_id') and self.device_id:
            params["current_weather"] = "false"
        
        _LOGGER.debug("Fetching Open-Meteo data with params: %s", params)
        
        try:
            import aiohttp
            import async_timeout
            from datetime import datetime, timezone
            
            async with async_timeout.timeout(30):
                session = async_get_clientsession(self.hass)
                async with session.get(URL, params=params) as response:
                    if response.status != 200:
                        _LOGGER.error("Error connecting to Open-Meteo API: %s", response.status)
                        raise UpdateFailed(f"Error connecting to Open-Meteo API: {response.status}")
                    
                    data = await response.json()
                    _LOGGER.debug("Received Open-Meteo data")
                    
                    # Add metadata to response
                    data["_metadata"] = {
                        "latitude": latitude,
                        "longitude": longitude,
                        "timezone": timezone,
                        "last_update": datetime.now(timezone.utc).isoformat(),
                    }
                    
                    return data
                    
        except Exception as err:
            _LOGGER.error("Error fetching Open-Meteo data: %s", err, exc_info=True)
            raise UpdateFailed(f"Error fetching Open-Meteo data: {err}") from err