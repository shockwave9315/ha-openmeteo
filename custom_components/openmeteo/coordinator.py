# SPDX-License-Identifier: Apache-2.0
"""Data update coordinator for Open-Meteo."""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_AREA_NAME_OVERRIDE,
    CONF_ENTITY_ID,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_MODE,
    CONF_TRACKED_ENTITY_ID,
    CONF_UPDATE_INTERVAL,
    DEFAULT_API_PROVIDER,
    DEFAULT_DAILY_VARIABLES,
    DEFAULT_HOURLY_VARIABLES,
    DEFAULT_UPDATE_INTERVAL,
    MODE_TRACK,
    URL,
)

_LOGGER = logging.getLogger(__name__)


class OpenMeteoDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching Open-Meteo data and tracking coordinates."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        self.hass = hass
        self.config_entry = entry
        interval = entry.options.get(
            CONF_UPDATE_INTERVAL,
            entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
        )
        try:
            interval = int(interval)
        except (TypeError, ValueError):
            interval = DEFAULT_UPDATE_INTERVAL
        if interval < 60:
            interval = 60
        super().__init__(
            hass, _LOGGER, name="Open-Meteo", update_interval=timedelta(seconds=interval)
        )
        self.location_name: str | None = entry.options.get(
            CONF_AREA_NAME_OVERRIDE, entry.data.get(CONF_AREA_NAME_OVERRIDE)
        )
        self.provider: str = entry.options.get("api_provider", DEFAULT_API_PROVIDER)
        self._last_data: dict[str, Any] | None = None
        self._last_coords: tuple[float, float] | None = None
        self._tracked_entity_id: str | None = None
        self._unsub_entity: callable | None = None

    async def async_options_updated(self) -> None:
        """Call when ConfigEntry options changed."""
        self._last_coords = None
        opts = self.config_entry.options or {}
        entity_id = opts.get("entity_id") or opts.get("track_entity") or opts.get("track_entity_id")
        await self._resubscribe_tracked_entity(entity_id)

    async def _resubscribe_tracked_entity(self, entity_id: str | None) -> None:
        if self._unsub_entity:
            self._unsub_entity()
            self._unsub_entity = None
        self._tracked_entity_id = entity_id
        if entity_id:
            async def _on_state_change(event):
                # refresh soon when entity coords appear/change
                await self.async_request_refresh()

            self._unsub_entity = async_track_state_change_event(
                self.hass, [entity_id], _on_state_change
            )

    async def _reverse_geocode(self, lat: float, lon: float) -> str | None:
        url = (
            "https://geocoding-api.open-meteo.com/v1/reverse"
            f"?latitude={lat:.5f}&longitude={lon:.5f}&language=pl&format=json"
        )
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    if resp.status != 200:
                        return None
                    js = await resp.json()
                    results = js.get("results") or []
                    if not results:
                        return None
                    r = results[0]
                    name = r.get("name") or r.get("admin2") or r.get("admin1")
                    country = r.get("country_code")
                    if name and country:
                        return f"{name}, {country}"
                    return name
        except Exception:
            return None

    def _coords_fallback(self, lat: float, lon: float) -> str:
        return f"{lat:.2f},{lon:.2f}"

    def _resolve_location(self) -> tuple[float, float, bool]:
        """Return (lat, lon, from_entity) chosen by precedence."""
        entry = self.config_entry
        opts = entry.options or {}
        track_enabled = (
            opts.get("track")
            or opts.get("track_enabled")
            or (entry.options.get(CONF_MODE) or entry.data.get(CONF_MODE)) == MODE_TRACK
        )
        track_entity_id = (
            opts.get("track_entity_id")
            or opts.get("track_entity")
            or opts.get(CONF_ENTITY_ID)
            or opts.get(CONF_TRACKED_ENTITY_ID)
            or entry.data.get("track_entity_id")
            or entry.data.get("track_entity")
            or entry.data.get(CONF_ENTITY_ID)
            or entry.data.get(CONF_TRACKED_ENTITY_ID)
        )
        lat = opts.get(CONF_LATITUDE, entry.data.get(CONF_LATITUDE))
        lon = opts.get(CONF_LONGITUDE, entry.data.get(CONF_LONGITUDE))

        if track_enabled and track_entity_id:
            st = self.hass.states.get(track_entity_id)
            if st:
                attrs = st.attributes or {}
                ent_lat = attrs.get("latitude")
                ent_lon = attrs.get("longitude")
                if isinstance(ent_lat, (int, float)) and isinstance(ent_lon, (int, float)):
                    return float(ent_lat), float(ent_lon), True

        if self._last_coords:
            return (*self._last_coords, False)

        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            return float(lat), float(lon), False

        return float(self.hass.config.latitude), float(self.hass.config.longitude), False

    async def _async_update_data(self) -> dict[str, Any]:
        latitude, longitude, from_entity = self._resolve_location()

        prev_loc = (self.data or {}).get("location") if self.data else None
        prev_lat = prev_loc.get("latitude") if prev_loc else None
        prev_lon = prev_loc.get("longitude") if prev_loc else None
        coords_changed = prev_lat != latitude or prev_lon != longitude

        loc_name = self.location_name
        last_loc_ts = (self.data or {}).get("last_location_update") if self.data else None
        if coords_changed:
            override = self.config_entry.options.get(
                CONF_AREA_NAME_OVERRIDE, self.config_entry.data.get(CONF_AREA_NAME_OVERRIDE)
            )
            if override:
                loc_name = override
            else:
                name = await self._reverse_geocode(latitude, longitude)
                loc_name = name or self._coords_fallback(latitude, longitude)
            last_loc_ts = dt_util.utcnow().isoformat()
            self.location_name = loc_name
        elif self.location_name:
            loc_name = self.location_name

        hourly_vars = list(dict.fromkeys(DEFAULT_HOURLY_VARIABLES + ["uv_index"]))
        daily_vars = DEFAULT_DAILY_VARIABLES
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current_weather": "true",
            "hourly": ",".join(hourly_vars),
            "daily": ",".join(daily_vars),
            "temperature_unit": "celsius",
            "windspeed_unit": "kmh",
            "precipitation_unit": "mm",
            "timezone": "auto",
            "timeformat": "iso8601",
        }
        params["current"] = ",".join(
            [
                "temperature_2m",
                "relative_humidity_2m",
                "dewpoint_2m",
                "pressure_msl",
                "wind_speed_10m",
                "wind_direction_10m",
                "wind_gusts_10m",
                "weathercode",
                "cloud_cover",
                "precipitation",
                "visibility",
                "uv_index",
            ]
        )

        session = async_get_clientsession(self.hass)
        headers = {
            "User-Agent": "HomeAssistant-OpenMeteo/1.0 (+https://www.home-assistant.io)"
        }
        try:
            for attempt in range(3):
                try:
                    async with session.get(
                        URL,
                        params=params,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=20),
                    ) as resp:
                        if resp.status >= 400:
                            text = await resp.text()
                            raise UpdateFailed(f"API error {resp.status}: {text[:100]}")
                        api_data = await resp.json()
                        self._last_data = api_data
                        break
                except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                    if attempt == 2:
                        raise UpdateFailed(f"Network error: {err}")
                    await asyncio.sleep(1.5 ** attempt + random.random() / 2)
            if self._last_data is None:
                raise UpdateFailed("No data received")
            self._last_data["location"] = {"latitude": latitude, "longitude": longitude}
            self._last_data["location_name"] = loc_name
            self._last_data["last_location_update"] = last_loc_ts
            hourly = self._last_data.setdefault("hourly", {})
            hourly.setdefault("time", [])
            hourly.setdefault("uv_index", [])
            if from_entity:
                self._last_coords = (latitude, longitude)
            return self._last_data
        except UpdateFailed:
            if self._last_data is not None:
                return self._last_data
            raise

