"""Config flow for Open-Meteo integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_DAILY_VARIABLES,
    CONF_HOURLY_VARIABLES,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_SCAN_INTERVAL,
    CONF_TIME_ZONE,
    CONF_TRACKED_ENTITY_ID,
    CONF_TRACKING_MODE,
    DEFAULT_DAILY_VARIABLES,
    DEFAULT_HOURLY_VARIABLES,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIME_ZONE,
    DOMAIN,
    TRACKING_MODE_DEVICE,
    TRACKING_MODE_FIXED,
    TIME_ZONES,
)

_LOGGER = logging.getLogger(__name__)


def create_location_schema(hass: HomeAssistant) -> vol.Schema:
    """Create schema for location and tracking options."""
    ha_lat = hass.config.latitude
    ha_lon = hass.config.longitude
    return vol.Schema(
        {
            vol.Required(CONF_TRACKING_MODE, default=TRACKING_MODE_FIXED): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(value=TRACKING_MODE_FIXED, label="Fixed Location"),
                        selector.SelectOptionDict(value=TRACKING_MODE_DEVICE, label="Tracked Device"),
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(CONF_LATITUDE, default=ha_lat): vol.Coerce(float),
            vol.Optional(CONF_LONGITUDE, default=ha_lon): vol.Coerce(float),
        }
    )


def get_tracked_entities_options(hass: HomeAssistant, current_entity: str | None = None) -> list[selector.SelectOptionDict]:
    """Dynamically get a list of trackable entities with their friendly names."""
    er_reg = er.async_get(hass)
    options = []
    
    for ent in er_reg.entities.values():
        if ent.domain in ("device_tracker", "person"):
            label = ent.original_name or ent.name or ent.entity_id
            options.append(selector.SelectOptionDict(value=ent.entity_id, label=label))
            
    # Sortowanie z użyciem casefold() dla lepszej obsługi znaków lokalnych
    options.sort(key=lambda o: o["label"].casefold())

    if current_entity and all(o["value"] != current_entity for o in options):
        options.insert(0, selector.SelectOptionDict(value=current_entity, label=current_entity))
    
    return options


class OpenMeteoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Open-Meteo."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize Open-Meteo config flow."""
        self._init_data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        if user_input is not None:
            self._init_data = user_input
            
            if user_input.get(CONF_TRACKING_MODE) == TRACKING_MODE_DEVICE:
                return await self.async_step_device()
            
            return self.async_create_entry(title="Open-Meteo", data=self._init_data)

        return self.async_show_form(
            step_id="user",
            data_schema=create_location_schema(self.hass),
            errors={},
        )

    async def async_step_device(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the device selection step."""
        if user_input is not None:
            data = {k: v for k, v in self._init_data.items() if k not in (CONF_LATITUDE, CONF_LONGITUDE)}
            data.update(user_input)
            return self.async_create_entry(title="Open-Meteo", data=data)

        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema({
                vol.Required(CONF_TRACKED_ENTITY_ID): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=get_tracked_entities_options(self.hass),
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                )
            }),
            errors={},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> OpenMeteoOptionsFlow:
        """Get the options flow for this handler."""
        return OpenMeteoOptionsFlow(config_entry)


class OpenMeteoOptionsFlow(config_entries.OptionsFlow):
    """Handle Open-Meteo options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize Open-Meteo options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        data = self.config_entry.data

        tracking_mode = options.get(CONF_TRACKING_MODE, data.get(CONF_TRACKING_MODE, TRACKING_MODE_FIXED))
        tracked_entity_id = options.get(CONF_TRACKED_ENTITY_ID, data.get(CONF_TRACKED_ENTITY_ID))

        options_schema = vol.Schema({
            vol.Required(
                CONF_SCAN_INTERVAL,
                default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): int,
            vol.Required(
                CONF_TIME_ZONE,
                default=options.get(CONF_TIME_ZONE, DEFAULT_TIME_ZONE)
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=TIME_ZONES,
                    mode=selector.SelectSelectorMode.DROPDOWN
                )
            ),
            vol.Required(
                CONF_HOURLY_VARIABLES,
                default=options.get(CONF_HOURLY_VARIABLES, DEFAULT_HOURLY_VARIABLES)
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[{"value": var, "label": var} for var in DEFAULT_HOURLY_VARIABLES],
                    multiple=True,
                    mode=selector.SelectSelectorMode.LISTBOX
                )
            ),
            vol.Required(
                CONF_DAILY_VARIABLES,
                default=options.get(CONF_DAILY_VARIABLES, DEFAULT_DAILY_VARIABLES)
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[{"value": var, "label": var} for var in DEFAULT_DAILY_VARIABLES],
                    multiple=True,
                    mode=selector.SelectSelectorMode.LISTBOX
                )
            ),
            vol.Required(
                CONF_TRACKING_MODE,
                default=tracking_mode
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(value=TRACKING_MODE_FIXED, label="Fixed Location"),
                        selector.SelectOptionDict(value=TRACKING_MODE_DEVICE, label="Tracked Device"),
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
        })

        if tracking_mode == TRACKING_MODE_FIXED:
            options_schema = options_schema.extend({
                vol.Required(
                    CONF_LATITUDE,
                    default=options.get(CONF_LATITUDE, data.get(CONF_LATITUDE, self.hass.config.latitude))
                ): vol.Coerce(float),
                vol.Required(
                    CONF_LONGITUDE,
                    default=options.get(CONF_LONGITUDE, data.get(CONF_LONGITUDE, self.hass.config.longitude))
                ): vol.Coerce(float),
            })
        elif tracking_mode == TRACKING_MODE_DEVICE:
            device_options = get_tracked_entities_options(self.hass, tracked_entity_id)
            options_schema = options_schema.extend({
                vol.Required(
                    CONF_TRACKED_ENTITY_ID,
                    default=tracked_entity_id
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=device_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                )
            })

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
            errors={},
        )