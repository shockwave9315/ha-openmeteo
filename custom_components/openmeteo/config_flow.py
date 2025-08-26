# SPDX-License-Identifier: Apache-2.0
"""Config and options flows for Open-Meteo."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.selector import selector

# Local constant definitions to avoid importing integration modules at import time
DOMAIN = "openmeteo"

CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_MODE = "mode"
MODE_STATIC = "static"
MODE_TRACK = "track"

CONF_UPDATE_INTERVAL = "update_interval"
DEFAULT_UPDATE_INTERVAL = 600
CONF_UNITS = "units"
DEFAULT_UNITS = "metric"

CONF_ENTITY_ID = "entity_id"
CONF_MIN_TRACK_INTERVAL = "min_track_interval"
DEFAULT_MIN_TRACK_INTERVAL = 15

CONF_USE_PLACE_AS_DEVICE_NAME = "use_place_as_device_name"
DEFAULT_USE_PLACE_AS_DEVICE_NAME = True
CONF_SHOW_PLACE_NAME = "show_place_name"
DEFAULT_SHOW_PLACE_NAME = True
CONF_AREA_NAME_OVERRIDE = "area_name_override"
CONF_GEOCODE_INTERVAL_MIN = "geocode_interval_min"
DEFAULT_GEOCODE_INTERVAL_MIN = 120
CONF_GEOCODE_MIN_DISTANCE_M = "geocode_min_distance_m"
DEFAULT_GEOCODE_MIN_DISTANCE_M = 500
CONF_GEOCODER_PROVIDER = "geocoder_provider"
DEFAULT_GEOCODER_PROVIDER = "osm_nominatim"


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

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return await self.async_step_save(user_input)

        opts = dict(self.config_entry.options)
        schema = vol.Schema(
            {
                vol.Optional("entity_id", default=opts.get("entity_id")): str,
                vol.Optional(
                    "min_track_interval",
                    default=opts.get("min_track_interval", 15),
                ): int,
                vol.Optional(
                    "update_interval",
                    default=opts.get("update_interval", 60),
                ): int,
                vol.Optional(
                    "units", default=opts.get("units", "metric")
                ): vol.In(["metric", "imperial"]),
                vol.Optional(
                    "use_place_as_device_name",
                    default=opts.get("use_place_as_device_name", False),
                ): bool,
                vol.Optional(
                    "show_place_name",
                    default=opts.get("show_place_name", True),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_save(self, user_input):
        new_options = {**dict(self.config_entry.options), **(user_input or {})}
        return self.async_create_entry(title="", data=new_options)


async def async_get_options_flow(config_entry):
    return OpenMeteoOptionsFlowHandler(config_entry)


