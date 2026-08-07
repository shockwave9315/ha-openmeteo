"""Open-Meteo HTTP client used by the v2 coordinator."""
from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import HTTP_USER_AGENT, URL

AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

CURRENT_FIELDS = (
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "is_day",
    "precipitation",
    "rain",
    "snowfall",
    "weather_code",
    "cloud_cover",
    "pressure_msl",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
)

HOURLY_FIELDS = (
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "dew_point_2m",
    "precipitation",
    "rain",
    "snowfall",
    "precipitation_probability",
    "weather_code",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "pressure_msl",
    "visibility",
    "cloud_cover",
    "is_day",
    "uv_index",
)

DAILY_FIELDS = (
    "temperature_2m_max",
    "temperature_2m_min",
    "apparent_temperature_max",
    "apparent_temperature_min",
    "weather_code",
    "precipitation_sum",
    "precipitation_probability_max",
    "wind_speed_10m_max",
    "wind_direction_10m_dominant",
    "sunrise",
    "sunset",
    "uv_index_max",
)

AQ_FIELDS = (
    "pm2_5",
    "pm10",
    "carbon_monoxide",
    "nitrogen_dioxide",
    "sulphur_dioxide",
    "ozone",
    "us_aqi",
    "european_aqi",
)


class OpenMeteoApiError(Exception):
    """Raised when a required Open-Meteo request cannot be completed."""


class OpenMeteoClient:
    """Small async client with bounded retries and no integration state."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._session = async_get_clientsession(hass)
        self._headers = {"User-Agent": HTTP_USER_AGENT}

    async def _request_json(
        self,
        url: str,
        params: Mapping[str, Any],
        *,
        timeout_seconds: int = 20,
        attempts: int = 3,
    ) -> dict[str, Any]:
        last_error: Exception | None = None

        for attempt in range(attempts):
            try:
                async with self._session.get(
                    url,
                    params=params,
                    headers=self._headers,
                    timeout=aiohttp.ClientTimeout(total=timeout_seconds),
                ) as response:
                    if response.status >= 400:
                        body = await response.text()
                        error = OpenMeteoApiError(
                            f"HTTP {response.status}: {body[:160]}"
                        )
                        if response.status != 429 and response.status < 500:
                            raise error
                        last_error = error
                    else:
                        payload = await response.json()
                        if not isinstance(payload, dict):
                            raise OpenMeteoApiError("API returned a non-object response")
                        if payload.get("error"):
                            raise OpenMeteoApiError(str(payload.get("reason") or "API error"))
                        return payload
            except OpenMeteoApiError as err:
                last_error = err
                # 4xx failures are deterministic except rate limiting.
                if "HTTP 4" in str(err) and "HTTP 429" not in str(err):
                    raise
            except (aiohttp.ClientError, asyncio.TimeoutError) as err:
                last_error = err

            if attempt + 1 < attempts:
                await asyncio.sleep(1.0 * (2**attempt))

        raise OpenMeteoApiError(str(last_error or "Open-Meteo request failed"))

    async def async_weather(self, latitude: float, longitude: float) -> dict[str, Any]:
        """Fetch the weather payload needed by all v2 weather/sensor entities."""
        return await self._request_json(
            URL,
            {
                "latitude": latitude,
                "longitude": longitude,
                "current": ",".join(CURRENT_FIELDS),
                "hourly": ",".join(HOURLY_FIELDS),
                "daily": ",".join(DAILY_FIELDS),
                "temperature_unit": "celsius",
                "wind_speed_unit": "kmh",
                "precipitation_unit": "mm",
                "timezone": "auto",
                "timeformat": "iso8601",
            },
        )

    async def async_air_quality(
        self, latitude: float, longitude: float
    ) -> dict[str, Any]:
        """Fetch optional air-quality data."""
        return await self._request_json(
            AIR_QUALITY_URL,
            {
                "latitude": latitude,
                "longitude": longitude,
                "hourly": ",".join(AQ_FIELDS),
                "timezone": "auto",
            },
            attempts=2,
        )
