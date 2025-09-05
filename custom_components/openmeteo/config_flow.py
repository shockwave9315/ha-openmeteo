from __future__ import annotations

from typing import Any, Dict

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector as sel

from .const import (
    DOMAIN,
    # tryb
    CONF_MODE,
    MODE_STATIC,
    MODE_TRACK,
    # pola
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_ENTITY_ID,
    CONF_MIN_TRACK_INTERVAL,
    CONF_UPDATE_INTERVAL,
    CONF_UNITS,
    CONF_USE_PLACE_AS_DEVICE_NAME,
    CONF_SHOW_PLACE_NAME,
    # domyślne
    DEFAULT_MIN_TRACK_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_UNITS,
    DEFAULT_USE_PLACE_AS_DEVICE_NAME,
    DEFAULT_SHOW_PLACE_NAME,
)

def _entity_selector_or_str():
    """Selector encji z bezpiecznym fallbackiem na str."""
    try:
        return sel.EntitySelector(
            sel.EntitySelectorConfig(domain=["device_tracker", "person"], multiple=False)
        )
    except Exception:
        return str


def _schema_common(defaults: Dict[str, Any]) -> vol.Schema:
    """Wspólne pola dla obu trybów."""
    return vol.Schema(
        {
            vol.Optional(
                CONF_UPDATE_INTERVAL,
                default=defaults.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
            ): int,
            vol.Optional(
                CONF_UNITS,
                default=defaults.get(CONF_UNITS, DEFAULT_UNITS),
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


def _schema_static(hass: HomeAssistant, defaults: Dict[str, Any]) -> vol.Schema:
    """Pola dla trybu STATIC."""
    base = vol.Schema(
        {
            vol.Required(
                CONF_LATITUDE, default=defaults.get(CONF_LATITUDE, hass.config.latitude)
            ): float,
            vol.Required(
                CONF_LONGITUDE, default=defaults.get(CONF_LONGITUDE, hass.config.longitude)
            ): float,
        }
    )
    return base.extend(_schema_common(defaults).schema)


def _schema_track(defaults: Dict[str, Any]) -> vol.Schema:
    """Pola dla trybu TRACK."""
    # Entity selector nie akceptuje pustych domyślnych wartości,
    # więc podajemy domyślny `CONF_ENTITY_ID` tylko gdy istnieje.
    entity_id = defaults.get(CONF_ENTITY_ID)
    if entity_id:
        base = vol.Schema(
            {
                vol.Required(CONF_ENTITY_ID, default=entity_id): _entity_selector_or_str(),
                vol.Optional(
                    CONF_MIN_TRACK_INTERVAL,
                    default=defaults.get(
                        CONF_MIN_TRACK_INTERVAL, DEFAULT_MIN_TRACK_INTERVAL
                    ),
                ): int,
            }
        )
    else:
        base = vol.Schema(
            {
                vol.Required(CONF_ENTITY_ID): _entity_selector_or_str(),
                vol.Optional(
                    CONF_MIN_TRACK_INTERVAL,
                    default=defaults.get(
                        CONF_MIN_TRACK_INTERVAL, DEFAULT_MIN_TRACK_INTERVAL
                    ),
                ): int,
            }
        )
    return base.extend(_schema_common(defaults).schema)


def _build_schema(hass: HomeAssistant, mode: str, defaults: Dict[str, Any]) -> vol.Schema:
    if mode == MODE_STATIC:
        return _schema_static(hass, defaults)
    if mode == MODE_TRACK:
        return _schema_track(defaults)
    # Defensive: nie wspieramy innych trybów
    return _schema_static(hass, defaults)


class OpenMeteoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow (tylko STATIC/TRACK)."""

    VERSION = 1

    def __init__(self) -> None:
        self._mode: str | None = None

    async def async_step_user(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Krok 1: wybór trybu."""
        if user_input is not None:
            self._mode = user_input[CONF_MODE]
            return await self.async_step_mode_details()

        schema = vol.Schema(
            {
                vol.Required(CONF_MODE, default=MODE_STATIC): vol.In([MODE_STATIC, MODE_TRACK]),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_mode_details(self, user_input: Dict[str, Any] | None = None) -> FlowResult:
        """Krok 2: szczegóły trybu."""
        mode = self._mode or MODE_STATIC
        defaults: Dict[str, Any] = {
            CONF_MODE: mode,
            CONF_LATITUDE: self.hass.config.latitude,
            CONF_LONGITUDE: self.hass.config.longitude,
            CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
            CONF_UNITS: DEFAULT_UNITS,
            CONF_USE_PLACE_AS_DEVICE_NAME: DEFAULT_USE_PLACE_AS_DEVICE_NAME,
            CONF_SHOW_PLACE_NAME: DEFAULT_SHOW_PLACE_NAME,
        }
        
        if user_input is not None:
            # Walidacja podstawowa
            if mode == MODE_STATIC:
                if user_input.get(CONF_LATITUDE) is None or user_input.get(CONF_LONGITUDE) is None:
                    return self.async_show_form(
                        step_id="mode_details", 
                        data_schema=_build_schema(self.hass, mode, {**defaults, **user_input}), 
                        errors={"base": "latlon_required"}
                    )
            elif mode == MODE_TRACK:
                if not user_input.get(CONF_ENTITY_ID):
                    return self.async_show_form(
                        step_id="mode_details", 
                        data_schema=_build_schema(self.hass, mode, {**defaults, **user_input}), 
                        errors={"base": "entity_required"}
                    )
            
            # Create entry with all options in data (will be moved to options in async_setup_entry)
            data = {**user_input, CONF_MODE: mode}
            return self.async_create_entry(
                title=f"OpenMeteo ({mode.capitalize()})", 
                data=data, 
                options=data  # Initialize options with user input
            )

        return self.async_show_form(step_id="mode_details", data_schema=_build_schema(self.hass, mode, defaults))


class OpenMeteoOptionsFlowHandler(config_entries.OptionsFlow):
    """Options flow allowing full edit after install."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry
        self._mode: str | None = None

    def _get(self, key: str, default: Any | None = None) -> Any:
        """Get a value from options or data with fallback."""
        return self.config_entry.options.get(
            key, self.config_entry.data.get(key, default)
        )

    async def async_step_init(
        self, user_input: Dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: choose mode."""
        if user_input is not None:
            self._mode = user_input[CONF_MODE]
            return await self.async_step_mode_details()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_MODE, default=self._get(CONF_MODE, MODE_STATIC)
                ): vol.In([MODE_STATIC, MODE_TRACK])
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)

    async def async_step_mode_details(
        self, user_input: Dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2: edit fields for selected mode."""
        mode = self._mode or self._get(CONF_MODE, MODE_STATIC)
        defaults: Dict[str, Any] = {
            CONF_LATITUDE: self._get(CONF_LATITUDE, self.hass.config.latitude),
            CONF_LONGITUDE: self._get(CONF_LONGITUDE, self.hass.config.longitude),
            CONF_ENTITY_ID: self._get(CONF_ENTITY_ID),
            CONF_MIN_TRACK_INTERVAL: self._get(
                CONF_MIN_TRACK_INTERVAL, DEFAULT_MIN_TRACK_INTERVAL
            ),
            CONF_UPDATE_INTERVAL: self._get(
                CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
            ),
            CONF_UNITS: self._get(CONF_UNITS, DEFAULT_UNITS),
            CONF_USE_PLACE_AS_DEVICE_NAME: self._get(
                CONF_USE_PLACE_AS_DEVICE_NAME, DEFAULT_USE_PLACE_AS_DEVICE_NAME
            ),
            CONF_SHOW_PLACE_NAME: self._get(
                CONF_SHOW_PLACE_NAME, DEFAULT_SHOW_PLACE_NAME
            ),
        }

        if user_input is not None:
            if mode == MODE_STATIC:
                if (
                    user_input.get(CONF_LATITUDE) is None
                    or user_input.get(CONF_LONGITUDE) is None
                ):
                    return self.async_show_form(
                        step_id="mode_details",
                        data_schema=_build_schema(
                            self.hass, mode, {**defaults, **user_input}
                        ),
                        errors={"base": "latlon_required"},
                    )
            elif mode == MODE_TRACK:
                if not user_input.get(CONF_ENTITY_ID):
                    return self.async_show_form(
                        step_id="mode_details",
                        data_schema=_build_schema(
                            self.hass, mode, {**defaults, **user_input}
                        ),
                        errors={"base": "entity_required"},
                    )
            new_options = {
                **self.config_entry.options,
                **user_input,
                CONF_MODE: mode,
            }
            return self.async_create_entry(title="", data=new_options)

        return self.async_show_form(
            step_id="mode_details",
            data_schema=_build_schema(self.hass, mode, defaults),
        )
