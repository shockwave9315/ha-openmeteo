"""Data update coordinator for Open-Meteo."""
from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta
from typing import Any, Optional

import aiohttp
import math
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


def _dew_point_c(temp_c: float | None, rh_pct: float | None) -> float | None:
    """Magnus-Tetens formula. Returns dew point in °C (1 decimal)."""
    if temp_c is None or rh_pct is None or rh_pct <= 0:
        return None
    a, b = 17.62, 243.12
    gamma = math.log(rh_pct / 100.0) + (a * temp_c) / (b + temp_c)
    dp = (b * gamma) / (a - gamma)
    return round(dp, 1)


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
        self._accepted_lat: float | None = None
        self._accepted_lon: float | None = None
        self._accepted_at: datetime | None = None
        override = entry.options.get(
            CONF_AREA_NAME_OVERRIDE, entry.data.get(CONF_AREA_NAME_OVERRIDE)
        )
        self.provider: str = entry.options.get("api_provider", DEFAULT_API_PROVIDER)
        self._warned_missing = False
        self._last_data: dict[str, Any] | None = None
        self.data: dict[str, Any] = {}
        if override:
            self.data["location_name"] = override

    @property
    def last_location_update(self) -> datetime | None:
        """Return timestamp when coordinates were last accepted."""
        return self._accepted_at

    async def _reverse_geocode(self, lat: float, lon: float) -> Optional[str]:
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

    async def _async_update_data(self) -> dict[str, Any]:
        mode = self._current_mode()
        cfg = {**self.entry.data, **self.entry.options}
        min_track = int(cfg.get(CONF_MIN_TRACK_INTERVAL, DEFAULT_MIN_TRACK_INTERVAL))
        now = dt_util.utcnow()
        coords_accepted = False

        if mode == MODE_TRACK:
            ent_id = cfg.get(CONF_ENTITY_ID) or cfg.get(CONF_TRACKED_ENTITY_ID)
            state = self.hass.states.get(ent_id) if ent_id else None
            if state and "latitude" in state.attributes and "longitude" in state.attributes:
                try:
                    lat = float(state.attributes["latitude"])
                    lon = float(state.attributes["longitude"])
                    if (
                        self._accepted_lat is None
                        or abs(lat - self._accepted_lat) > self.EPS
                        or abs(lon - self._accepted_lon) > self.EPS
                    ) and (
                        self._accepted_at is None
                        or now - self._accepted_at >= timedelta(minutes=min_track)
                    ):
                        self._accepted_lat = lat
                        self._accepted_lon = lon
                        self._accepted_at = now
                        coords_accepted = True
                    self._warned_missing = False
                except (TypeError, ValueError):
                    pass
            else:
                if not self._warned_missing:
                    _LOGGER.warning(
                        "Tracked entity %s missing or lacks GPS attributes", ent_id
                    )
                    self._warned_missing = True
        else:
            lat = float(cfg.get(CONF_LATITUDE, self.hass.config.latitude))
            lon = float(cfg.get(CONF_LONGITUDE, self.hass.config.longitude))
            if (
                self._accepted_lat is None
                or abs(lat - self._accepted_lat) > self.EPS
                or abs(lon - self._accepted_lon) > self.EPS
            ):
                self._accepted_lat = lat
                self._accepted_lon = lon
                self._accepted_at = now
                coords_accepted = True

        if self._accepted_lat is None or self._accepted_lon is None:
            raise UpdateFailed("No valid coordinates available")

        latitude = self._accepted_lat
        longitude = self._accepted_lon

        location_name = (self.data or {}).get("location_name")
        last_loc_update = (self.data or {}).get("last_location_update")

        if coords_accepted:
            if cfg.get(CONF_AREA_NAME_OVERRIDE):
                location_name = cfg.get(CONF_AREA_NAME_OVERRIDE)
            else:
                name = await self._reverse_geocode(latitude, longitude)
                location_name = name or self._coords_fallback(latitude, longitude)
            last_loc_update = now.isoformat()

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current_weather": "true",
            "hourly": ",".join(DEFAULT_HOURLY_VARIABLES),
            "daily": ",".join(DEFAULT_DAILY_VARIABLES),
            "temperature_unit": "celsius",
            "windspeed_unit": "kmh",
            "precipitation_unit": "mm",
        }

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

            current_temp = self._last_data.get("current_weather", {}).get("temperature")
            current_hum = None
            hum_arr = self._last_data.get("hourly", {}).get("relativehumidity_2m")
            if isinstance(hum_arr, list) and hum_arr:
                current_hum = hum_arr[0]
            self._last_data["dew_point"] = _dew_point_c(current_temp, current_hum)

            self._last_data["location_name"] = location_name or self._coords_fallback(
                latitude, longitude
            )
            self._last_data["last_location_update"] = last_loc_update
            return self._last_data
        except UpdateFailed:
            if self._last_data is not None:
                return self._last_data
            raise

