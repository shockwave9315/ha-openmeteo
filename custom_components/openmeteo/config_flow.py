# SPDX-License-Identifier: Apache-2.0
"""Config and options flows for Open-Meteo."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector as sel


def _entity_selector_or_str():
    try:
        return sel.EntitySelector(
            sel.EntitySelectorConfig(domain=["device_tracker", "person"], multiple=False)
        )
    except Exception:
        return str


# Local constant definitions to avoid importing integration modules at import time
DOMAIN = "openmeteo"

CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_MODE = "mode"
MODE_STATIC = "static"
MODE_TRACK = "track"

CONF_UPDATE_INTERVAL = "update_interval"
DEFAULT_UPDATE_INTERVAL = 60
CONF_UNITS = "units"
DEFAULT_UNITS = "metric"

CONF_ENTITY_ID = "entity_id"
CONF_MIN_TRACK_INTERVAL = "min_track_interval"
DEFAULT_MIN_TRACK_INTERVAL = 15

CONF_USE_PLACE_AS_DEVICE_NAME = "use_place_as_device_name"
DEFAULT_USE_PLACE_AS_DEVICE_NAME = False
CONF_SHOW_PLACE_NAME = "show_place_name"
DEFAULT_SHOW_PLACE_NAME = True


def _build_schema(hass: HomeAssistant, mode: str, defaults: dict[str, Any]) -> vol.Schema:
    """Build a schema for config/option flows."""
    data: dict[Any, Any]
    if mode == MODE_TRACK:
        entity_field = _entity_selector_or_str()
        data = {
            vol.Optional(
                CONF_ENTITY_ID, default=defaults.get(CONF_ENTITY_ID)
            ): entity_field,
            vol.Optional(
                CONF_MIN_TRACK_INTERVAL,
                default=defaults.get(CONF_MIN_TRACK_INTERVAL, DEFAULT_MIN_TRACK_INTERVAL),
            ): int,
        }
    else:
        data = {
            vol.Required(
                CONF_LATITUDE,
                default=defaults.get(CONF_LATITUDE, hass.config.latitude),
            ): vol.Coerce(float),
            vol.Required(
                CONF_LONGITUDE,
                default=defaults.get(CONF_LONGITUDE, hass.config.longitude),
            ): vol.Coerce(float),
        }

    data.update(
        {
            vol.Optional(
                CONF_UPDATE_INTERVAL,
                default=defaults.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
            ): int,
            vol.Optional(
                CONF_UNITS, default=defaults.get(CONF_UNITS, DEFAULT_UNITS)
            ): vol.In(["metric", "imperial"]),
            vol.Optional(
                CONF_USE_PLACE_AS_DEVICE_NAME,
                default=defaults.get(
                    CONF_USE_PLACE_AS_DEVICE_NAME, DEFAULT_USE_PLACE_AS_DEVICE_NAME
                ),
            ): bool,
            vol.Optional(
                CONF_SHOW_PLACE_NAME,
                default=defaults.get(CONF_SHOW_PLACE_NAME, DEFAULT_SHOW_PLACE_NAME),
            ): bool,
        }
    )
    return vol.Schema(data)


class OpenMeteoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the integration."""

    VERSION = 2

    def __init__(self) -> None:
        self._mode = MODE_STATIC

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """First step: choose tracking mode."""
        if user_input is not None:
            self._mode = user_input[CONF_MODE]
            return await self.async_step_mode_details()

        schema = vol.Schema(
            {vol.Required(CONF_MODE, default=self._mode): vol.In([MODE_STATIC, MODE_TRACK])}
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_mode_details(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Second step: gather fields for the selected mode."""
        errors: dict[str, str] = {}
        defaults = user_input or {}

        if user_input is not None:
            if self._mode == MODE_TRACK:
                entity = user_input.get(CONF_ENTITY_ID)
                if not entity:
                    errors[CONF_ENTITY_ID] = "required"
            else:
                if not user_input.get(CONF_LATITUDE):
                    errors[CONF_LATITUDE] = "required"
                if not user_input.get(CONF_LONGITUDE):
                    errors[CONF_LONGITUDE] = "required"

            if not errors:
                data = {**user_input, CONF_MODE: self._mode}
                return self.async_create_entry(title="", data=data)

        schema = _build_schema(self.hass, self._mode, defaults)
        return self.async_show_form(
            step_id="mode_details", data_schema=schema, errors=errors
        )


class OpenMeteoOptionsFlowHandler(config_entries.OptionsFlow):
    """Options flow allowing to tweak settings after setup."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return await self.async_step_save(user_input)

        defaults_or_opts = {**self.config_entry.data, **self.config_entry.options}
        entity_field = _entity_selector_or_str()
        schema = vol.Schema(
            {
                vol.Optional(
                    "entity_id", default=defaults_or_opts.get("entity_id")
                ): entity_field,
                vol.Optional(
                    "min_track_interval",
                    default=defaults_or_opts.get(
                        "min_track_interval", DEFAULT_MIN_TRACK_INTERVAL
                    ),
                ): int,
                vol.Optional(
                    "update_interval",
                    default=defaults_or_opts.get("update_interval", DEFAULT_UPDATE_INTERVAL),
                ): int,
                vol.Optional(
                    "units", default=defaults_or_opts.get("units", DEFAULT_UNITS)
                ): vol.In(["metric", "imperial"]),
                vol.Optional(
                    "use_place_as_device_name",
                    default=defaults_or_opts.get(
                        "use_place_as_device_name", DEFAULT_USE_PLACE_AS_DEVICE_NAME
                    ),
                ): bool,
                vol.Optional(
                    "show_place_name",
                    default=defaults_or_opts.get("show_place_name", DEFAULT_SHOW_PLACE_NAME),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_save(self, user_input):
        new_options = {**dict(self.config_entry.options), **(user_input or {})}
        return self.async_create_entry(title="", data=new_options)


