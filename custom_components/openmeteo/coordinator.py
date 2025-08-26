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
from homeassistant.helpers import device_registry as dr
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
    DEFAULT_DAILY_VARIABLES,
    DEFAULT_HOURLY_VARIABLES,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MODE_TRACK,
    URL,
    CONF_GEOCODE_INTERVAL_MIN,
    CONF_GEOCODE_MIN_DISTANCE_M,
    CONF_GEOCODER_PROVIDER,
    DEFAULT_GEOCODE_INTERVAL_MIN,
    DEFAULT_GEOCODE_MIN_DISTANCE_M,
    DEFAULT_GEOCODER_PROVIDER,
)

_LOGGER = logging.getLogger(__name__)


_GEOCODE_CACHE: dict[tuple[float, float], str] = {}
_GEOCODE_LOCK = asyncio.Lock()
_LAST_GEOCODE: float = 0.0


async def async_reverse_geocode(
    hass: HomeAssistant, lat: float, lon: float, provider: str
) -> str | None:
    """Reverse geocode coordinates to a place name with caching."""
    key = (round(lat, 4), round(lon, 4))
    if key in _GEOCODE_CACHE:
        return _GEOCODE_CACHE[key]
    if provider == "none":
        return None

    session = async_get_clientsession(hass)
    url: str | None = None
    headers = {"User-Agent": "HomeAssistant-OpenMeteo/1.0"}
    if provider == "osm_nominatim":
        url = (
            "https://nominatim.openstreetmap.org/reverse"
            f"?format=jsonv2&lat={lat:.5f}&lon={lon:.5f}&zoom=10&addressdetails=1"
        )
    elif provider == "photon":
        url = (
            "https://photon.komoot.io/reverse"
            f"?lat={lat:.5f}&lon={lon:.5f}&lang=pl"
        )
    if not url:
        return None

    js: dict[str, Any] | None = None
    async with _GEOCODE_LOCK:
        import time

        global _LAST_GEOCODE
        wait = 1.0 - (time.monotonic() - _LAST_GEOCODE)
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            async with session.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status != 200:
                    _LOGGER.debug("Geocode HTTP status %s", resp.status)
                    return None
                js = await resp.json()
        except Exception as err:  # pragma: no cover - network errors
            _LOGGER.debug("Geocode request failed: %s", err)
            return None
        finally:
            _LAST_GEOCODE = time.monotonic()

    if js is None:
        return None

    name: str | None = None
    try:
        if provider == "osm_nominatim":
            addr = js.get("address", {})
            name = (
                addr.get("town")
                or addr.get("city")
                or addr.get("village")
                or addr.get("municipality")
            )
            cc = addr.get("country_code")
            if name and cc:
                name = f"{name}, {cc.upper()}"
        elif provider == "photon":
            feats = js.get("features") or []
            if feats:
                props = feats[0].get("properties", {})
                name = props.get("city") or props.get("name")
                cc = props.get("country")
                if name and cc:
                    name = f"{name}, {cc.upper()}"
    except Exception:  # pragma: no cover - defensive
        name = None

    if name:
        _GEOCODE_CACHE[key] = name
    return name


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
        self.latitude: float | None = None
        self.longitude: float | None = None
        self.show_place_name: bool = bool(entry.options.get("show_place_name", True))
        self._last_data: dict[str, Any] | None = None
        self._tracked_entity_id: str | None = None
        self._unsub_entity: callable | None = None

    async def async_unload(self) -> None:
        """Cancel subscriptions and listeners."""
        if self._unsub_entity:
            self._unsub_entity()
            self._unsub_entity = None
        if self._unsub_refresh:
            self._unsub_refresh()
            self._unsub_refresh = None
        await super().async_shutdown()

    async def async_options_updated(self) -> None:
        """Apply updated ConfigEntry options."""
        opts = self.config_entry.options or {}
        entity_id = (
            opts.get("entity_id")
            or opts.get("track_entity")
            or opts.get("track_entity_id")
        )
        await self._resubscribe_tracked_entity(entity_id)
        interval = opts.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        try:
            interval = int(interval)
        except (TypeError, ValueError):
            interval = DEFAULT_UPDATE_INTERVAL
        if interval < 60:
            interval = 60
        self.update_interval = timedelta(seconds=interval)
        self.show_place_name = bool(opts.get("show_place_name", True))
        display_name = self.location_name
        if not display_name:
            lat = getattr(self, "latitude", None)
            lon = getattr(self, "longitude", None)
            if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                display_name = f"{lat:.5f},{lon:.5f}"
        name = display_name if (self.show_place_name and display_name) else "Open-Meteo"
        dev_reg = dr.async_get(self.hass)
        device = dev_reg.async_get_device({(DOMAIN, self.config_entry.entry_id)})
        if device:
            dev_reg.async_update_device(device.id, name=name)
        await self.async_request_refresh()

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

        opts = self.config_entry.options
        show_place = bool(opts.get("show_place_name", True))
        self.show_place_name = show_place
        provider = opts.get(CONF_GEOCODER_PROVIDER, DEFAULT_GEOCODER_PROVIDER)
        interval = int(opts.get(CONF_GEOCODE_INTERVAL_MIN, DEFAULT_GEOCODE_INTERVAL_MIN))
        min_dist = int(
            opts.get(CONF_GEOCODE_MIN_DISTANCE_M, DEFAULT_GEOCODE_MIN_DISTANCE_M)
        )

        store = (
            self.hass.data.setdefault(DOMAIN, {})
            .setdefault("entries", {})
            .setdefault(self.config_entry.entry_id, {})
        )
        last_time = store.get("geocode_last")
        last_lat = store.get("geocode_lat")
        last_lon = store.get("geocode_lon")
        now = dt_util.utcnow()
        delta = (now - last_time).total_seconds() / 60 if last_time else interval + 1
        need_geocode = show_place and (last_time is None or delta >= interval)
        if show_place and not need_geocode and isinstance(last_lat, (int, float)) and isinstance(last_lon, (int, float)):
            # check distance
            try:
                from math import radians, sin, cos, sqrt, atan2

                R = 6371000
                dlat = radians(latitude - last_lat)
                dlon = radians(longitude - last_lon)
                a = sin(dlat / 2) ** 2 + cos(radians(last_lat)) * cos(radians(latitude)) * sin(
                    dlon / 2
                ) ** 2
                c = 2 * atan2(sqrt(a), sqrt(1 - a))
                dist = R * c
                if dist > min_dist:
                    need_geocode = True
            except Exception:
                pass

        place = None
        if show_place and (need_geocode or store.get("location_name") is None):
            try:
                async with asyncio.timeout(10):
                    place = await async_reverse_geocode(
                        self.hass, latitude, longitude, provider
                    )
            except asyncio.TimeoutError:
                place = None
            store["geocode_last"] = now
            if place:
                store["geocode_lat"] = latitude
                store["geocode_lon"] = longitude
                store["geocode_last_success"] = now.isoformat()
        else:
            place = store.get("location_name")
        _LOGGER.debug(
            "Reverse geocode result for %s,%s: %s", latitude, longitude, place
        )
        display_name = place or f"{latitude:.5f},{longitude:.5f}"
        self.location_name = display_name
        self.latitude = latitude
        self.longitude = longitude
        store["coords"] = (latitude, longitude)
        store["source"] = src
        store["lat"] = latitude
        store["lon"] = longitude
        store["place_name"] = display_name
        store["location_name"] = display_name
        store["geocode_provider"] = provider
        last_loc_ts = dt_util.utcnow().isoformat()
        dev_reg = dr.async_get(self.hass)
        device = dev_reg.async_get_device({(DOMAIN, self.config_entry.entry_id)})
        if device:
            name = (
                display_name if self.show_place_name and display_name else "Open-Meteo"
            )
            dev_reg.async_update_device(device.id, name=name)
        async_dispatcher_send(
            self.hass, f"openmeteo_place_updated_{self.config_entry.entry_id}"
        )

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": ",".join(DEFAULT_HOURLY_VARIABLES),
            "daily": ",".join(DEFAULT_DAILY_VARIABLES),
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
                        timeout=aiohttp.ClientTimeout(total=5),
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
            self._last_data["location_name"] = display_name
            self._last_data["last_location_update"] = last_loc_ts
            hourly = self._last_data.setdefault("hourly", {})
            hourly.setdefault("time", [])
            hourly.setdefault("uv_index", [])
            return self._last_data
        except UpdateFailed:
            if self._last_data is not None:
                return self._last_data
            raise

