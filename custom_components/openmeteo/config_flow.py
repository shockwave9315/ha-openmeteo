"""Config flow for Open-Meteo integration."""
from __future__ import annotations

from typing import Any
from zoneinfo import available_timezones

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
    CONF_SCAN_INTERVAL,
    CONF_TIME_ZONE,
    CONF_TRACKED_ENTITY_ID,
    CONF_TRACKING_MODE,
    DEFAULT_DAILY_VARIABLES,
    DEFAULT_HOURLY_VARIABLES,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    TRACKING_MODE_DEVICE,
    TRACKING_MODE_FIXED,
)

# --- Schemas -----------------------------------------------------------------

def _mode_schema() -> vol.Schema:
    """First step: choose tracking mode only."""
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
            )
        }
    )


def _manual_schema(hass: HomeAssistant) -> vol.Schema:
    """Second step (manual): latitude/longitude only."""
    ha_lat = hass.config.latitude
    ha_lon = hass.config.longitude
    return vol.Schema(
        {
            vol.Required(CONF_LATITUDE, default=ha_lat): vol.All(
                vol.Coerce(float), vol.Range(min=-90, max=90)
            ),
            vol.Required(CONF_LONGITUDE, default=ha_lon): vol.All(
                vol.Coerce(float), vol.Range(min=-180, max=180)
            ),
        }
    )


def get_tracked_entities_options(
    hass: HomeAssistant, current_entity: str | None = None
) -> list[selector.SelectOptionDict]:
    """Dynamically get a list of trackable entities with their friendly names."""
    er_reg = er.async_get(hass)
    options: list[selector.SelectOptionDict] = []
    for ent in er_reg.entities.values():
        if ent.domain in ("device_tracker", "person"):
            label = ent.original_name or ent.name or ent.entity_id
            options.append(selector.SelectOptionDict(value=ent.entity_id, label=label))
    options.sort(key=lambda o: o["label"].casefold())
    if current_entity and all(o["value"] != current_entity for o in options):
        options.insert(0, selector.SelectOptionDict(value=current_entity, label=current_entity))
    return options


def _tz_options_with_auto() -> list[str]:
    """Return timezone options with 'auto' prepended.

    NOTE: This touches tzdata on disk; call it from executor to avoid blocking.
    """
    tzs = sorted(available_timezones())
    return ["auto"] + tzs


# --- Config Flow --------------------------------------------------------------

class OpenMeteoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Open-Meteo."""

    VERSION = 1

    def __init__(self) -> None:
        self._init_data: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Step 1: choose tracking mode."""
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=_mode_schema(), errors={})

        # Store selected mode and branch to the dedicated step.
        self._init_data = {CONF_TRACKING_MODE: user_input[CONF_TRACKING_MODE]}
        if user_input[CONF_TRACKING_MODE] == TRACKING_MODE_DEVICE:
            return await self.async_step_device()
        return await self.async_step_manual()

    async def async_step_manual(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Step 2A (Fixed Location): capture lat/lon only."""
        if user_input is None:
            return self.async_show_form(step_id="manual", data_schema=_manual_schema(self.hass), errors={})

        data = {
            **self._init_data,  # contains CONF_TRACKING_MODE = TRACKING_MODE_FIXED
            CONF_LATITUDE: float(user_input[CONF_LATITUDE]),
            CONF_LONGITUDE: float(user_input[CONF_LONGITUDE]),
        }
        # Ensure we don't carry tracker_id by accident
        data.pop(CONF_TRACKED_ENTITY_ID, None)
        return self.async_create_entry(title="Open-Meteo", data=data)

    async def async_step_device(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Step 2B (Tracked Device): choose tracker entity only."""
        errors: dict[str, str] = {}
        if user_input is not None:
            tracked_entity_id = user_input.get(CONF_TRACKED_ENTITY_ID)
            entity_registry = er.async_get(self.hass)
            if not tracked_entity_id or not entity_registry.async_get(tracked_entity_id):
                errors["base"] = "invalid_entity"
            else:
                # Do not keep lat/lon when tracking a device
                data = {k: v for k, v in self._init_data.items() if k not in (CONF_LATITUDE, CONF_LONGITUDE)}
                data.update({CONF_TRACKED_ENTITY_ID: tracked_entity_id})
                return self.async_create_entry(title="Open-Meteo", data=data)

        default_entity = self._init_data.get(CONF_TRACKED_ENTITY_ID)
        return self.async_show_form(
            step_id="device",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_TRACKED_ENTITY_ID, default=default_entity): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=get_tracked_entities_options(self.hass),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> "OpenMeteoOptionsFlow":
        return OpenMeteoOptionsFlow(config_entry)


# --- Options Flow -------------------------------------------------------------

class OpenMeteoOptionsFlow(config_entries.OptionsFlow):
    """Handle Open-Meteo options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        # NIE nadpisuj self.config_entry (deprecated). Trzymaj własne pole.
        self._entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self._entry.options
        data = self._entry.data

        tracking_mode = options.get(CONF_TRACKING_MODE, data.get(CONF_TRACKING_MODE, TRACKING_MODE_FIXED))
        tracked_entity_id = options.get(CONF_TRACKED_ENTITY_ID, data.get(CONF_TRACKED_ENTITY_ID))

        # Pobierz listę stref czasu w executorze — unikamy blokowania event loopa.
        tz_options = await self.hass.async_add_executor_job(_tz_options_with_auto)

        options_schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL, default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                ): int,
                vol.Required(
                    CONF_TIME_ZONE, default=options.get(CONF_TIME_ZONE, "auto")
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=tz_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Required(
                    CONF_HOURLY_VARIABLES, default=options.get(CONF_HOURLY_VARIABLES, DEFAULT_HOURLY_VARIABLES)
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[{"value": var, "label": var} for var in DEFAULT_HOURLY_VARIABLES],
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,  # kompatybilnie z HA
                    )
                ),
                vol.Required(
                    CONF_DAILY_VARIABLES, default=options.get(CONF_DAILY_VARIABLES, DEFAULT_DAILY_VARIABLES)
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[{"value": var, "label": var} for var in DEFAULT_DAILY_VARIABLES],
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,  # kompatybilnie z HA
                    )
                ),
                vol.Required(CONF_TRACKING_MODE, default=tracking_mode): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=TRACKING_MODE_FIXED, label="Fixed Location"),
                            selector.SelectOptionDict(value=TRACKING_MODE_DEVICE, label="Tracked Device"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        if tracking_mode == TRACKING_MODE_FIXED:
            options_schema = options_schema.extend(
                {
                    vol.Required(
                        CONF_LATITUDE,
                        default=options.get(CONF_LATITUDE, data.get(CONF_LATITUDE, self.hass.config.latitude)),
                    ): vol.All(vol.Coerce(float), vol.Range(min=-90, max=90)),
                    vol.Required(
                        CONF_LONGITUDE,
                        default=options.get(CONF_LONGITUDE, data.get(CONF_LONGITUDE, self.hass.config.longitude)),
                    ): vol.All(vol.Coerce(float), vol.Range(min=-180, max=180)),
                }
            )
        elif tracking_mode == TRACKING_MODE_DEVICE:
            device_options = get_tracked_entities_options(self.hass, tracked_entity_id)
            options_schema = options_schema.extend(
                {
                    vol.Required(CONF_TRACKED_ENTITY_ID, default=tracked_entity_id): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=device_options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            )

        return self.async_show_form(step_id="init", data_schema=options_schema, errors={})
