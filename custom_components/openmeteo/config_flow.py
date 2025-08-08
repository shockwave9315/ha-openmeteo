"""Config flow for Open-Meteo integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
import homeassistant.helpers.config_validation as cv
from homeassistant.components.device_tracker import DOMAIN as DEVICE_TRACKER_DOMAIN
from homeassistant.helpers import device_registry as dr

from .const import (
    
    CONF_DAILY_VARIABLES,
    CONF_DEVICE_TRACKERS,
    CONF_HOURLY_VARIABLES,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    CONF_TIME_ZONE,
    CONF_TRACK_DEVICES,
    CONF_USE_DEVICE_NAMES,
    CONF_AREA_OVERRIDES,
    DEFAULT_DAILY_VARIABLES,
    DEFAULT_DEVICE_TRACKERS,
    DEFAULT_HOURLY_VARIABLES,
    TRANSLATED_VARIABLES,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TRACK_DEVICES,
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

        # Pusta lista śledzonych urządzeń - będzie uzupełniona w opcjach po instalacji
        trackable_devices = {}
        
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
            vol.Optional(
                CONF_TRACK_DEVICES, 
                default=DEFAULT_TRACK_DEVICES
            ): bool,
        }
        
        # Dodaj wybór urządzeń tylko jeśli opcja śledzenia jest włączona
        if trackable_devices:
            data_schema.update({
                vol.Optional(
                    CONF_DEVICE_TRACKERS,
                    default=list(DEFAULT_DEVICE_TRACKERS)
                ): cv.multi_select(trackable_devices),
            })

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(data_schema),
            errors=errors,
        )


class OpenMeteoOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Open-Meteo."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            # Przetwórz dane wejściowe, aby wyodrębnić area_overrides
            area_overrides = {}
            keys_to_remove = []
            
            # Najpierw zbierz klucze do usunięcia i zbuduj słownik area_overrides
            for key, value in user_input.items():
                if key.startswith(f"{CONF_AREA_OVERRIDES}_"):
                    device_id = key.replace(f"{CONF_AREA_OVERRIDES}_", "")
                    if value and value.strip():
                        area_overrides[device_id] = value.strip()
                    keys_to_remove.append(key)
            
            # Następnie usuń zebrane klucze ze słownika wejściowego
            for key in keys_to_remove:
                user_input.pop(key, None)
            
            # Dodaj area_overrides do danych konfiguracyjnych
            if area_overrides:
                user_input[CONF_AREA_OVERRIDES] = area_overrides
            
            return self.async_create_entry(title="", data=user_input)

        # Użycie wartości z opcji lub danych konfiguracyjnych jako domyślnych
        current_daily = self.options.get(CONF_DAILY_VARIABLES, DEFAULT_DAILY_VARIABLES)
        current_hourly = self.options.get(CONF_HOURLY_VARIABLES, DEFAULT_HOURLY_VARIABLES)
        scan_interval = self.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        
        # Pobierz dostępne urządzenia do śledzenia
        device_registry = dr.async_get(self.hass)
        trackable_devices = {}
        
        # Sprawdź czy mamy już entry_id (czy to nie jest pierwsze uruchomienie)
        if hasattr(self, 'config_entry') and self.config_entry:
            device_entries = dr.async_entries_for_config_entry(
                device_registry, self.config_entry.entry_id
            )
            
            # Filtruj tylko urządzenia z komponentu device_tracker
            trackable_devices = {
                entry.id: entry.name_by_user or entry.name or f"Device {entry.id}"
                for entry in device_entries
                if any(
                    identifier[0] == DEVICE_TRACKER_DOMAIN 
                    for identifier in entry.identifiers
                )
            }      
        
        # Pobierz aktualne wartości konfiguracji
        current_track_devices = self.options.get(CONF_TRACK_DEVICES, DEFAULT_TRACK_DEVICES)
        current_device_trackers = self.options.get(CONF_DEVICE_TRACKERS, DEFAULT_DEVICE_TRACKERS)
        use_device_names = self.options.get(CONF_USE_DEVICE_NAMES, True)
        area_overrides = self.options.get(CONF_AREA_OVERRIDES, {})
        
        # Schemat formularza opcji
        options_schema = {            vol.Optional(
                CONF_SCAN_INTERVAL,
                default=scan_interval
            ): cv.positive_int,
            vol.Optional(
                CONF_DAILY_VARIABLES, 
                default=current_daily
            ): cv.multi_select(
                {var: TRANSLATED_VARIABLES.get(var, var.replace("_", " ").title()) 
                 for var in DEFAULT_DAILY_VARIABLES}
            ),
            vol.Optional(
                CONF_HOURLY_VARIABLES, 
                default=current_hourly
            ): cv.multi_select(
                {var: TRANSLATED_VARIABLES.get(var, var.replace("_", " ").title())
                 for var in DEFAULT_HOURLY_VARIABLES}
            ),
            vol.Optional(
                CONF_TRACK_DEVICES,
                default=current_track_devices
            ): bool,
        }
        
        # Dodaj opcje związane ze śledzeniem urządzeń tylko jeśli są dostępne
        if trackable_devices:
            options_schema.update({
                vol.Optional(
                    CONF_DEVICE_TRACKERS,
                    default=current_device_trackers
                ): cv.multi_select(trackable_devices),
                vol.Optional(
                    CONF_USE_DEVICE_NAMES,
                    default=use_device_names
                ): bool,
            })
            
            # Dodaj pola do nadpisywania nazw obszarów dla każdego trackera
            for device_id, device_name in trackable_devices.items():
                options_schema[
                    vol.Optional(
                        f"{CONF_AREA_OVERRIDES}_{device_id}",
                        default=area_overrides.get(device_id, device_name),
                    )
                ] = str

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(options_schema),
        )