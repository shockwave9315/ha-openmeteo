"""Config flow for Open-Meteo integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from homeassistant.helpers import selector

from .const import (
    CONF_DAILY_VARIABLES,
    CONF_HOURLY_VARIABLES,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    CONF_TIME_ZONE,
    CONF_TRACKED_ENTITY_ID,
    CONF_TRACKING_MODE,
    DEFAULT_DAILY_VARIABLES,
    DEFAULT_HOURLY_VARIABLES,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    TRACKING_MODE_DEVICE,
    TRACKING_MODE_FIXED,
)

_LOGGER = logging.getLogger(__name__)

class OpenMeteoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Open-Meteo."""

    VERSION = 1
    data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        return await self.async_step_location_mode()

    async def async_step_location_mode(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the location mode selection step."""
        if user_input is not None:
            self.data[CONF_TRACKING_MODE] = user_input[CONF_TRACKING_MODE]
            if user_input[CONF_TRACKING_MODE] == TRACKING_MODE_DEVICE:
                return await self.async_step_device()
            return await self.async_step_fixed_location()

        schema = vol.Schema(
            {
                vol.Required(CONF_TRACKING_MODE, default=TRACKING_MODE_FIXED): vol.In(
                    [TRACKING_MODE_FIXED, TRACKING_MODE_DEVICE]
                )
            }
        )

        return self.async_show_form(step_id="location_mode", data_schema=schema)

    async def async_step_device(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the device tracking step."""
        if user_input is not None:
            self.data.update(user_input)
            return self.async_create_entry(title=self.data[CONF_NAME], data=self.data)

        device_entities = {
            entity.entity_id: entity.name
            for entity in self.hass.states.async_all(("device_tracker", "person"))
        }

        if not device_entities:
            return self.async_abort(reason="no_devices_found")

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(CONF_TRACKED_ENTITY_ID): vol.In(device_entities),
                vol.Optional(CONF_TIME_ZONE, default="auto"): str,
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): cv.positive_int,
            }
        )

        return self.async_show_form(step_id="device", data_schema=schema)

    async def async_step_fixed_location(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the fixed location step."""
        if user_input is not None:
            self.data.update(user_input)
            return self.async_create_entry(title=self.data[CONF_NAME], data=self.data)

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Required(CONF_LATITUDE, default=self.hass.config.latitude): cv.latitude,
                vol.Required(CONF_LONGITUDE, default=self.hass.config.longitude): cv.longitude,
                vol.Optional(CONF_TIME_ZONE, default="auto"): str,
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): cv.positive_int,
            }
        )

        return self.async_show_form(step_id="fixed_location", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OpenMeteoOptionsFlow:
        """Get the options flow for this handler."""
        return OpenMeteoOptionsFlow(config_entry)


class OpenMeteoOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Open-Meteo."""

    def __init__(self, config_entry: config_entries.ConfigEntry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            # Combine existing options with user input
            updated_data = {**self.config_entry.options, **user_input}
            return self.async_create_entry(title="", data=updated_data)

        # Get all device tracker and person entities
        tracking_entities = self.hass.states.async_all(("device_tracker", "person"))
        device_selector = selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[
                    entity.entity_id for entity in tracking_entities
                ],
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )

        # Build schema
        schema = {
            vol.Required(
                CONF_TRACKING_MODE,
                default=self.config_entry.options.get(CONF_TRACKING_MODE, TRACKING_MODE_FIXED),
            ): vol.In([TRACKING_MODE_FIXED, TRACKING_MODE_DEVICE]),
            vol.Optional(
                CONF_TRACKED_ENTITY_ID,
                description={"suggested_value": self.config_entry.options.get(CONF_TRACKED_ENTITY_ID)},
            ): device_selector,
            vol.Optional(
                CONF_DAILY_VARIABLES,
                default=self.config_entry.options.get(CONF_DAILY_VARIABLES, DEFAULT_DAILY_VARIABLES),
            ): cv.multi_select({var: var.replace("_", " ").title() for var in DEFAULT_DAILY_VARIABLES}),
            vol.Optional(
                CONF_HOURLY_VARIABLES,
                default=self.config_entry.options.get(CONF_HOURLY_VARIABLES, DEFAULT_HOURLY_VARIABLES),
            ): cv.multi_select({var: var.replace("_", " ").title() for var in DEFAULT_HOURLY_VARIABLES}),
            vol.Optional(
                CONF_SCAN_INTERVAL,
                default=self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): cv.positive_int,
        }

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema),
        )