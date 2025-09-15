"""Config and options flows for the Open-Meteo integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import (
    CONF_API_PROVIDER,
    CONF_AREA_NAME_OVERRIDE,
    CONF_ENTITY_ID,
    CONF_MIN_TRACK_INTERVAL,
    CONF_MODE,
    CONF_UNITS,
    CONF_UPDATE_INTERVAL,
    CONF_USE_PLACE_AS_DEVICE_NAME,
    DEFAULT_API_PROVIDER,
    DEFAULT_MIN_TRACK_INTERVAL,
    DEFAULT_UNITS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MODE_STATIC,
    MODE_TRACK,
)
from .coordinator import async_reverse_geocode


def _build_schema(
    hass: HomeAssistant,
    mode: str,
    defaults: dict[str, Any],
    *,
    include_use_place: bool = True,
) -> vol.Schema:
    """Build a schema for the config and options flow."""

    if mode == MODE_TRACK:
        data: dict[Any, Any] = {
            vol.Required(
                CONF_ENTITY_ID, default=defaults.get(CONF_ENTITY_ID, "")
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

    extra = {
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
    if include_use_place:
        extra[vol.Required(
            CONF_USE_PLACE_AS_DEVICE_NAME,
            default=defaults.get(CONF_USE_PLACE_AS_DEVICE_NAME, True),
        )] = bool

    data.update(extra)
    return vol.Schema(data)


async def _async_guess_title(
    hass: HomeAssistant, mode: str, data: dict[str, Any]
) -> str:
    """Derive a friendly title for the entry based on provided data."""

    override = (data.get(CONF_AREA_NAME_OVERRIDE) or "").strip()
    if override:
        return override

    try:
        if mode == MODE_TRACK:
            entity_id = data.get(CONF_ENTITY_ID)
            if entity_id:
                state = hass.states.get(entity_id)
                if state:
                    lat = state.attributes.get("latitude")
                    lon = state.attributes.get("longitude")
                    try:
                        lat_f = float(lat) if lat is not None else None
                        lon_f = float(lon) if lon is not None else None
                    except (TypeError, ValueError):
                        lat_f = lon_f = None

                    if lat_f is not None and lon_f is not None:
                        place = await async_reverse_geocode(hass, lat_f, lon_f)
                        if place:
                            return place
                        return f"Open-Meteo: {lat_f:.4f},{lon_f:.4f}"

                    friendly = (
                        state.attributes.get("friendly_name")
                        or state.name
                        or entity_id
                    )
                    return f"Open-Meteo: {friendly}"
            return "Open-Meteo: Śledzenie"

        lat = data.get(CONF_LATITUDE)
        lon = data.get(CONF_LONGITUDE)
        if lat is None or lon is None:
            return "Open-Meteo"

        lat_f = float(lat)
        lon_f = float(lon)
        place = await async_reverse_geocode(hass, lat_f, lon_f)
        if place:
            return place
        return f"Open-Meteo: {lat_f:.4f},{lon_f:.4f}"
    except Exception:  # pragma: no cover - defensive
        return "Open-Meteo"


class OpenMeteoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the configuration flow for Open-Meteo."""

    VERSION = 2

    def __init__(self) -> None:
        self._mode = MODE_STATIC

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Initial step asking for operating mode."""

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
        """Collect details specific to the chosen mode."""

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
                if user_input.get(CONF_LATITUDE) in (None, ""):
                    errors[CONF_LATITUDE] = "required"
                if user_input.get(CONF_LONGITUDE) in (None, ""):
                    errors[CONF_LONGITUDE] = "required"

            if not errors:
                data = {**user_input, CONF_MODE: self._mode}
                title = await _async_guess_title(self.hass, self._mode, data)
                return self.async_create_entry(title=title, data=data)

        schema = _build_schema(
            self.hass,
            self._mode,
            defaults,
            include_use_place=self._mode == MODE_TRACK,
        )
        return self.async_show_form(
            step_id="mode_details", data_schema=schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return OpenMeteoOptionsFlow(config_entry)


class OpenMeteoOptionsFlow(config_entries.OptionsFlow):
    """Handle the options flow after the integration is set up."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry
        merged = {**entry.data, **entry.options}
        self._mode = merged.get(CONF_MODE, MODE_STATIC)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """First step of the options flow: choose mode."""

        if user_input is not None:
            self._mode = user_input[CONF_MODE]
            return await self.async_step_mode_details()

        schema = vol.Schema(
            {vol.Required(CONF_MODE, default=self._mode): vol.In([MODE_STATIC, MODE_TRACK])}
        )
        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_mode_details(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Collect mode-specific options."""

        merged_defaults = {**self._entry.data, **self._entry.options}
        defaults = dict(merged_defaults)
        errors: dict[str, str] = {}

        if user_input is not None:
            defaults.update(user_input)

            if self._mode == MODE_TRACK:
                if not user_input.get(CONF_ENTITY_ID):
                    errors[CONF_ENTITY_ID] = "required"
            else:
                if user_input.get(CONF_LATITUDE) in (None, ""):
                    errors[CONF_LATITUDE] = "required"
                if user_input.get(CONF_LONGITUDE) in (None, ""):
                    errors[CONF_LONGITUDE] = "required"

            if not errors:
                new_options: dict[str, Any] = dict(self._entry.options)

                if self._mode == MODE_TRACK:
                    new_options.pop(CONF_LATITUDE, None)
                    new_options.pop(CONF_LONGITUDE, None)
                else:
                    new_options.pop(CONF_ENTITY_ID, None)
                    new_options.pop(CONF_MIN_TRACK_INTERVAL, None)

                new_options.update(user_input)
                new_options[CONF_MODE] = self._mode

                return self.async_create_entry(title="", data=new_options)

        schema = _build_schema(
            self.hass,
            self._mode,
            defaults,
            include_use_place=self._mode == MODE_TRACK,
        )
        return self.async_show_form(
            step_id="mode_details", data_schema=schema, errors=errors
        )
