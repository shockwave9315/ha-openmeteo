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
    CONF_OPTIONS_SAVE_COOLDOWN_MIN,
    CONF_REVERSE_GEOCODE_COOLDOWN_MIN,
    CONF_UNITS,
    CONF_UPDATE_INTERVAL,  # legacy seconds key (fallback)
    CONF_UPDATE_INTERVAL_MIN,
    CONF_USE_PLACE_AS_DEVICE_NAME,
    DEFAULT_API_PROVIDER,
    DEFAULT_MIN_TRACK_INTERVAL,
    DEFAULT_OPTIONS_SAVE_COOLDOWN_MIN,
    DEFAULT_REVERSE_GEOCODE_COOLDOWN_MIN,
    DEFAULT_UNITS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MODE_STATIC,
    MODE_TRACK,
)
from .coordinator import async_reverse_geocode
from .helpers import (
    async_forward_geocode,  # new helper for onboarding
    async_zip_to_coords,
    haversine_km,
    async_reverse_postcode,
    format_postal,
)


def _build_schema(
    hass: HomeAssistant,
    mode: str,
    defaults: dict[str, Any],
    *,
    include_use_place: bool = True,
) -> vol.Schema:
    """Build a schema for the config and options flow."""

    # Derive minutes-based defaults for UI fields
    def _default_update_interval_min(d: dict[str, Any]) -> int:
        val = d.get(CONF_UPDATE_INTERVAL_MIN)
        if val is not None:
            try:
                return max(1, int(val))
            except (TypeError, ValueError):
                pass
        # Fallback to legacy seconds
        sec = d.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        try:
            return max(1, int(sec) // 60)
        except (TypeError, ValueError):
            return max(1, DEFAULT_UPDATE_INTERVAL // 60)

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
            CONF_UPDATE_INTERVAL_MIN,
            default=_default_update_interval_min(defaults),
        ): vol.All(vol.Coerce(int), vol.Range(min=1)),
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
        # Cooldowny tylko dla trybu TRACK
        extra[vol.Optional(
            CONF_REVERSE_GEOCODE_COOLDOWN_MIN,
            default=defaults.get(CONF_REVERSE_GEOCODE_COOLDOWN_MIN, DEFAULT_REVERSE_GEOCODE_COOLDOWN_MIN),
        )] = vol.All(vol.Coerce(int), vol.Range(min=1, max=240))
        extra[vol.Optional(
            CONF_OPTIONS_SAVE_COOLDOWN_MIN,
            default=defaults.get(CONF_OPTIONS_SAVE_COOLDOWN_MIN, DEFAULT_OPTIONS_SAVE_COOLDOWN_MIN),
        )] = vol.All(vol.Coerce(int), vol.Range(min=1, max=360))

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
        self._prefill: dict[str, Any] = {}
        self._search_results: list[dict[str, Any]] = []
        self._search_zip: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Initial step asking for operating mode."""

        if user_input is not None:
            self._mode = user_input[CONF_MODE]
            if self._mode == MODE_STATIC:
                return await self.async_step_search_place()
            return await self.async_step_mode_details()

        schema = vol.Schema(
            {vol.Required(CONF_MODE, default=self._mode): vol.In([MODE_STATIC, MODE_TRACK])}
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_search_place(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Static onboarding: ask for a place name to forward‑geocode."""

        assert self._mode == MODE_STATIC

        errors: dict[str, str] = {}
        if user_input is not None:
            query = (user_input.get("place_query") or "").strip()
            postal_code = (user_input.get("postal_code") or "").strip()
            # Determine country preference
            country_cfg = (self.hass.config.country or "").upper()
            country_ui = (user_input.get("country_code") or "").strip().upper()
            country = country_cfg or country_ui
            if not query:
                errors["place_query"] = "required"
            else:
                try:
                    results = await async_forward_geocode(self.hass, query, count=10)
                except Exception:  # pragma: no cover – defensive
                    results = []
                    errors["base"] = "network_error"

                # Optional narrowing: keep only selected country if provided
                if country:
                    results = [r for r in results if (r.get("country_code") or "").upper() == country]

                if not results and not errors:
                    errors["place_query"] = "no_results"
                else:
                    # Sort by distance to postal code center if provided and country known
                    if postal_code and country:
                        zip_center = await async_zip_to_coords(self.hass, country, postal_code)
                        if zip_center is not None:
                            zlat, zlon = zip_center
                            try:
                                results.sort(
                                    key=lambda r: haversine_km(
                                        float(r.get("latitude")),
                                        float(r.get("longitude")),
                                        float(zlat),
                                        float(zlon),
                                    )
                                )
                            except Exception:
                                pass
                    # Limit to top 50 and enrich with per-item postcode
                    self._search_results = results[:50]
                    # Try to fetch postcode for each result (best-effort)
                    for r in self._search_results:
                        try:
                            info = await async_reverse_postcode_info_cached(
                                self.hass,
                                float(r.get("latitude")),
                                float(r.get("longitude")),
                            )
                            if info:
                                if info.get("postcode"):
                                    r["postcode"] = info.get("postcode")
                                if info.get("state"):
                                    r["_state"] = info.get("state")
                        except Exception:
                            continue
                    self._search_zip = postal_code or None
                    return await self.async_step_pick_place()

        # Build schema: always place_query; postal_code optional; country_code only if HA has no country
        schema_fields: dict[Any, Any] = {
            vol.Required("place_query", default=user_input.get("place_query") if user_input else ""): str,
            vol.Optional("postal_code", default=user_input.get("postal_code") if user_input else ""): str,
        }
        if not (self.hass.config.country or "").strip():
            schema_fields[vol.Optional("country_code", default=(user_input.get("country_code") if user_input else "PL"))] = str

        schema = vol.Schema(schema_fields)
        return self.async_show_form(step_id="search_place", data_schema=schema, errors=errors)

    async def async_step_pick_place(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Let the user pick one of the geocoding results, then prefill lat/lon."""

        assert self._mode == MODE_STATIC

        def _label(r: dict[str, Any]) -> str:
            name = r.get("name") or "?"
            admin1 = r.get("admin1") or r.get("admin2") or ""
            cc = (r.get("country_code") or "").upper()
            lat = r.get("latitude")
            lon = r.get("longitude")
            pc = (r.get("postcode") or "").strip()
            st = (r.get("_state") or "").strip()
            try:
                base = f"{name}, {admin1}, {cc} ({float(lat):.4f}, {float(lon):.4f})"
                fpc = format_postal(cc, pc) if pc else None
                # show postcode only if available and (state matches admin1 or state missing)
                if fpc and (not st or st.lower() in admin1.lower() or admin1.lower() in st.lower()):
                    return f"{base} • kod: {fpc}"
                return base
            except Exception:
                base = f"{name}, {admin1}, {cc}"
                fpc = format_postal(cc, pc) if pc else None
                if fpc and (not st or st.lower() in admin1.lower() or admin1.lower() in st.lower()):
                    return f"{base} • kod: {fpc}"
                return base

        options = {str(idx): _label(r) for idx, r in enumerate(self._search_results)}

        errors: dict[str, str] = {}
        if user_input is not None:
            key = user_input.get("picked")
            if key in options:
                r = self._search_results[int(key)]
                self._prefill = {
                    CONF_LATITUDE: r.get("latitude"),
                    CONF_LONGITUDE: r.get("longitude"),
                }
                return await self.async_step_mode_details()
            errors["picked"] = "required"

        schema = vol.Schema({vol.Required("picked"): vol.In(options)})
        return self.async_show_form(step_id="pick_place", data_schema=schema, errors=errors)

    async def async_step_mode_details(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Collect details specific to the chosen mode."""

        errors: dict[str, str] = {}
        defaults = user_input or dict(self._prefill)

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
