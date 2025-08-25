# SPDX-License-Identifier: Apache-2.0
# SPDX-License-Identifier: Apache-2.0
"""Config and options flows for Open-Meteo."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import (
    CONF_AREA_NAME_OVERRIDE,
    CONF_ENTITY_ID,
    CONF_MIN_TRACK_INTERVAL,
    CONF_MODE,
    CONF_UNITS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_MIN_TRACK_INTERVAL,
    DEFAULT_UNITS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MODE_STATIC,
    MODE_TRACK,
    CONF_API_PROVIDER,
    DEFAULT_API_PROVIDER,
    CONF_USE_PLACE_AS_DEVICE_NAME,
    DEFAULT_USE_PLACE_AS_DEVICE_NAME,
)


def _build_schema(hass: HomeAssistant, mode: str, defaults: dict[str, Any]) -> vol.Schema:
    """Build a schema for config/option flows."""
    if mode == MODE_TRACK:
        data: dict[Any, Any] = {
            vol.Required(
                CONF_ENTITY_ID, default=defaults.get(CONF_ENTITY_ID, None)
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["device_tracker", "person"])
            ),
            vol.Optional(
                CONF_MIN_TRACK_INTERVAL,
                default=defaults.get(
                    CONF_MIN_TRACK_INTERVAL, DEFAULT_MIN_TRACK_INTERVAL
                ),
            ): vol.All(vol.Coerce(int), vol.Range(min=1)),
        }
    else:
        data = {
            vol.Required(
                CONF_LATITUDE,
                default=defaults.get(CONF_LATITUDE, hass.config.latitude),
            ): vol.All(vol.Coerce(float), vol.Range(min=-90, max=90)),
            vol.Required(
                CONF_LONGITUDE,
                default=defaults.get(CONF_LONGITUDE, hass.config.longitude),
            ): vol.All(vol.Coerce(float), vol.Range(min=-180, max=180)),
        }

    data.update(
        {
            vol.Required(
                CONF_UPDATE_INTERVAL,
                default=defaults.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
            ): vol.All(vol.Coerce(int), vol.Range(min=60)),
            vol.Required(
                CONF_UNITS, default=defaults.get(CONF_UNITS, DEFAULT_UNITS)
            ): vol.In(["metric", "imperial"]),
            vol.Required(
                CONF_API_PROVIDER,
                default=defaults.get(CONF_API_PROVIDER, DEFAULT_API_PROVIDER),
            ): vol.In(["open_meteo"]),
            vol.Required(
                CONF_USE_PLACE_AS_DEVICE_NAME,
                default=defaults.get(
                    CONF_USE_PLACE_AS_DEVICE_NAME,
                    DEFAULT_USE_PLACE_AS_DEVICE_NAME,
                ),
            ): bool,
            vol.Optional(
                CONF_AREA_NAME_OVERRIDE,
                default=defaults.get(CONF_AREA_NAME_OVERRIDE, ""),
            ): str,
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
                    state = self.hass.states.get(entity)
                    if not state or "latitude" not in state.attributes or "longitude" not in state.attributes:
                        errors[CONF_ENTITY_ID] = "invalid_entity"
            else:
                if not user_input.get(CONF_LATITUDE):
                    errors[CONF_LATITUDE] = "required"
                if not user_input.get(CONF_LONGITUDE):
                    errors[CONF_LONGITUDE] = "required"

            if not errors:
                data = {**user_input, CONF_MODE: self._mode}
                use_place = data.pop(
                    CONF_USE_PLACE_AS_DEVICE_NAME, DEFAULT_USE_PLACE_AS_DEVICE_NAME
                )
                return self.async_create_entry(
                    title="", data=data, options={CONF_USE_PLACE_AS_DEVICE_NAME: use_place}
                )

        schema = _build_schema(self.hass, self._mode, defaults)
        return self.async_show_form(
            step_id="mode_details", data_schema=schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OpenMeteoOptionsFlow:
        return OpenMeteoOptionsFlow(config_entry)


class OpenMeteoOptionsFlow(config_entries.OptionsFlow):
    """Options flow allowing to tweak settings after setup."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry
        # Copy options so we can safely mutate defaults
        self._options: dict[str, Any] = dict(entry.options)
        eff = {**entry.data, **entry.options}
        # Migrate old configs that stored an empty string for the entity
        if self._options.get(CONF_ENTITY_ID) == "":
            self._options[CONF_ENTITY_ID] = None
        self._mode = eff.get(CONF_MODE, MODE_STATIC)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """First step: choose tracking mode."""

        if user_input is not None:
            self._mode = user_input[CONF_MODE]
            return await self.async_step_mode_details()
        schema = vol.Schema(
            {
                vol.Required(CONF_MODE, default=self._mode): vol.In(
                    [MODE_STATIC, MODE_TRACK]
                )
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_mode_details(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Second step: gather fields for the selected mode."""
        errors: dict[str, str] = {}

        data = {**self._entry.data, **self._entry.options}
        defaults = user_input or data


        if user_input is not None:
            if self._mode == MODE_TRACK:
                if not user_input.get(CONF_ENTITY_ID):
                    errors[CONF_ENTITY_ID] = "required"
            else:
                if not user_input.get(CONF_LATITUDE):
                    errors[CONF_LATITUDE] = "required"
                if not user_input.get(CONF_LONGITUDE):
                    errors[CONF_LONGITUDE] = "required"

            if not errors:
                new_options: dict[str, Any] = {**self._entry.options}
                if self._mode == MODE_TRACK:

                    new_options.pop(CONF_LATITUDE, None)
                    new_options.pop(CONF_LONGITUDE, None)
                else:

                    new_options.pop(CONF_ENTITY_ID, None)
                    new_options.pop(CONF_MIN_TRACK_INTERVAL, None)
                new_options.update(user_input)
                new_options[CONF_MODE] = self._mode
                return self.async_create_entry(title="", data=new_options)

        if self._mode == MODE_TRACK:
            schema = vol.Schema(
                {
                    vol.Required(
                        CONF_ENTITY_ID,

                        default=defaults.get(CONF_ENTITY_ID, None),
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain=["device_tracker", "person"]

                        )
                    ),
                    vol.Optional(
                        CONF_MIN_TRACK_INTERVAL,
                        default=defaults.get(
                            CONF_MIN_TRACK_INTERVAL, DEFAULT_MIN_TRACK_INTERVAL
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1)),
                    vol.Required(
                        CONF_UPDATE_INTERVAL,
                        default=defaults.get(
                            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=60)),
                    vol.Required(
                        CONF_UNITS, default=defaults.get(CONF_UNITS, DEFAULT_UNITS)
                    ): vol.In(["metric", "imperial"]),
                    vol.Required(
                        CONF_API_PROVIDER,
                        default=defaults.get(
                            CONF_API_PROVIDER, DEFAULT_API_PROVIDER
                        ),
                    ): vol.In(["open_meteo"]),
                    vol.Required(
                        CONF_USE_PLACE_AS_DEVICE_NAME,
                        default=defaults.get(
                            CONF_USE_PLACE_AS_DEVICE_NAME,
                            DEFAULT_USE_PLACE_AS_DEVICE_NAME,
                        ),
                    ): bool,
                    vol.Optional(
                        CONF_AREA_NAME_OVERRIDE,
                        default=defaults.get(CONF_AREA_NAME_OVERRIDE, ""),
                    ): str,
                }
            )
        else:
            schema = vol.Schema(
                {
                    vol.Required(
                        CONF_LATITUDE,
                        default=defaults.get(
                            CONF_LATITUDE, self.hass.config.latitude
                        ),
                    ): vol.All(vol.Coerce(float), vol.Range(min=-90, max=90)),
                    vol.Required(
                        CONF_LONGITUDE,
                        default=defaults.get(
                            CONF_LONGITUDE, self.hass.config.longitude
                        ),
                    ): vol.All(vol.Coerce(float), vol.Range(min=-180, max=180)),
                    vol.Required(
                        CONF_UPDATE_INTERVAL,
                        default=defaults.get(
                            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=60)),
                    vol.Required(
                        CONF_UNITS, default=defaults.get(CONF_UNITS, DEFAULT_UNITS)
                    ): vol.In(["metric", "imperial"]),
                    vol.Required(
                        CONF_API_PROVIDER,
                        default=defaults.get(
                            CONF_API_PROVIDER, DEFAULT_API_PROVIDER
                        ),
                    ): vol.In(["open_meteo"]),
                    vol.Required(
                        CONF_USE_PLACE_AS_DEVICE_NAME,
                        default=defaults.get(
                            CONF_USE_PLACE_AS_DEVICE_NAME,
                            DEFAULT_USE_PLACE_AS_DEVICE_NAME,
                        ),
                    ): bool,
                    vol.Optional(
                        CONF_AREA_NAME_OVERRIDE,
                        default=defaults.get(CONF_AREA_NAME_OVERRIDE, ""),
                    ): str,
                }
            )

        return self.async_show_form(
            step_id="mode_details", data_schema=schema, errors=errors
        )

