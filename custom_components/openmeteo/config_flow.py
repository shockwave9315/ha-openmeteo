# SPDX-License-Identifier: Apache-2.0
"""Config and options flows for Open-Meteo."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    # modes
    CONF_MODE,
    MODE_STATIC,
    MODE_TRACK,
    # base config
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    CONF_UNITS,
    DEFAULT_UNITS,
    CONF_API_PROVIDER,
    DEFAULT_API_PROVIDER,
    # tracking
    CONF_ENTITY_ID,
    CONF_MIN_TRACK_INTERVAL,
    DEFAULT_MIN_TRACK_INTERVAL,
    # naming / geocode
    CONF_USE_PLACE_AS_DEVICE_NAME,
    DEFAULT_USE_PLACE_AS_DEVICE_NAME,
    CONF_SHOW_PLACE_NAME,
    DEFAULT_SHOW_PLACE_NAME,
    CONF_AREA_NAME_OVERRIDE,
    CONF_GEOCODE_INTERVAL_MIN,
    DEFAULT_GEOCODE_INTERVAL_MIN,
    CONF_GEOCODE_MIN_DISTANCE_M,
    DEFAULT_GEOCODE_MIN_DISTANCE_M,
    CONF_GEOCODER_PROVIDER,
    DEFAULT_GEOCODER_PROVIDER,
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
                default=defaults.get(CONF_MIN_TRACK_INTERVAL, DEFAULT_MIN_TRACK_INTERVAL),
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

    common: dict[Any, Any] = {
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
    }

    # opcje nieblokujące setupu
    common[vol.Optional(
        CONF_USE_PLACE_AS_DEVICE_NAME,
        default=defaults.get(CONF_USE_PLACE_AS_DEVICE_NAME, DEFAULT_USE_PLACE_AS_DEVICE_NAME),
    )] = bool
    common[vol.Optional(
        CONF_SHOW_PLACE_NAME,
        default=defaults.get(CONF_SHOW_PLACE_NAME, DEFAULT_SHOW_PLACE_NAME),
    )] = bool
    common[vol.Optional(
        CONF_AREA_NAME_OVERRIDE,
        default=defaults.get(CONF_AREA_NAME_OVERRIDE, ""),
    )] = str
    common[vol.Optional(
        CONF_GEOCODE_INTERVAL_MIN,
        default=defaults.get(CONF_GEOCODE_INTERVAL_MIN, DEFAULT_GEOCODE_INTERVAL_MIN),
    )] = vol.All(vol.Coerce(int), vol.Range(min=0))
    common[vol.Optional(
        CONF_GEOCODE_MIN_DISTANCE_M,
        default=defaults.get(CONF_GEOCODE_MIN_DISTANCE_M, DEFAULT_GEOCODE_MIN_DISTANCE_M),
    )] = vol.All(vol.Coerce(int), vol.Range(min=0))
    common[vol.Optional(
        CONF_GEOCODER_PROVIDER,
        default=defaults.get(CONF_GEOCODER_PROVIDER, DEFAULT_GEOCODER_PROVIDER),
    )] = vol.In(["osm_nominatim", "photon", "none"])

    data.update(common)
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
                # część pól jako options (nieblokujące)
                options: dict[str, Any] = {}
                if self._mode != MODE_STATIC:
                    use_place = data.pop(CONF_USE_PLACE_AS_DEVICE_NAME, True)
                    options[CONF_USE_PLACE_AS_DEVICE_NAME] = bool(use_place)
                options[CONF_SHOW_PLACE_NAME] = bool(
                    data.pop(CONF_SHOW_PLACE_NAME, True)
                )
                for opt_key in (
                    CONF_AREA_NAME_OVERRIDE,
                    CONF_GEOCODE_INTERVAL_MIN,
                    CONF_GEOCODE_MIN_DISTANCE_M,
                    CONF_GEOCODER_PROVIDER,
                ):
                    if opt_key in data:
                        options[opt_key] = data.pop(opt_key)
                return self.async_create_entry(title="", data=data, options=options)

        schema = _build_schema(self.hass, self._mode, defaults)
        return self.async_show_form(
            step_id="mode_details", data_schema=schema, errors=errors
        )


class OpenMeteoOptionsFlowHandler(config_entries.OptionsFlow):
    """Options flow allowing to tweak settings after setup."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        if user_input is not None:
            return await self.async_step_save(user_input)
        opts = dict(self.config_entry.options)
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_ENTITY_ID, default=opts.get(CONF_ENTITY_ID)
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["device_tracker", "person"])
                ),
                vol.Optional(
                    CONF_MIN_TRACK_INTERVAL,
                    default=opts.get(CONF_MIN_TRACK_INTERVAL, DEFAULT_MIN_TRACK_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=1)),
                vol.Optional(
                    CONF_UPDATE_INTERVAL,
                    default=opts.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=60)),
                vol.Optional(
                    CONF_UNITS, default=opts.get(CONF_UNITS, DEFAULT_UNITS)
                ): vol.In(["metric", "imperial"]),
                vol.Optional(
                    CONF_USE_PLACE_AS_DEVICE_NAME,
                    default=opts.get(
                        CONF_USE_PLACE_AS_DEVICE_NAME, DEFAULT_USE_PLACE_AS_DEVICE_NAME
                    ),
                ): bool,
                vol.Optional(
                    CONF_SHOW_PLACE_NAME,
                    default=opts.get(CONF_SHOW_PLACE_NAME, DEFAULT_SHOW_PLACE_NAME),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_save(
        self, user_input: dict[str, Any] | None
    ) -> config_entries.FlowResult:
        new_options = {**dict(self.config_entry.options), **(user_input or {})}
        return self.async_create_entry(title="", data=new_options)


async def async_get_options_flow(config_entry: config_entries.ConfigEntry):
    return OpenMeteoOptionsFlowHandler(config_entry)


