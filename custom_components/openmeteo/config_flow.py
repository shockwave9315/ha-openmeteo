"""Config flow for Open-Meteo integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv

from .const import (
    CONF_DAILY_VARIABLES,
    CONF_HOURLY_VARIABLES,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    CONF_TIME_ZONE,
    DEFAULT_DAILY_VARIABLES,
    DEFAULT_HOURLY_VARIABLES,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

class OpenMeteoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Open-Meteo."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OpenMeteoOptionsFlow:
        """Get the options flow for this handler."""
        return OpenMeteoOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            return self.async_create_entry(
                title=user_input.get(CONF_NAME, DEFAULT_NAME),
                data=user_input,
            )

        # ===== TUTAJ JEST ZMIANA: AUTOMATYCZNE UZUPEŁNIANIE LOKALIZACJI =====
        data_schema = {
            vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
            vol.Required(
                CONF_LATITUDE, default=self.hass.config.latitude
            ): cv.latitude,
            vol.Required(
                CONF_LONGITUDE, default=self.hass.config.longitude
            ): cv.longitude,
            vol.Optional(CONF_TIME_ZONE, default="auto"): str,
            vol.Optional(
                CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
            ): cv.positive_int,
        }

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(data_schema),
            errors=errors,
        )


class OpenMeteoOptionsFlow(config_entries.OptionsFlowWithConfigEntry):
    """Handle options flow for Open-Meteo."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Użycie wartości z opcji lub danych konfiguracyjnych jako domyślnych
        current_daily = self.options.get(CONF_DAILY_VARIABLES, DEFAULT_DAILY_VARIABLES)
        current_hourly = self.options.get(CONF_HOURLY_VARIABLES, DEFAULT_HOURLY_VARIABLES)
        scan_interval = self.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        
        # Schemat formularza opcji
        options_schema = {
            vol.Optional(
                CONF_SCAN_INTERVAL,
                default=scan_interval
            ): cv.positive_int,
            vol.Optional(
                CONF_DAILY_VARIABLES, 
                default=current_daily
            ): cv.multi_select(
                # Tutaj można dodać słownik tłumaczeń, jeśli chcesz mieć ładne etykiety
                # Na razie zostawiamy tak, jak było, dla prostoty
                {var: var.replace("_", " ").title() for var in DEFAULT_DAILY_VARIABLES}
            ),
            vol.Optional(
                CONF_HOURLY_VARIABLES, 
                default=current_hourly
            ): cv.multi_select(
                {var: var.replace("_", " ").title() for var in DEFAULT_HOURLY_VARIABLES}
            ),
        }

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(options_schema),
        )