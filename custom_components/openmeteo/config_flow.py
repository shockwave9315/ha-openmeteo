"""Config and options flows for the Open-Meteo integration."""
from __future__ import annotations

import asyncio
import unicodedata
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
from homeassistant.helpers.translation import async_get_cached_translations

from .const import (
    AQ_SENSOR_KEYS,
    CONF_API_PROVIDER,
    CONF_AREA_NAME_OVERRIDE,
    CONF_ENABLED_AQ_SENSORS,
    CONF_ENABLED_SENSORS,
    CONF_ENABLED_WEATHER_SENSORS,
    CONF_ENTITY_ID,
    CONF_MIN_TRACK_INTERVAL,
    CONF_MODE,
    CONF_OPTIONS_SAVE_COOLDOWN_MIN,
    CONF_PRESET_AQ,
    CONF_PRESET_INFO,
    CONF_PRESET_WEATHER,
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
    PRESET_ALL,
    PRESET_KEEP,
    PRESET_NONE,
    SENSOR_LABELS,
    WEATHER_SENSOR_KEYS,
)
from .coordinator import async_reverse_geocode
from .helpers import (
    async_forward_geocode,  # new helper for onboarding
    async_zip_to_coords,
    haversine_km,
    async_reverse_postcode,
    async_reverse_postcode_info_cached,
    async_best_effort_postcode_cached,
    async_prefer_user_zip_postcode,
    format_postal,
)

def _build_schema(
    hass: HomeAssistant,
    mode: str,
    defaults: dict[str, Any],
    *,
    include_use_place: bool = True,
    tmp_weather_sel: list[str] | None = None,
    tmp_aq_sel: list[str] | None = None,
    show_preset_info: bool = False,
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
    lang_full = hass.config.language or "en"
    lang = lang_full.split("-")[0].lower()

    translations_config = async_get_cached_translations(
        hass, lang_full, "config", DOMAIN
    )
    translations_options = async_get_cached_translations(
        hass, lang_full, "options", DOMAIN
    )
    fallback_config: dict[str, str] = {}
    fallback_options: dict[str, str] = {}
    if lang_full.lower() != "en":
        fallback_config = async_get_cached_translations(hass, "en", "config", DOMAIN)
        fallback_options = async_get_cached_translations(
            hass, "en", "options", DOMAIN
        )

    def localize(key: str) -> str:
        search_keys = [
            f"component.{DOMAIN}.options.step.init.data.{key}",
            f"component.{DOMAIN}.options.step.mode_details.data.{key}",
            f"component.{DOMAIN}.config.step.mode_details.data.{key}",
            f"component.{DOMAIN}.config.step.user.data.{key}",
        ]
        for full_key in search_keys:
            if full_key in translations_options:
                return translations_options[full_key]
            if full_key in translations_config:
                return translations_config[full_key]
        for full_key in search_keys:
            if full_key in fallback_options:
                return fallback_options[full_key]
            if full_key in fallback_config:
                return fallback_config[full_key]
        fallback_map = {
            "preset_keep": "Keep current selection",
            "preset_all": "Select all",
            "preset_none": "Select none",
            "preset_weather": "Weather preset",
            "preset_aq": "Air quality preset",
            "preset_info": "Preset applied. Review the selection below and click Submit to save.",
        }
        return fallback_map.get(key, key)

    def _label_for(key: str) -> str:
        d = SENSOR_LABELS.get(key) or {}
        return d.get(lang) or d.get("en") or key

    weather_labeled = [
        {"label": _label_for(k), "value": k} for k in WEATHER_SENSOR_KEYS
    ]
    aq_labeled = [{"label": _label_for(k), "value": k} for k in AQ_SENSOR_KEYS]

    stored_weather = defaults.get(CONF_ENABLED_WEATHER_SENSORS)
    stored_aq = defaults.get(CONF_ENABLED_AQ_SENSORS)

    if tmp_weather_sel is not None:
        def_sel_weather = list(tmp_weather_sel)
    elif isinstance(stored_weather, list):
        def_sel_weather = list(stored_weather)
    else:
        legacy = defaults.get(CONF_ENABLED_SENSORS)
        if isinstance(legacy, list) and legacy:
            legacy_set = set(legacy)
            def_sel_weather = [
                k for k in WEATHER_SENSOR_KEYS if k in legacy_set
            ] or WEATHER_SENSOR_KEYS
        else:
            def_sel_weather = WEATHER_SENSOR_KEYS

    if tmp_aq_sel is not None:
        def_sel_aq = list(tmp_aq_sel)
    elif isinstance(stored_aq, list):
        def_sel_aq = list(stored_aq)
    else:
        legacy = defaults.get(CONF_ENABLED_SENSORS)
        if isinstance(legacy, list) and legacy:
            legacy_set = set(legacy)
            def_sel_aq = [k for k in AQ_SENSOR_KEYS if k in legacy_set] or AQ_SENSOR_KEYS
        else:
            def_sel_aq = AQ_SENSOR_KEYS

    preset_options = [
        {
            "label": localize("preset_keep"),
            "value": PRESET_KEEP,
        },
        {
            "label": localize("preset_all"),
            "value": PRESET_ALL,
        },
        {
            "label": localize("preset_none"),
            "value": PRESET_NONE,
        },
    ]
    extra[vol.Optional(CONF_PRESET_WEATHER, default=PRESET_KEEP)] = (
        selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=preset_options,
                multiple=False,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )
    )
    extra[
        vol.Optional(
            CONF_ENABLED_WEATHER_SENSORS,
            default=def_sel_weather,
        )
    ] = selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=weather_labeled,
            multiple=True,
            mode=selector.SelectSelectorMode.LIST,
        )
    )

    extra[vol.Optional(CONF_PRESET_AQ, default=PRESET_KEEP)] = (
        selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=preset_options,
                multiple=False,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        )
    )
    extra[
        vol.Optional(
            CONF_ENABLED_AQ_SENSORS,
            default=def_sel_aq,
        )
    ] = selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=aq_labeled,
            multiple=True,
            mode=selector.SelectSelectorMode.LIST,
        )
    )
    if show_preset_info:
        extra[vol.Optional(CONF_PRESET_INFO, default=localize("preset_info"))] = (
            selector.TextSelector(
                selector.TextSelectorConfig(
                    type=selector.TextSelectorType.TEXT,
                    multiline=True,
                )
            )
        )
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
        self._tmp_weather_sel: list[str] | None = None
        self._tmp_aq_sel: list[str] | None = None
        self._show_preset_info = False

    def _reset_preset_state(self) -> None:
        """Reset temporary preset selections and info flag."""

        self._tmp_weather_sel = None
        self._tmp_aq_sel = None
        self._show_preset_info = False

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Initial step asking for operating mode."""

        if user_input is None:
            self._reset_preset_state()

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

        if user_input is None:
            self._show_preset_info = False

        errors: dict[str, str] = {}
        if user_input is not None:
            query = (user_input.get("place_query") or "").strip()
            postal_code = (user_input.get("postal_code") or "").strip()
            admin1_query = (user_input.get("admin1") or "").strip()
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

                # Optional narrowing: filter by admin1/region if provided
                if admin1_query:
                    def _norm(s: str) -> str:
                        s = s.lower()
                        s = unicodedata.normalize("NFKD", s)
                        s = "".join(ch for ch in s if not unicodedata.combining(ch))
                        return s
                    qn = _norm(admin1_query)
                    filtered = []
                    for r in results:
                        a1 = (r.get("admin1") or "")
                        a1n = _norm(a1)
                        if qn in a1n or a1n.startswith(qn[:5]):
                            filtered.append(r)
                    results = filtered

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
                    # Limit to top 10 and enrich with per-item postcode
                    self._search_results = results[:10]
                    # Try to fetch postcode for top results (best-effort, throttled)
                    for idx, r in enumerate(self._search_results):
                        if idx >= 15:  # avoid rate limits; enrich only top 15
                            break
                        try:
                            # Best-effort postcode around the point (center + small neighborhood)
                            pc, approx = await async_prefer_user_zip_postcode(
                                self.hass,
                                float(r.get("latitude")),
                                float(r.get("longitude")),
                                country_code=country,
                                postal_code=postal_code,
                            )
                            if pc:
                                r["postcode"] = pc
                                if approx:
                                    r["_postcode_approx"] = True
                        except Exception:
                            continue
                        # throttle to avoid Nominatim rate limits
                        await asyncio.sleep(1.0)
                    self._search_zip = postal_code or None
                    return await self.async_step_pick_place()

        # Build schema: always place_query; postal_code optional; country_code only if HA has no country
        schema_fields: dict[Any, Any] = {
            vol.Required("place_query", default=user_input.get("place_query") if user_input else ""): str,
            vol.Optional("postal_code", default=user_input.get("postal_code") if user_input else ""): str,
        }
        # If country is PL (from HA) or user selected PL in this form, show dropdown of voivodeships
        user_country = (user_input.get("country_code") if user_input else "") or ""
        user_country = user_country.strip().upper()
        ha_country = (self.hass.config.country or "").strip().upper()
        is_pl = (ha_country == "PL") or (user_country == "PL")

        if is_pl:
            voivodeships_pl = [
                "Dolnośląskie",
                "Kujawsko-pomorskie",
                "Lubelskie",
                "Lubuskie",
                "Łódzkie",
                "Małopolskie",
                "Mazowieckie",
                "Opolskie",
                "Podkarpackie",
                "Podlaskie",
                "Pomorskie",
                "Śląskie",
                "Świętokrzyskie",
                "Warmińsko-mazurskie",
                "Wielkopolskie",
                "Zachodniopomorskie",
            ]
            schema_fields[vol.Optional("admin1", default=user_input.get("admin1") if user_input else "")] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[{ "label": v, "value": v } for v in voivodeships_pl],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
        else:
            schema_fields[vol.Optional("admin1", default=user_input.get("admin1") if user_input else "")] = str
        if not (self.hass.config.country or "").strip():
            schema_fields[vol.Optional("country_code", default=(user_input.get("country_code") if user_input else "PL"))] = str

        schema = vol.Schema(schema_fields)
        return self.async_show_form(step_id="search_place", data_schema=schema, errors=errors)

    async def async_step_pick_place(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Let the user pick one of the geocoding results, then prefill lat/lon."""

        assert self._mode == MODE_STATIC

        if user_input is None:
            self._show_preset_info = False

        def _label(r: dict[str, Any]) -> str:
            name = r.get("name") or "?"
            admin1 = r.get("admin1") or r.get("admin2") or ""
            cc = (r.get("country_code") or "").upper()
            lat = r.get("latitude")
            lon = r.get("longitude")
            pc = (r.get("postcode") or "").strip()
            st = (r.get("_state") or "").strip()
            approx_pc = bool(r.get("_postcode_approx"))
            try:
                base = f"{name}, {admin1}, {cc} ({float(lat):.4f}, {float(lon):.4f})"
                fpc = format_postal(cc, pc) if pc else None
                # Show postcode whenever available (we removed user-zip fallback, so it's per-point)
                if fpc:
                    mark = "≈" if approx_pc else ""
                    return f"{base} • kod: {mark}{fpc}"
                return base
            except Exception:
                base = f"{name}, {admin1}, {cc}"
                fpc = format_postal(cc, pc) if pc else None
                if fpc:
                    mark = "≈" if approx_pc else ""
                    return f"{base} • kod: {mark}{fpc}"
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

        if user_input is None:
            self._show_preset_info = False

        errors: dict[str, str] = {}
        defaults = dict(self._prefill)
        if user_input is not None:
            user_input = dict(user_input)
            defaults.update(
                {
                    k: v
                    for k, v in user_input.items()
                    if k
                    not in {
                        CONF_ENABLED_WEATHER_SENSORS,
                        CONF_ENABLED_AQ_SENSORS,
                        CONF_PRESET_WEATHER,
                        CONF_PRESET_AQ,
                        CONF_PRESET_INFO,
                    }
                }
            )

            preset_w = user_input.get(CONF_PRESET_WEATHER, PRESET_KEEP)
            preset_a = user_input.get(CONF_PRESET_AQ, PRESET_KEEP)

            stored_weather_default = defaults.get(CONF_ENABLED_WEATHER_SENSORS)
            if isinstance(stored_weather_default, list):
                fallback_weather = list(stored_weather_default)
            else:
                fallback_weather = WEATHER_SENSOR_KEYS[:]

            stored_aq_default = defaults.get(CONF_ENABLED_AQ_SENSORS)
            if isinstance(stored_aq_default, list):
                fallback_aq = list(stored_aq_default)
            else:
                fallback_aq = AQ_SENSOR_KEYS[:]

            weather_raw = user_input.get(CONF_ENABLED_WEATHER_SENSORS)
            aq_raw = user_input.get(CONF_ENABLED_AQ_SENSORS)
            cur_weather = list(weather_raw or [])
            cur_aq = list(aq_raw or [])

            if preset_w == PRESET_ALL:
                self._tmp_weather_sel = WEATHER_SENSOR_KEYS[:]
            elif preset_w == PRESET_NONE:
                self._tmp_weather_sel = []
            else:
                if weather_raw is not None:
                    self._tmp_weather_sel = cur_weather
                elif self._tmp_weather_sel is None:
                    self._tmp_weather_sel = list(fallback_weather)

            if preset_a == PRESET_ALL:
                self._tmp_aq_sel = AQ_SENSOR_KEYS[:]
            elif preset_a == PRESET_NONE:
                self._tmp_aq_sel = []
            else:
                if aq_raw is not None:
                    self._tmp_aq_sel = cur_aq
                elif self._tmp_aq_sel is None:
                    self._tmp_aq_sel = list(fallback_aq)

            if preset_w != PRESET_KEEP or preset_a != PRESET_KEEP:
                self._show_preset_info = True
                defaults_with_tmp = dict(defaults)
                defaults_with_tmp[CONF_ENABLED_WEATHER_SENSORS] = (
                    self._tmp_weather_sel or WEATHER_SENSOR_KEYS
                )
                defaults_with_tmp[CONF_ENABLED_AQ_SENSORS] = (
                    self._tmp_aq_sel or AQ_SENSOR_KEYS
                )
                user_input[CONF_PRESET_WEATHER] = PRESET_KEEP
                user_input[CONF_PRESET_AQ] = PRESET_KEEP
                user_input.pop(CONF_PRESET_INFO, None)
                schema = _build_schema(
                    self.hass,
                    self._mode,
                    defaults_with_tmp,
                    include_use_place=self._mode == MODE_TRACK,
                    tmp_weather_sel=self._tmp_weather_sel,
                    tmp_aq_sel=self._tmp_aq_sel,
                    show_preset_info=self._show_preset_info,
                )
                return self.async_show_form(
                    step_id="mode_details", data_schema=schema, errors={}
                )

            self._show_preset_info = False

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
                if self._tmp_weather_sel is not None:
                    final_weather = list(self._tmp_weather_sel)
                elif weather_raw is not None:
                    final_weather = cur_weather
                else:
                    final_weather = list(fallback_weather)

                if self._tmp_aq_sel is not None:
                    final_aq = list(self._tmp_aq_sel)
                elif aq_raw is not None:
                    final_aq = cur_aq
                else:
                    final_aq = list(fallback_aq)

                user_input[CONF_ENABLED_WEATHER_SENSORS] = final_weather
                user_input[CONF_ENABLED_AQ_SENSORS] = final_aq
                user_input.pop(CONF_PRESET_INFO, None)
                user_input.pop(CONF_PRESET_WEATHER, None)
                user_input.pop(CONF_PRESET_AQ, None)

                data = {**user_input, CONF_MODE: self._mode}
                title = await _async_guess_title(self.hass, self._mode, data)
                self._reset_preset_state()
                return self.async_create_entry(title=title, data=data)

        schema = _build_schema(
            self.hass,
            self._mode,
            defaults,
            include_use_place=self._mode == MODE_TRACK,
            tmp_weather_sel=self._tmp_weather_sel,
            tmp_aq_sel=self._tmp_aq_sel,
            show_preset_info=self._show_preset_info,
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
        self._tmp_weather_sel: list[str] | None = None
        self._tmp_aq_sel: list[str] | None = None
        self._show_preset_info = False

    def _reset_preset_state(self) -> None:
        """Reset temporary preset selections for options flow."""

        self._tmp_weather_sel = None
        self._tmp_aq_sel = None
        self._show_preset_info = False

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """First step of the options flow: choose mode."""

        if user_input is None:
            self._reset_preset_state()

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

        if user_input is None:
            self._show_preset_info = False

        merged_defaults = {**self._entry.data, **self._entry.options}
        defaults = dict(merged_defaults)
        errors: dict[str, str] = {}

        if user_input is not None:
            user_input = dict(user_input)
            defaults.update(
                {
                    k: v
                    for k, v in user_input.items()
                    if k
                    not in {
                        CONF_ENABLED_WEATHER_SENSORS,
                        CONF_ENABLED_AQ_SENSORS,
                        CONF_PRESET_WEATHER,
                        CONF_PRESET_AQ,
                        CONF_PRESET_INFO,
                    }
                }
            )

            preset_w = user_input.get(CONF_PRESET_WEATHER, PRESET_KEEP)
            preset_a = user_input.get(CONF_PRESET_AQ, PRESET_KEEP)

            stored_weather_default = defaults.get(CONF_ENABLED_WEATHER_SENSORS)
            if isinstance(stored_weather_default, list):
                fallback_weather = list(stored_weather_default)
            else:
                fallback_weather = WEATHER_SENSOR_KEYS[:]

            stored_aq_default = defaults.get(CONF_ENABLED_AQ_SENSORS)
            if isinstance(stored_aq_default, list):
                fallback_aq = list(stored_aq_default)
            else:
                fallback_aq = AQ_SENSOR_KEYS[:]

            weather_raw = user_input.get(CONF_ENABLED_WEATHER_SENSORS)
            aq_raw = user_input.get(CONF_ENABLED_AQ_SENSORS)
            cur_weather = list(weather_raw or [])
            cur_aq = list(aq_raw or [])

            if preset_w == PRESET_ALL:
                self._tmp_weather_sel = WEATHER_SENSOR_KEYS[:]
            elif preset_w == PRESET_NONE:
                self._tmp_weather_sel = []
            else:
                if weather_raw is not None:
                    self._tmp_weather_sel = cur_weather
                elif self._tmp_weather_sel is None:
                    self._tmp_weather_sel = list(fallback_weather)

            if preset_a == PRESET_ALL:
                self._tmp_aq_sel = AQ_SENSOR_KEYS[:]
            elif preset_a == PRESET_NONE:
                self._tmp_aq_sel = []
            else:
                if aq_raw is not None:
                    self._tmp_aq_sel = cur_aq
                elif self._tmp_aq_sel is None:
                    self._tmp_aq_sel = list(fallback_aq)

            if preset_w != PRESET_KEEP or preset_a != PRESET_KEEP:
                self._show_preset_info = True
                defaults_with_tmp = dict(defaults)
                defaults_with_tmp[CONF_ENABLED_WEATHER_SENSORS] = (
                    self._tmp_weather_sel or WEATHER_SENSOR_KEYS
                )
                defaults_with_tmp[CONF_ENABLED_AQ_SENSORS] = (
                    self._tmp_aq_sel or AQ_SENSOR_KEYS
                )
                user_input[CONF_PRESET_WEATHER] = PRESET_KEEP
                user_input[CONF_PRESET_AQ] = PRESET_KEEP
                user_input.pop(CONF_PRESET_INFO, None)
                schema = _build_schema(
                    self.hass,
                    self._mode,
                    defaults_with_tmp,
                    include_use_place=self._mode == MODE_TRACK,
                    tmp_weather_sel=self._tmp_weather_sel,
                    tmp_aq_sel=self._tmp_aq_sel,
                    show_preset_info=self._show_preset_info,
                )
                return self.async_show_form(
                    step_id="mode_details", data_schema=schema, errors={}
                )

            self._show_preset_info = False

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

                new_options.pop(CONF_ENABLED_SENSORS, None)

                if self._tmp_weather_sel is not None:
                    final_weather = list(self._tmp_weather_sel)
                elif weather_raw is not None:
                    final_weather = cur_weather
                else:
                    final_weather = list(fallback_weather)

                if self._tmp_aq_sel is not None:
                    final_aq = list(self._tmp_aq_sel)
                elif aq_raw is not None:
                    final_aq = cur_aq
                else:
                    final_aq = list(fallback_aq)

                user_input[CONF_ENABLED_WEATHER_SENSORS] = final_weather
                user_input[CONF_ENABLED_AQ_SENSORS] = final_aq
                user_input.pop(CONF_PRESET_INFO, None)
                user_input.pop(CONF_PRESET_WEATHER, None)
                user_input.pop(CONF_PRESET_AQ, None)

                new_options.update(user_input)
                new_options[CONF_MODE] = self._mode
                self._reset_preset_state()

                return self.async_create_entry(title="", data=new_options)

        schema = _build_schema(
            self.hass,
            self._mode,
            defaults,
            include_use_place=self._mode == MODE_TRACK,
            tmp_weather_sel=self._tmp_weather_sel,
            tmp_aq_sel=self._tmp_aq_sel,
            show_preset_info=self._show_preset_info,
        )
        return self.async_show_form(
            step_id="mode_details", data_schema=schema, errors=errors
        )
