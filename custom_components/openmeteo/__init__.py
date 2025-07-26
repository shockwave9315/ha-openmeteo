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
from homeassistant.core import Event

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
    DEFAULT_USE_DEVICE_NAMES,
    CONF_USE_DEVICE_NAMES,
    CONF_AREA_OVERRIDES,
    DOMAIN,
    URL,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["weather", "sensor"]
SIGNAL_UPDATE_ENTITIES = f"{DOMAIN}_update_entities"

class OpenMeteoInstance:
    """Represents a single OpenMeteo instance for a specific location."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, device_id: str = None):
        self.hass = hass
        self.entry = entry
        self.device_id = device_id
        self.coordinator = OpenMeteoDataUpdateCoordinator(hass, entry, device_id)
        self.entities = set()

    async def async_init(self) -> None:
        await self.coordinator.async_config_entry_first_refresh()

    async def async_unload(self) -> bool:
        """Unload the instance and all its platforms.
        
        Returns:
            bool: True if all platforms were unloaded successfully, False otherwise.
        """
        success = True
        for platform in PLATFORMS:
            try:
                result = await self.hass.config_entries.async_forward_entry_unload(self.entry, platform)
                if not result:
                    _LOGGER.warning("Failed to unload platform %s", platform)
                    success = False
            except Exception as err:
                _LOGGER.error("Error unloading platform %s: %s", platform, str(err), exc_info=True)
                success = False
        return success

    def add_entity(self, entity_id: str) -> None:
        self.entities.add(entity_id)

    def remove_entity(self, entity_id: str) -> None:
        self.entities.discard(entity_id)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    main_instance = OpenMeteoInstance(hass, entry)
    await main_instance.async_init()

    hass.data[DOMAIN][entry.entry_id] = {
        "main_instance": main_instance,
        "device_instances": {},
        "tracked_devices": set(),
        "entry": entry,
    }

    if entry.data.get("track_devices", False):
        await _setup_device_tracking(hass, entry)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if DOMAIN not in hass.data or entry.entry_id not in hass.data[DOMAIN]:
        return True

    entry_data = hass.data[DOMAIN][entry.entry_id]
    unload_ok = True

    for device_id in list(entry_data["device_instances"].keys()):
        unload_ok = unload_ok and await _unload_device_instance(hass, entry, device_id)

    if "main_instance" in entry_data:
        unload_ok = unload_ok and await entry_data["main_instance"].async_unload()

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)

    return unload_ok

async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    if DOMAIN not in hass.data or entry.entry_id not in hass.data[DOMAIN]:
        return

    entry_data = hass.data[DOMAIN][entry.entry_id]

    old_track_devices = entry_data["entry"].data.get("track_devices", False)
    new_track_devices = entry.data.get("track_devices", False)

    if old_track_devices != new_track_devices:
        await hass.config_entries.async_reload(entry.entry_id)
    else:
        entry_data["entry"] = entry
        if "main_instance" in entry_data:
            entry_data["main_instance"].coordinator.update_interval = timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            )
        for device_id, instance in entry_data["device_instances"].items():
            instance.coordinator.update_interval = timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            )
        async_dispatcher_send(hass, SIGNAL_UPDATE_ENTITIES, entry.entry_id)

async def _setup_device_tracking(hass: HomeAssistant, entry: ConfigEntry) -> None:
    entry_data = hass.data[DOMAIN][entry.entry_id]
    tracked_devices = set()

    for state in hass.states.async_all(DEVICE_TRACKER_DOMAIN):
        if state.attributes.get("latitude") is not None:
            tracked_devices.add(state.entity_id)

    entry_data["tracked_devices"] = tracked_devices

    entry_data["remove_listener"] = async_track_state_change_event(
        hass, tracked_devices, 
        lambda event: _handle_device_tracker_update(hass, entry, event)
    )

    for device_entity_id in tracked_devices:
        state = hass.states.get(device_entity_id)
        if state and state.attributes.get("latitude") is not None:
            await _create_device_instance(hass, entry, device_entity_id, state)

async def _create_device_instance(
    hass: HomeAssistant, entry: ConfigEntry, device_entity_id: str, state: State
) -> Optional[OpenMeteoInstance]:
    """Create a new device instance with validation and error handling."""
    try:
        _LOGGER.debug("Creating device instance for %s", device_entity_id)
        
        if not isinstance(state, State) or not hasattr(state, 'attributes'):
            _LOGGER.error("Invalid state object provided for device %s", device_entity_id)
            return None
            
        lat = state.attributes.get("latitude")
        lon = state.attributes.get("longitude")

        if lat is None or lon is None:
            _LOGGER.warning("Device %s is missing latitude/longitude in attributes", device_entity_id)
            return None

        # Validate entry data
        if not hasattr(entry, 'data') or not isinstance(entry.data, dict):
            _LOGGER.error("Invalid entry data for device %s: entry.data is missing or not a dictionary", 
                         device_entity_id)
            return None
            
        # Ensure required fields are present in entry data
        required_fields = [CONF_LATITUDE, CONF_LONGITUDE, CONF_NAME]
        missing_fields = [field for field in required_fields if field not in entry.data]
        if missing_fields:
            _LOGGER.error("Missing required fields in entry data for device %s: %s", 
                         device_entity_id, ", ".join(missing_fields))
            return None

        device_id = device_entity_id
        
        # Create a copy of entry data to avoid modifying the original
        config_data = dict(entry.data)
        
        # Update with device-specific coordinates
        config_data.update({
            CONF_LATITUDE: float(lat),
            CONF_LONGITUDE: float(lon),
        })

        # Initialize the instance
        instance = OpenMeteoInstance(hass, entry, device_id)
        await instance.async_init()

        # Store the instance
        if DOMAIN not in hass.data or entry.entry_id not in hass.data[DOMAIN]:
            _LOGGER.error("Integration not properly initialized for entry %s", entry.entry_id)
            return None
            
        hass.data[DOMAIN][entry.entry_id].setdefault("device_instances", {})[device_id] = instance

        # Set up platforms for the new instance
        for platform in PLATFORMS:
            try:
                await hass.config_entries.async_forward_entry_setup(entry, platform)
            except Exception as platform_err:
                _LOGGER.error("Failed to setup platform %s for device %s: %s", 
                            platform, device_entity_id, str(platform_err))
                # Continue with other platforms even if one fails
                continue

        _LOGGER.debug("Successfully created device instance for %s", device_entity_id)
        return instance
        
    except Exception as err:
        _LOGGER.error("Error creating device instance for %s: %s", 
                     device_entity_id, str(err), exc_info=True)
        return None

async def _unload_device_instance(
    hass: HomeAssistant, entry: ConfigEntry, device_id: str
) -> bool:
    if (DOMAIN not in hass.data or 
            entry.entry_id not in hass.data[DOMAIN] or 
            device_id not in hass.data[DOMAIN][entry.entry_id]["device_instances"]):
        return True

    instance = hass.data[DOMAIN][entry.entry_id]["device_instances"].pop(device_id, None)
    if instance:
        await instance.async_unload()
    return True

@callback
def _handle_device_tracker_update(
    hass: HomeAssistant, entry: ConfigEntry, event: Event
) -> None:
    """Handle device tracker state changes in a thread-safe way."""
    entity_id = event.data.get("entity_id")
    new_state = hass.states.get(entity_id)

    if not new_state or new_state.attributes.get("latitude") is None:
        hass.add_job(_unload_device_instance(hass, entry, entity_id))
    else:
        hass.add_job(_update_device_instance(hass, entry, entity_id, new_state))

async def _update_device_instance(
    hass: HomeAssistant, entry: ConfigEntry, device_entity_id: str, state: State
) -> None:
    """Update an existing device instance with new state data."""
    try:
        _LOGGER.debug("Updating device instance for %s", device_entity_id)
        
        # Validate input parameters
        if not isinstance(device_entity_id, str) or not device_entity_id:
            _LOGGER.error("Invalid device_entity_id provided")
            return
            
        if not isinstance(state, State) or not hasattr(state, 'attributes'):
            _LOGGER.error("Invalid state object provided for device %s", device_entity_id)
            return
            
        # Validate required attributes
        lat = state.attributes.get("latitude")
        lon = state.attributes.get("longitude")
        
        if lat is None or lon is None:
            _LOGGER.warning("Cannot update device %s: missing latitude/longitude in state attributes", 
                          device_entity_id)
            return
            
        # Validate entry data
        if not hasattr(entry, 'data') or not isinstance(entry.data, dict):
            _LOGGER.error("Invalid entry data for device %s: entry.data is missing or not a dictionary", 
                         device_entity_id)
            return
            
        device_id = f"{device_entity_id}"
        
        # Safely get entry data
        try:
            entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
            if not entry_data:
                _LOGGER.error("No entry data found for entry %s", entry.entry_id)
                return
                
            device_instances = entry_data.get("device_instances", {})
            
            if device_id in device_instances:
                instance = device_instances[device_id]
                if not hasattr(instance, 'coordinator') or not hasattr(instance.coordinator, 'entry'):
                    _LOGGER.error("Invalid instance or coordinator for device %s", device_id)
                    return
                    
                # Create a copy of the data to avoid modifying the original
                updated_data = dict(instance.coordinator.entry.data)
                updated_data.update({
                    CONF_LATITUDE: float(lat),
                    CONF_LONGITUDE: float(lon),
                })
                
                # Update the coordinator's entry data
                instance.coordinator.entry.data = updated_data
                
                # Refresh the coordinator
                try:
                    await instance.coordinator.async_refresh()
                    _LOGGER.debug("Successfully updated device instance %s", device_id)
                except Exception as refresh_err:
                    _LOGGER.error("Failed to refresh coordinator for device %s: %s", 
                                device_id, str(refresh_err))
            else:
                # Create a new instance if it doesn't exist
                _LOGGER.debug("Device %s not found, creating new instance", device_id)
                await _create_device_instance(hass, entry, device_entity_id, state)
                
        except KeyError as key_err:
            _LOGGER.error("Key error while updating device %s: %s", device_id, str(key_err))
        except Exception as data_err:
            _LOGGER.error("Error accessing data for device %s: %s", device_id, str(data_err))
            
    except Exception as err:
        _LOGGER.error("Unexpected error in _update_device_instance for %s: %s", 
                     device_entity_id, str(err), exc_info=True)

class OpenMeteoDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator for managing OpenMeteo data updates with error handling."""
    
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, device_id: Optional[str] = None) -> None:
        """Initialize the OpenMeteo data update coordinator."""
        try:
            if not isinstance(hass, HomeAssistant):
                raise ValueError("Invalid HomeAssistant instance provided")
                
            if not isinstance(entry, ConfigEntry):
                raise ValueError("Invalid ConfigEntry provided")
                
            self.hass = hass
            self.entry = entry
            self.device_id = device_id
            self._data: dict[str, Any] = {}
            self._last_update_success = False
            
            # Validate and get scan interval
            try:
                scan_interval_seconds = entry.options.get(
                    CONF_SCAN_INTERVAL,
                    entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                )
                
                # Ensure scan_interval_seconds is a valid integer
                try:
                    scan_interval_seconds = int(scan_interval_seconds)
                    if scan_interval_seconds < 30:  # Minimum 30 seconds between updates
                        _LOGGER.warning(
                            "Scan interval %s is too low, using minimum of 30 seconds",
                            scan_interval_seconds
                        )
                        scan_interval_seconds = 30
                except (TypeError, ValueError) as err:
                    _LOGGER.warning(
                        "Invalid scan interval %s, using default %s: %s",
                        scan_interval_seconds, DEFAULT_SCAN_INTERVAL, str(err)
                    )
                    scan_interval_seconds = DEFAULT_SCAN_INTERVAL
                    
                update_interval = timedelta(seconds=scan_interval_seconds)
                
            except Exception as interval_err:
                _LOGGER.error(
                    "Error setting up scan interval, using default: %s",
                    str(interval_err)
                )
                update_interval = timedelta(seconds=DEFAULT_SCAN_INTERVAL)
                scan_interval_seconds = DEFAULT_SCAN_INTERVAL
            
            # Initialize the parent class
            try:
                super().__init__(
                    hass,
                    _LOGGER,
                    name=f"OpenMeteo{' ' + str(device_id) if device_id else ''}",
                    update_interval=update_interval,
                )
            except Exception as parent_err:
                _LOGGER.error("Failed to initialize parent class: %s", str(parent_err))
                raise
                
            self.scan_interval_seconds = scan_interval_seconds
            _LOGGER.debug(
                "Initialized OpenMeteoDataUpdateCoordinator for device %s with interval %s",
                device_id or 'main',
                update_interval
            )
            
        except Exception as init_err:
            _LOGGER.critical(
                "Failed to initialize OpenMeteoDataUpdateCoordinator: %s",
                str(init_err),
                exc_info=True
            )
            raise

    async def _async_update_data(self) -> dict[str, Any]:
        latitude = self.entry.data[CONF_LATITUDE]
        longitude = self.entry.data[CONF_LONGITUDE]
        timezone = self.entry.data.get(CONF_TIME_ZONE, "auto")

        daily_vars = self.entry.options.get(
            CONF_DAILY_VARIABLES,
            self.entry.data.get(CONF_DAILY_VARIABLES, DEFAULT_DAILY_VARIABLES)
        )
        hourly_vars = self.entry.options.get(
            CONF_HOURLY_VARIABLES,
            self.entry.data.get(CONF_HOURLY_VARIABLES, DEFAULT_HOURLY_VARIABLES)
        )

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

        if self.device_id:
            params["current_weather"] = "false"

        try:
            import aiohttp
            import async_timeout
            from datetime import datetime, timezone

            async with async_timeout.timeout(30):
                session = async_get_clientsession(self.hass)
                async with session.get(URL, params=params) as response:
                    if response.status != 200:
                        raise UpdateFailed(f"API error: {response.status}")

                    data = await response.json()
                    # Dodajemy dane lokalizacyjne do głównego słownika danych
                    data["latitude"] = latitude
                    data["longitude"] = longitude
                    data["timezone"] = timezone
                    data["_metadata"] = {
                        "last_update": datetime.now(timezone.utc).isoformat(),
                    }
                    return data
        except Exception as err:
            _LOGGER.error("Update failed: %s", err, exc_info=True)
            raise UpdateFailed(f"Fetch error: {err}") from err
