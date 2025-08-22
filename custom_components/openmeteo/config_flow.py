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
)


def _build_schema(hass: HomeAssistant, mode: str, defaults: dict[str, Any]) -> vol.Schema:
    """Build a schema for config/option flows depending on mode."""
    data: dict[Any, Any] = {
        vol.Required(CONF_MODE, default=mode): vol.In([MODE_STATIC, MODE_TRACK]),
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
        vol.Optional(
            CONF_AREA_NAME_OVERRIDE,
            default=defaults.get(CONF_AREA_NAME_OVERRIDE, ""),
        ): str,
    }
    if mode == MODE_STATIC:
        data.update(
            {
                vol.Required(
                    CONF_LATITUDE,
                    default=defaults.get(CONF_LATITUDE, hass.config.latitude),
                ): vol.All(vol.Coerce(float), vol.Range(min=-90, max=90)),
                vol.Required(
                    CONF_LONGITUDE,
                    default=defaults.get(CONF_LONGITUDE, hass.config.longitude),
                ): vol.All(vol.Coerce(float), vol.Range(min=-180, max=180)),
            }
        )
    else:
        data.update(
            {
                vol.Required(
                    CONF_ENTITY_ID,
                    default=defaults.get(CONF_ENTITY_ID, ""),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["device_tracker", "person"])
                ),
                vol.Required(
                    CONF_MIN_TRACK_INTERVAL,
                    default=defaults.get(
                        CONF_MIN_TRACK_INTERVAL, DEFAULT_MIN_TRACK_INTERVAL
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=1)),
            }
        )
    return vol.Schema(data)


class OpenMeteoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the integration."""

    VERSION = 2

    def __init__(self) -> None:
        self._mode = MODE_STATIC

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        defaults = user_input or {}
        mode = defaults.get(CONF_MODE, self._mode)
        if user_input is not None:
            if mode == MODE_STATIC:
                if CONF_LATITUDE not in user_input or CONF_LONGITUDE not in user_input:
                    errors["base"] = "missing_location"
            elif mode == MODE_TRACK:
                entity = user_input.get(CONF_ENTITY_ID)
                if not entity:
                    errors["base"] = "missing_entity"
                else:
                    state = self.hass.states.get(entity)
                    if not state or "latitude" not in state.attributes or "longitude" not in state.attributes:
                        errors["base"] = "invalid_entity"
            if not errors:
                return self.async_create_entry(title="Open-Meteo", data=user_input)
        self._mode = mode
        schema = _build_schema(self.hass, mode, defaults)
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

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
        self._mode = entry.options.get(CONF_MODE, entry.data.get(CONF_MODE, MODE_STATIC))

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ):
        errors: dict[str, str] = {}
        data = {**self._entry.data, **self._entry.options}
        defaults = user_input or data
        mode = defaults.get(CONF_MODE, self._mode)
        if user_input is not None:
            if mode == MODE_STATIC and (
                CONF_LATITUDE not in user_input or CONF_LONGITUDE not in user_input
            ):
                errors["base"] = "missing_location"
            elif mode == MODE_TRACK:
                entity = user_input.get(CONF_ENTITY_ID)
                if not entity:
                    errors["base"] = "missing_entity"
                else:
                    state = self.hass.states.get(entity)
                    if not state or "latitude" not in state.attributes or "longitude" not in state.attributes:
                        errors["base"] = "invalid_entity"
            if not errors:
                return self.async_create_entry(title="", data=user_input)
        self._mode = mode
        schema = _build_schema(self.hass, mode, defaults)
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)

