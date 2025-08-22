# SPDX-License-Identifier: Apache-2.0
# SPDX-License-Identifier: Apache-2.0
"""Data update coordinator for Open-Meteo."""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_AREA_NAME_OVERRIDE,
    CONF_ENTITY_ID,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_MIN_TRACK_INTERVAL,
    CONF_MODE,
    CONF_UPDATE_INTERVAL,
    CONF_TRACKED_ENTITY_ID,
    CONF_TRACKING_MODE,
    DEFAULT_API_PROVIDER,
    DEFAULT_DAILY_VARIABLES,
    DEFAULT_HOURLY_VARIABLES,
    DEFAULT_MIN_TRACK_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MODE_STATIC,
    MODE_TRACK,
    URL,
)

_LOGGER = logging.getLogger(__name__)


class OpenMeteoDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching Open-Meteo data and tracking coordinates."""

    EPS = 1e-4

    def __init__(self, hass: HomeAssistant, entry) -> None:
        self.entry = entry
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
        self._cached: tuple[float, float] | None = None
        self._accepted_lat: float | None = None
        self._accepted_lon: float | None = None
        self._accepted_at: datetime | None = None
        self.location_name: str | None = entry.options.get(
            CONF_AREA_NAME_OVERRIDE, entry.data.get(CONF_AREA_NAME_OVERRIDE)
        )
        self.provider: str = entry.options.get("api_provider", DEFAULT_API_PROVIDER)
        self._warned_missing = False
        self._last_data: dict[str, Any] | None = None

    @property
    def last_location_update(self) -> datetime | None:
        """Return timestamp when coordinates were last accepted."""
        return self._accepted_at

    def _current_mode(self) -> str:
        data = {**self.entry.data, **self.entry.options}
        mode = data.get(CONF_MODE) or data.get(CONF_TRACKING_MODE)
        if not mode:
            if data.get(CONF_ENTITY_ID) or data.get(CONF_TRACKED_ENTITY_ID):
                return MODE_TRACK
            return MODE_STATIC
        if mode in (MODE_STATIC, MODE_TRACK):
            return mode
        if mode == "device":
            return MODE_TRACK
        return MODE_STATIC

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

    async def _async_update_data(self) -> dict[str, Any]:
        mode = self._current_mode()
        data = {**self.entry.data, **self.entry.options}
        min_track = int(data.get(CONF_MIN_TRACK_INTERVAL, DEFAULT_MIN_TRACK_INTERVAL))
        now = dt_util.utcnow()

        prev_name = self.data.get("location_name") if self.data else None
        prev_loc_ts = self.data.get("last_location_update") if self.data else None
        coords_changed = False

        if mode == MODE_TRACK:
            ent_id = data.get(CONF_ENTITY_ID) or data.get(CONF_TRACKED_ENTITY_ID)
            state = self.hass.states.get(ent_id) if ent_id else None
            if state and "latitude" in state.attributes and "longitude" in state.attributes:
                try:
                    lat = float(state.attributes["latitude"])
                    lon = float(state.attributes["longitude"])
                    if (
                        self._cached is None
                        or (
                            abs(lat - self._cached[0]) > self.EPS
                            or abs(lon - self._cached[1]) > self.EPS
                        )
                        and (
                            self._accepted_at is None
                            or now - self._accepted_at >= timedelta(minutes=min_track)
                        )
                    ):
                        self._cached = (lat, lon)
                        self._accepted_lat = lat
                        self._accepted_lon = lon
                        self._accepted_at = now
                        coords_changed = True
                    self._warned_missing = False
                except (TypeError, ValueError):
                    pass
            else:
                if not self._warned_missing:
                    _LOGGER.warning(
                        "Tracked entity %s missing or lacks GPS attributes, "
                        "falling back to configured coordinates",
                        ent_id,
                    )
                    self._warned_missing = True
                if self._cached is None:
                    lat = float(
                        data.get(CONF_LATITUDE, self.hass.config.latitude)
                    )
                    lon = float(
                        data.get(CONF_LONGITUDE, self.hass.config.longitude)
                    )
                    self._cached = (lat, lon)
                    self._accepted_lat = lat
                    self._accepted_lon = lon
                    self._accepted_at = (
                        now if self._accepted_at is None else self._accepted_at
                    )
                    coords_changed = True
        else:
            lat = float(
                data.get(CONF_LATITUDE, self.hass.config.latitude)
            )
            lon = float(
                data.get(CONF_LONGITUDE, self.hass.config.longitude)
            )
            if (
                self._cached is None
                or abs(lat - self._cached[0]) > self.EPS
                or abs(lon - self._cached[1]) > self.EPS
            ):
                self._cached = (lat, lon)
                self._accepted_lat = lat
                self._accepted_lon = lon
                self._accepted_at = now if self._accepted_at is None else self._accepted_at
                coords_changed = True
            elif self._accepted_at is None:
                self._accepted_at = now

        loc_name = prev_name
        last_loc_ts = prev_loc_ts
        if coords_changed:
            if data.get(CONF_AREA_NAME_OVERRIDE):
                loc_name = data.get(CONF_AREA_NAME_OVERRIDE)
            else:
                name = await self._reverse_geocode(lat, lon)
                loc_name = name or self._coords_fallback(lat, lon)
            last_loc_ts = now.isoformat()
            self.location_name = loc_name
        elif self.location_name:
            loc_name = self.location_name

        if not self._cached:
            raise UpdateFailed("No valid coordinates available")
        latitude, longitude = self._cached

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current_weather": "true",
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
                "cloud_cover",
                "precipitation",
                "visibility",
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
            return self._last_data
        except UpdateFailed:
            if self._last_data is not None:
                return self._last_data
            raise

