"""""The Open-Meteo integration with dynamic device tracking."""
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
from homeassistant.helpers.typing import EventType

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

    async def async_unload(self) -> None:
        for platform in PLATFORMS:
            await self.hass.config_entries.async_forward_entry_unload(self.entry, platform)

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
    lat = state.attributes.get("latitude")
    lon = state.attributes.get("longitude")

    if lat is None or lon is None:
        return None

    device_id = device_entity_id

    config_data = dict(entry.data)
    config_data.update({
        CONF_LATITUDE: lat,
        CONF_LONGITUDE: lon,
    })

    device_entry = ConfigEntry(
        version=entry.version,
        domain=entry.domain,
        title=entry.title,
        data=config_data,
        source=entry.source,
        options=dict(entry.options),
        unique_id=f"{entry.unique_id}_{device_id}",
        entry_id=f"{entry.entry_id}_{device_id}",
    )

    instance = OpenMeteoInstance(hass, device_entry, device_id)
    await instance.async_init()

    hass.data[DOMAIN][entry.entry_id]["device_instances"][device_id] = instance

    for platform in PLATFORMS:
        await hass.config_entries.async_forward_entry_setup(device_entry, platform)

    return instance

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
    hass: HomeAssistant, entry: ConfigEntry, event: EventType
) -> None:
    entity_id = event.data.get("entity_id")
    new_state = hass.states.get(entity_id)

    if not new_state or new_state.attributes.get("latitude") is None:
        hass.async_create_task(_unload_device_instance(hass, entry, entity_id))
        return

    hass.async_create_task(_update_device_instance(hass, entry, entity_id, new_state))

async def _update_device_instance(
    hass: HomeAssistant, entry: ConfigEntry, device_entity_id: str, state: State
) -> None:
    device_id = f"{device_entity_id}"
    entry_data = hass.data[DOMAIN][entry.entry_id]

    if device_id in entry_data["device_instances"]:
        instance = entry_data["device_instances"][device_id]
        instance.coordinator.entry.data.update({
            CONF_LATITUDE: state.attributes["latitude"],
            CONF_LONGITUDE: state.attributes["longitude"],
        })
        await instance.coordinator.async_refresh()
    else:
        await _create_device_instance(hass, entry, device_entity_id, state)

class OpenMeteoDataUpdateCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, device_id: Optional[str] = None) -> None:
        self.hass = hass
        self.entry = entry
        self.device_id = device_id
        self._data: dict[str, Any] = {}

        scan_interval_seconds = entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )

        if not isinstance(scan_interval_seconds, int):
            scan_interval_seconds = int(scan_interval_seconds)

        update_interval = timedelta(seconds=scan_interval_seconds)

        super().__init__(
            hass,
            _LOGGER,
            name="OpenMeteo",
            update_interval=update_interval,
        )

        self.scan_interval_seconds = scan_interval_seconds

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
                    data["_metadata"] = {
                        "latitude": latitude,
                        "longitude": longitude,
                        "timezone": timezone,
                        "last_update": datetime.now(timezone.utc).isoformat(),
                    }
                    return data
        except Exception as err:
            _LOGGER.error("Update failed: %s", err, exc_info=True)
            raise UpdateFailed(f"Fetch error: {err}") from err
