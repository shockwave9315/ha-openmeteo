"""The Open-Meteo integration with dynamic device tracking."""
from __future__ import annotations

import logging
from datetime import timedelta
from homeassistant.core import HomeAssistant, Event, callback
from homeassistant.config_entries import ConfigEntry, ConfigEntryNotReady
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.aiohttp_client import async_get_clientsession
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
        
        # Initialize coordinates for main instance or device tracker
        if device_id is not None:
            # Handle device tracker coordinates
            state = hass.states.get(device_id)
            if state and state.attributes.get("latitude") is not None:
                try:
                    lat = float(state.attributes["latitude"])
                    lon = float(state.attributes["longitude"])
                    self.coordinator.update_coordinates(lat, lon)
                    _LOGGER.debug("Set coordinates for tracked device %s: (%s, %s)", 
                                device_id, lat, lon)
                except (ValueError, TypeError) as e:
                    _LOGGER.warning("Invalid lat/lon for device %s: %s", 
                                  device_id, str(e))
        elif hasattr(entry, 'data') and isinstance(entry.data, dict):
            # Handle main instance coordinates from config entry
            lat = entry.data.get(CONF_LATITUDE)
            lon = entry.data.get(CONF_LONGITUDE)
            if lat is not None and lon is not None:
                try:
                    self.coordinator.update_coordinates(float(lat), float(lon))
                    _LOGGER.debug("Set initial coordinates for main instance in __init__")
                except (ValueError, TypeError) as e:
                    _LOGGER.warning("Could not set coordinates in instance init: %s", str(e))

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
    """Set up OpenMeteo from a config entry.
    
    Args:
        hass: The Home Assistant instance
        entry: The config entry
        
    Returns:
        bool: True if setup was successful, False otherwise
    """
    hass.data.setdefault(DOMAIN, {})

    try:
        # Create and initialize the main instance
        instance = OpenMeteoInstance(hass, entry)
        await instance.async_init()
        
        # Store the instance with consistent key 'main_instance' for backward compatibility
        hass.data[DOMAIN][entry.entry_id] = {
            "main_instance": instance,
            "device_instances": {}
        }
        
        _LOGGER.debug("Successfully initialized main instance for entry %s", entry.entry_id)
        
    except Exception as err:
        _LOGGER.error("Failed to set up OpenMeteo: %s", str(err), exc_info=True)
        return False

    if entry.data.get("track_devices", False):
        await _setup_device_tracking(hass, entry)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_options))

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle removal of an entry."""
    try:
        if DOMAIN not in hass.data or entry.entry_id not in hass.data[DOMAIN]:
            _LOGGER.debug("No entry data found for %s, nothing to unload", entry.entry_id)
            return True

        entry_data = hass.data[DOMAIN][entry.entry_id]
        unload_ok = True
        
        _LOGGER.debug("Starting to unload entry %s", entry.entry_id)

        # Unload all device instances
        if "device_instances" in entry_data and entry_data["device_instances"]:
            _LOGGER.debug("Unloading %d device instances", len(entry_data["device_instances"]))
            for device_id in list(entry_data["device_instances"].keys()):
                try:
                    if not await _unload_device_instance(hass, entry, device_id):
                        _LOGGER.warning("Failed to unload device instance %s", device_id)
                        unload_ok = False
                except Exception as err:
                    _LOGGER.error("Error unloading device instance %s: %s", device_id, str(err), exc_info=True)
                    unload_ok = False

        # Unload main instance
        if "main_instance" in entry_data and entry_data["main_instance"] is not None:
            _LOGGER.debug("Unloading main instance")
            try:
                if not await entry_data["main_instance"].async_unload():
                    _LOGGER.warning("Failed to unload main instance")
                    unload_ok = False
            except Exception as err:
                _LOGGER.error("Error unloading main instance: %s", str(err), exc_info=True)
                unload_ok = False
        else:
            _LOGGER.debug("No main instance to unload")

        # Clean up data
        if unload_ok:
            _LOGGER.debug("Successfully unloaded entry %s, cleaning up", entry.entry_id)
            hass.data[DOMAIN].pop(entry.entry_id)
            if not hass.data[DOMAIN]:
                _LOGGER.debug("No more entries, removing domain from hass.data")
                hass.data.pop(DOMAIN)
        else:
            _LOGGER.warning("Some components failed to unload properly for entry %s", entry.entry_id)

        return unload_ok
        
    except Exception as err:
        _LOGGER.error("Unexpected error in async_unload_entry: %s", str(err), exc_info=True)
        return False

async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update.
    
    Args:
        hass: The Home Assistant instance
        entry: The config entry being updated
    """
    if DOMAIN not in hass.data or entry.entry_id not in hass.data[DOMAIN]:
        _LOGGER.debug("No entry data found for %s, skipping options update", entry.entry_id)
        return

    entry_data = hass.data[DOMAIN][entry.entry_id]
    
    # Check if device tracking setting has changed
    old_track_devices = entry.data.get("track_devices", False)
    new_track_devices = entry.options.get("track_devices", False)

    if old_track_devices != new_track_devices:
        _LOGGER.debug("Device tracking setting changed, reloading integration")
        await hass.config_entries.async_reload(entry.entry_id)
        return
        
    # Update scan interval for all instances
    new_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    update_interval = timedelta(seconds=new_interval)
    
    # Update main instance if it exists
    if "main_instance" in entry_data and entry_data["main_instance"] is not None:
        entry_data["main_instance"].coordinator.update_interval = update_interval
        _LOGGER.debug("Updated scan interval for main instance to %s seconds", new_interval)
    
    # Update all device instances
    for device_id, instance in entry_data.get("device_instances", {}).items():
        if hasattr(instance, 'coordinator'):
            instance.coordinator.update_interval = update_interval
            _LOGGER.debug("Updated scan interval for device %s to %s seconds", 
                         device_id, new_interval)
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

        device_id = device_entity_id
        
        # Create a basic config with required fields
        config_data = {
            CONF_NAME: f"{device_entity_id.replace('_', ' ').title()}",
            "track_devices": True,
            "device_entity_id": device_entity_id
        }
        
        # For main instance, ensure we have required fields
        if not device_entity_id.startswith('device_tracker.'):
            if not hasattr(entry, 'data') or not isinstance(entry.data, dict):
                _LOGGER.error("Invalid entry data for device %s: entry.data is missing or not a dictionary", 
                            device_entity_id)
                return None
                
            required_fields = [CONF_LATITUDE, CONF_LONGITUDE, CONF_NAME]
            missing_fields = [field for field in required_fields if field not in entry.data]
            if missing_fields:
                _LOGGER.error("Missing required fields in entry data for device %s: %s", 
                            device_entity_id, ", ".join(missing_fields))
                return None
            
            config_data.update(entry.data)
        
        # Create the instance
        instance = OpenMeteoInstance(hass, entry, device_id)
        
        # Update the coordinates in the coordinator
        instance.coordinator.update_coordinates(lat, lon)

        # Initialize the instance
        await instance.async_init()

        # Store the instance
        if DOMAIN not in hass.data or entry.entry_id not in hass.data[DOMAIN]:
            _LOGGER.error("Integration not properly initialized for entry %s", entry.entry_id)
            return None
            
        hass.data[DOMAIN][entry.entry_id].setdefault("device_instances", {})[device_id] = instance

        # Platforms are already loaded in async_setup_entry, no need to forward setup again
        _LOGGER.debug("Successfully created device instance for %s", device_entity_id)
        return instance
        
    except Exception as err:
        _LOGGER.error("Error creating device instance for %s: %s", 
                     device_entity_id, str(err), exc_info=True)
        return None

async def _unload_device_instance(
    hass: HomeAssistant, entry: ConfigEntry, device_id: str
) -> bool:
    """Unload a device instance and clean up its resources.
    
    Args:
        hass: The Home Assistant instance
        entry: The config entry
        device_id: The ID of the device to unload
        
    Returns:
        bool: True if the device was unloaded successfully, False otherwise
    """
    try:
        _LOGGER.debug("Starting to unload device instance %s", device_id)
        
        # Check if the device instance exists
        if (DOMAIN not in hass.data or 
                entry.entry_id not in hass.data[DOMAIN] or 
                device_id not in hass.data[DOMAIN][entry.entry_id].get("device_instances", {})):
            _LOGGER.debug("Device instance %s not found or already unloaded", device_id)
            return True

        # Get and remove the instance from the registry
        instance = hass.data[DOMAIN][entry.entry_id]["device_instances"].pop(device_id, None)
        if not instance:
            _LOGGER.debug("No instance found for device %s", device_id)
            return True
            
        _LOGGER.debug("Found instance for device %s, starting unload", device_id)
        
        # Unload the instance
        try:
            success = await instance.async_unload()
            if not success:
                _LOGGER.warning("Instance for device %s reported unload failure", device_id)
            else:
                _LOGGER.debug("Successfully unloaded device instance %s", device_id)
            return success
            
        except Exception as err:
            _LOGGER.error("Error unloading device instance %s: %s", device_id, str(err), exc_info=True)
            return False
            
    except Exception as err:
        _LOGGER.error("Unexpected error in _unload_device_instance for device %s: %s", 
                     device_id, str(err), exc_info=True)
        return False

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
            
        # For main instance, validate entry data
        if not device_entity_id.startswith('device_tracker.'):
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
                    
                # Update the coordinates in the coordinator
                instance.coordinator.update_coordinates(lat, lon)
                
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
            
            # Store coordinates in instance variables
            self._latitude = None
            self._longitude = None
            self._timezone = "auto"
            
            # Initialize coordinates from entry data if available
            if hasattr(entry, 'data') and isinstance(entry.data, dict):
                self._latitude = entry.data.get(CONF_LATITUDE)
                self._longitude = entry.data.get(CONF_LONGITUDE)
                self._timezone = entry.data.get(CONF_TIME_ZONE, "auto")
            
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

    def update_coordinates(self, latitude: float, longitude: float) -> None:
        """Update the coordinates for this coordinator."""
        self._latitude = float(latitude)
        self._longitude = float(longitude)
        _LOGGER.debug("Updated coordinates to lat=%s, lon=%s", self._latitude, self._longitude)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Open-Meteo API.
        
        Returns:
            dict: The weather data from the API
            
        Raises:
            UpdateFailed: If there's an error fetching the data or if coordinates are not available
        """
        # Fallback to Home Assistant's default coordinates if none are set
        if self._latitude is None or self._longitude is None:
            if hasattr(self.hass.config, 'latitude') and hasattr(self.hass.config, 'longitude'):
                self._latitude = self.hass.config.latitude
                self._longitude = self.hass.config.longitude
                self._timezone = self.hass.config.time_zone or "auto"
                _LOGGER.warning(
                    "Using Home Assistant's default coordinates: lat=%s, lon=%s, tz=%s",
                    self._latitude, self._longitude, self._timezone
                )
            else:
                raise UpdateFailed("Coordinates not set and cannot fall back to Home Assistant's default coordinates")

        daily_vars = self.entry.options.get(
            CONF_DAILY_VARIABLES,
            self.entry.data.get(CONF_DAILY_VARIABLES, DEFAULT_DAILY_VARIABLES)
        )
        hourly_vars = self.entry.options.get(
            CONF_HOURLY_VARIABLES,
            self.entry.data.get(CONF_HOURLY_VARIABLES, DEFAULT_HOURLY_VARIABLES)
        )

        params = {
            "latitude": self._latitude,
            "longitude": self._longitude,
            "timezone": self._timezone,
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
                    # Add location data to the main data dictionary
                    data["latitude"] = self._latitude
                    data["longitude"] = self._longitude
                    data["timezone"] = self._timezone
                    data["_metadata"] = {
                        "last_update": datetime.now(timezone.utc).isoformat(),
                    }
                    return data
        except Exception as err:
            _LOGGER.error("Update failed: %s", err, exc_info=True)
            raise UpdateFailed(f"Fetch error: {err}") from err
