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
from homeassistant.helpers.dispatcher import async_dispatcher_send
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
    DOMAIN,
    MODE_TRACK,
    URL,
)
from .helpers import maybe_update_device_name, maybe_update_entry_title

_LOGGER = logging.getLogger(__name__)


async def async_reverse_geocode(
    hass: HomeAssistant, lat: float, lon: float
) -> str | None:
    """Resolve a human-readable place for given coords using Open-Meteo geocoding."""
    try:
        lang = getattr(hass.config, "language", None) or "en"
        url = (
            "https://geocoding-api.open-meteo.com/v1/reverse"
            f"?latitude={lat:.5f}&longitude={lon:.5f}&language={lang}&format=json"
        )
        session = async_get_clientsession(hass)
        async with session.get(url, timeout=10) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError):
        return None

    results = data.get("results") or []
    if not results:
        return None

    # priorytet: name -> admin2 -> admin1
    first = results[0]
    for key in ("name", "admin2", "admin1"):
        val = first.get(key)
        if val:
            return str(val)
    return None

class OpenMeteoDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching Open-Meteo data and tracking coordinates."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        self.hass = hass
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
        self.config_entry = entry
        override = entry.options.get(CONF_AREA_NAME_OVERRIDE)
        if override is None:
            override = entry.data.get(CONF_AREA_NAME_OVERRIDE)
        self.location_name: str | None = override
        self.provider: str = entry.options.get("api_provider", DEFAULT_API_PROVIDER)
        self._last_data: dict[str, Any] | None = None
        self._tracked_entity_id: str | None = None
        self._unsub_entity: callable | None = None

    async def async_shutdown(self) -> None:
        """Cancel subscriptions and shut down."""
        if self._unsub_entity:
            self._unsub_entity()
            self._unsub_entity = None
        await super().async_shutdown()

    async def async_options_updated(self) -> None:
        """Call when ConfigEntry options changed."""
        opts = self.config_entry.options or {}
        entity_id = (
            opts.get("entity_id")
            or opts.get("track_entity")
            or opts.get("track_entity_id")
        )
        await self._resubscribe_tracked_entity(entity_id)
        from . import resolve_coords

        latitude, longitude, _ = await resolve_coords(
            self.hass, self.config_entry
        )
        geocode_on = self.config_entry.options.get(
            "geocode_name", self.config_entry.data.get("geocode_name", True)
        )
        place = (
            await async_reverse_geocode(self.hass, latitude, longitude)
            if geocode_on
            else None
        )
        _LOGGER.debug(
            "Reverse geocode result for %s,%s: %s", latitude, longitude, place
        )
        self.location_name = place
        override = self.config_entry.options.get(CONF_AREA_NAME_OVERRIDE)
        if override is None:
            override = self.config_entry.data.get(CONF_AREA_NAME_OVERRIDE)
        store = (
            self.hass.data.setdefault(DOMAIN, {})
            .setdefault("entries", {})
            .setdefault(self.config_entry.entry_id, {})
        )
        store["lat"] = latitude
        store["lon"] = longitude
        store["place"] = place
        await maybe_update_entry_title(
            self.hass, self.config_entry, latitude, longitude, place
        )
        await maybe_update_device_name(
            self.hass,
            self.config_entry,
            override or place,
        )
        async_dispatcher_send(
            self.hass, f"openmeteo_place_updated_{self.config_entry.entry_id}"
        )

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
            from . import _register_unsub

            _register_unsub(self.hass, self.config_entry, self._unsub_entity)

    def _schedule_refresh(self) -> None:
        super()._schedule_refresh()
        if self._unsub_refresh:
            from . import _register_unsub

            _register_unsub(self.hass, self.config_entry, self._unsub_refresh)

    async def _async_update_data(self) -> dict[str, Any]:
        from . import resolve_coords

        latitude, longitude, src = await resolve_coords(
            self.hass, self.config_entry
        )

        geocode_on = self.config_entry.options.get(
            "geocode_name", self.config_entry.data.get("geocode_name", True)
        )
        place = (
            await async_reverse_geocode(self.hass, latitude, longitude)
            if geocode_on
            else None
        )
        _LOGGER.debug(
            "Reverse geocode result for %s,%s: %s", latitude, longitude, place
        )
        self.location_name = place
        override = self.config_entry.options.get(CONF_AREA_NAME_OVERRIDE)
        if override is None:
            override = self.config_entry.data.get(CONF_AREA_NAME_OVERRIDE)
        store = (
            self.hass.data.setdefault(DOMAIN, {})
            .setdefault("entries", {})
            .setdefault(self.config_entry.entry_id, {})
        )
        store["coords"] = (latitude, longitude)
        store["source"] = src
        store["lat"] = latitude
        store["lon"] = longitude
        store["place_name"] = place
        store["place"] = place
        last_loc_ts = dt_util.utcnow().isoformat()
        await maybe_update_entry_title(
            self.hass, self.config_entry, latitude, longitude, place
        )
        await maybe_update_device_name(
            self.hass,
            self.config_entry,
            override or place,
        )
        async_dispatcher_send(
            self.hass, f"openmeteo_place_updated_{self.config_entry.entry_id}"
        )

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
            self._last_data["location_name"] = place
            self._last_data["last_location_update"] = last_loc_ts
            hourly = self._last_data.setdefault("hourly", {})
            hourly.setdefault("time", [])
            hourly.setdefault("uv_index", [])
            return self._last_data
        except UpdateFailed:
            if self._last_data is not None:
                return self._last_data
            raise

