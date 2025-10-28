# SPDX-License-Identifier: Apache-2.0
"""Binary sensor platform for Open-Meteo integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import OpenMeteoDataUpdateCoordinator
from .const import (
    ATTRIBUTION,
    CONF_ENABLED_SENSORS,
    CONF_ENABLED_WEATHER_SENSORS,
    DOMAIN,
)

# Polish slug for binary_sensor entity_id
OBJECT_ID_PL = {
    "pv_appliances_ready": "pv_gotowe_agd",
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Open-Meteo binary sensor based on a config entry."""
    # Get coordinator from hass.data
    stored = hass.data[DOMAIN][config_entry.entry_id]
    coordinator: OpenMeteoDataUpdateCoordinator = (
        stored.get("coordinator") if isinstance(stored, dict) else stored
    )

    # Check if PV appliances ready sensor should be created
    options = config_entry.options or {}
    data = config_entry.data or {}

    # Check enabled_weather_sensors (preferred) or legacy enabled_sensors
    enabled_weather = options.get(CONF_ENABLED_WEATHER_SENSORS) or data.get(CONF_ENABLED_WEATHER_SENSORS)
    if not isinstance(enabled_weather, list):
        enabled_weather = options.get(CONF_ENABLED_SENSORS) or data.get(CONF_ENABLED_SENSORS)
        if not isinstance(enabled_weather, list):
            enabled_weather = []

    enabled_set = set(enabled_weather)

    entities = []

    # Add PV appliances ready binary sensor if enabled
    if "pv_appliances_ready" in enabled_set:
        entities.append(OpenMeteoPvAppliancesSensor(coordinator, config_entry))

    async_add_entities(entities, True)


class OpenMeteoPvAppliancesSensor(CoordinatorEntity[OpenMeteoDataUpdateCoordinator], BinarySensorEntity):
    """Binary sensor indicating if appliances can be run based on PV production forecast.

    This sensor uses PV production forecasts to determine if there's sufficient solar
    power to run household appliances (washing machine, dishwasher, dryer) sequentially.

    The sensor is ON when:
    - Average PV production in next 3h >= 1000W
    - Minimum PV production in next 3h >= 600W (60% of average threshold)

    Attributes provide detailed information about production levels and confidence.

    # REQUIRES TESTING - this is a new feature that needs real-world validation
    """

    def __init__(
        self,
        coordinator: OpenMeteoDataUpdateCoordinator,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the PV appliances ready binary sensor."""
        super().__init__(coordinator)
        self._config_entry = config_entry

        # Set entity attributes (has_entity_name=False to keep simple entity_id)
        self._attr_has_entity_name = False
        self._attr_suggested_object_id = OBJECT_ID_PL.get("pv_appliances_ready", "pv_gotowe_agd")
        self._attr_unique_id = f"{config_entry.entry_id}:pv_appliances_ready"
        self._attr_icon = "mdi:washing-machine"
        self._attr_device_class = None  # No standard device_class for this use case
        self._attr_translation_key = "pv_appliances_ready"
        self._attr_name = "Gotowe do uruchomienia AGD"

        # Set device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, config_entry.entry_id)},
            name=config_entry.title,
            manufacturer="Open-Meteo",
        )

    @property
    def is_on(self) -> bool:
        """Return True if appliances can be run (sufficient PV production expected)."""
        if not self.coordinator.data:
            return False
        return self.coordinator.data.get("pv", {}).get("appliances_ready", False)

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success

    @property
    def extra_state_attributes(self):
        """Return detailed attributes about PV production forecast.

        Attributes:
            avg_production_w: Average PV production in next 3 hours (W)
            min_production_w: Minimum PV production in next 3 hours (W)
            total_3h_kwh: Total energy production in next 3 hours (kWh)
            confidence: Confidence level (high/medium/low/unknown/error)
            reasoning: Human-readable explanation of the decision
        """
        if not self.coordinator.data:
            return {}

        attrs = self.coordinator.data.get("pv", {}).get("appliances_ready_attrs", {})
        # Add attribution
        attrs["attribution"] = ATTRIBUTION
        return attrs

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        store = (
            self.hass.data.get(DOMAIN, {})
            .get("entries", {})
            .setdefault(self._config_entry.entry_id, {})
        )
        store.setdefault("entities", []).append(self)

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        store = (
            self.hass.data.get(DOMAIN, {})
            .get("entries", {})
            .get(self._config_entry.entry_id)
        )
        if store and self in store.get("entities", []):
            store["entities"].remove(self)
        await super().async_will_remove_from_hass()
