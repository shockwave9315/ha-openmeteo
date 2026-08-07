"""Config and options flows for Open-Meteo v2."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_LATITUDE, CONF_LOCATION, CONF_LONGITUDE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import (
    AQ_SENSOR_KEYS,
    CONF_AREA_NAME_OVERRIDE,
    CONF_ENABLED_AQ_SENSORS,
    CONF_ENABLED_SENSORS,
    CONF_ENABLED_WEATHER_SENSORS,
    CONF_ENTITY_ID,
    CONF_MIN_TRACK_INTERVAL,
    CONF_MODE,
    CONF_REVERSE_GEOCODE_COOLDOWN_MIN,
    CONF_UPDATE_INTERVAL,
    CONF_UPDATE_INTERVAL_MIN,
    DEFAULT_MIN_TRACK_INTERVAL,
    DEFAULT_REVERSE_GEOCODE_COOLDOWN_MIN,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MODE_STATIC,
    MODE_TRACK,
    SENSOR_LABELS,
    WEATHER_SENSOR_KEYS,
)
from .identity import CONF_SOURCE_KEY, derive_source_key
from .location import async_reverse_geocode, coordinate_label


def _update_interval_minutes(defaults: dict[str, Any]) -> int:
    raw = defaults.get(CONF_UPDATE_INTERVAL_MIN)
    if raw is not None:
        try:
            return max(1, int(raw))
        except (TypeError, ValueError):
            pass
    try:
        return max(1, int(defaults.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)) // 60)
    except (TypeError, ValueError):
        return max(1, DEFAULT_UPDATE_INTERVAL // 60)


def _label_options(hass: HomeAssistant, keys: list[str]) -> list[dict[str, str]]:
    language = (hass.config.language or "en").split("-", 1)[0].lower()
    return [
        {
            "value": key,
            "label": (SENSOR_LABELS.get(key) or {}).get(language)
            or (SENSOR_LABELS.get(key) or {}).get("en")
            or key,
        }
        for key in keys
    ]


def _mode_selector(hass: HomeAssistant) -> selector.SelectSelector:
    language = (hass.config.language or "en").split("-", 1)[0].lower()
    if language == "pl":
        labels = {MODE_STATIC: "Stała lokalizacja", MODE_TRACK: "Śledź encję"}
    else:
        labels = {MODE_STATIC: "Static location", MODE_TRACK: "Track an entity"}
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[{"value": value, "label": label} for value, label in labels.items()],
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _selected_defaults(
    defaults: dict[str, Any], key: str, allowed: list[str]
) -> list[str]:
    value = defaults.get(key)
    if isinstance(value, list):
        return [item for item in value if item in allowed]
    legacy = defaults.get(CONF_ENABLED_SENSORS)
    if isinstance(legacy, list):
        selected = [item for item in legacy if item in allowed]
        if selected:
            return selected
    return list(allowed)


def _details_schema(
    hass: HomeAssistant,
    mode: str,
    defaults: dict[str, Any],
) -> vol.Schema:
    fields: dict[Any, Any] = {}

    if mode == MODE_TRACK:
        fields[
            vol.Required(CONF_ENTITY_ID, default=defaults.get(CONF_ENTITY_ID, ""))
        ] = selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["device_tracker", "person"])
        )
        fields[
            vol.Required(
                CONF_MIN_TRACK_INTERVAL,
                default=defaults.get(CONF_MIN_TRACK_INTERVAL, DEFAULT_MIN_TRACK_INTERVAL),
            )
        ] = vol.All(vol.Coerce(int), vol.Range(min=1, max=240))
    else:
        location_default = {
            CONF_LATITUDE: defaults.get(CONF_LATITUDE, hass.config.latitude),
            CONF_LONGITUDE: defaults.get(CONF_LONGITUDE, hass.config.longitude),
        }
        fields[
            vol.Required(CONF_LOCATION, default=location_default)
        ] = selector.LocationSelector(selector.LocationSelectorConfig(radius=False))

    fields[
        vol.Optional(
            CONF_AREA_NAME_OVERRIDE,
            default=defaults.get(CONF_AREA_NAME_OVERRIDE, ""),
        )
    ] = str
    fields[
        vol.Required(
            CONF_UPDATE_INTERVAL_MIN,
            default=_update_interval_minutes(defaults),
        )
    ] = vol.All(vol.Coerce(int), vol.Range(min=1, max=240))
    fields[
        vol.Required(
            CONF_REVERSE_GEOCODE_COOLDOWN_MIN,
            default=defaults.get(
                CONF_REVERSE_GEOCODE_COOLDOWN_MIN,
                DEFAULT_REVERSE_GEOCODE_COOLDOWN_MIN,
            ),
        )
    ] = vol.All(vol.Coerce(int), vol.Range(min=1, max=240))
    fields[
        vol.Optional(
            CONF_ENABLED_WEATHER_SENSORS,
            default=_selected_defaults(
                defaults, CONF_ENABLED_WEATHER_SENSORS, WEATHER_SENSOR_KEYS
            ),
        )
    ] = selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=_label_options(hass, WEATHER_SENSOR_KEYS),
            multiple=True,
            mode=selector.SelectSelectorMode.LIST,
        )
    )
    fields[
        vol.Optional(
            CONF_ENABLED_AQ_SENSORS,
            default=_selected_defaults(defaults, CONF_ENABLED_AQ_SENSORS, AQ_SENSOR_KEYS),
        )
    ] = selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=_label_options(hass, AQ_SENSOR_KEYS),
            multiple=True,
            mode=selector.SelectSelectorMode.LIST,
        )
    )
    return vol.Schema(fields)


def _flatten_static_location(values: dict[str, Any]) -> None:
    location = values.pop(CONF_LOCATION, None)
    if not isinstance(location, dict):
        return
    if CONF_LATITUDE in location:
        values[CONF_LATITUDE] = float(location[CONF_LATITUDE])
    if CONF_LONGITUDE in location:
        values[CONF_LONGITUDE] = float(location[CONF_LONGITUDE])


async def _initial_title(hass: HomeAssistant, mode: str, data: dict[str, Any]) -> str:
    override = str(data.get(CONF_AREA_NAME_OVERRIDE) or "").strip()
    if override:
        return override

    if mode == MODE_TRACK:
        entity_id = data.get(CONF_ENTITY_ID)
        state = hass.states.get(entity_id) if entity_id else None
        if state is not None:
            friendly = state.attributes.get("friendly_name") or state.name
            if friendly:
                return f"Open-Meteo: {friendly}"
        if entity_id:
            return f"Open-Meteo: {str(entity_id).split('.', 1)[-1]}"
        return "Open-Meteo: tracking"

    try:
        latitude = float(data[CONF_LATITUDE])
        longitude = float(data[CONF_LONGITUDE])
    except (KeyError, TypeError, ValueError):
        return "Open-Meteo"
    place = await async_reverse_geocode(hass, latitude, longitude)
    return place or coordinate_label(latitude, longitude)


class OpenMeteoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Set up one static or tracking Open-Meteo source."""

    VERSION = 4

    def __init__(self) -> None:
        self._mode = MODE_STATIC

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            self._mode = user_input[CONF_MODE]
            return await self.async_step_details()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_MODE, default=self._mode): _mode_selector(self.hass)}
            ),
        )

    async def async_step_details(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        defaults = dict(user_input or {})

        if user_input is not None:
            data = dict(user_input)
            if self._mode == MODE_STATIC:
                _flatten_static_location(data)
            else:
                entity_id = data.get(CONF_ENTITY_ID)
                state = self.hass.states.get(entity_id) if entity_id else None
                if not entity_id:
                    errors[CONF_ENTITY_ID] = "required"
                elif state is not None and (
                    state.attributes.get("latitude") is None
                    or state.attributes.get("longitude") is None
                ):
                    errors[CONF_ENTITY_ID] = "invalid_entity"

            if not errors:
                data[CONF_MODE] = self._mode
                title = await _initial_title(self.hass, self._mode, data)
                data[CONF_SOURCE_KEY] = derive_source_key(
                    entry_id="new",
                    title=title,
                    data=data,
                )
                return self.async_create_entry(title=title, data=data)

        return self.async_show_form(
            step_id="details",
            data_schema=_details_schema(self.hass, self._mode, defaults),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return OpenMeteoOptionsFlow(config_entry)


class OpenMeteoOptionsFlow(config_entries.OptionsFlow):
    """Edit runtime behavior without changing the stable source key."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry
        merged = {**dict(entry.data or {}), **dict(entry.options or {})}
        self._mode = merged.get(CONF_MODE, MODE_STATIC)

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            self._mode = user_input[CONF_MODE]
            return await self.async_step_details()

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {vol.Required(CONF_MODE, default=self._mode): _mode_selector(self.hass)}
            ),
        )

    async def async_step_details(self, user_input: dict[str, Any] | None = None):
        merged = {**dict(self._entry.data or {}), **dict(self._entry.options or {})}
        defaults = dict(merged)
        errors: dict[str, str] = {}

        if user_input is not None:
            values = dict(user_input)
            if self._mode == MODE_STATIC:
                _flatten_static_location(values)
            elif not values.get(CONF_ENTITY_ID):
                errors[CONF_ENTITY_ID] = "required"

            if not errors:
                new_options = dict(self._entry.options or {})
                new_options.pop(CONF_ENABLED_SENSORS, None)
                if self._mode == MODE_TRACK:
                    new_options.pop(CONF_LATITUDE, None)
                    new_options.pop(CONF_LONGITUDE, None)
                else:
                    new_options.pop(CONF_ENTITY_ID, None)
                    new_options.pop(CONF_MIN_TRACK_INTERVAL, None)
                new_options.update(values)
                new_options[CONF_MODE] = self._mode
                return self.async_create_entry(title="", data=new_options)
            defaults.update(values)

        return self.async_show_form(
            step_id="details",
            data_schema=_details_schema(self.hass, self._mode, defaults),
            errors=errors,
        )
