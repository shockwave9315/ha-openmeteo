"""Location primitives for Open-Meteo v2."""
from __future__ import annotations

import asyncio
import math
from typing import Any

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import HTTP_USER_AGENT

NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance between two WGS84 points."""
    radius = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def coordinate_label(latitude: float, longitude: float) -> str:
    """Return a deterministic presentation fallback."""
    return f"{latitude:.4f}, {longitude:.4f}"


async def async_reverse_geocode(
    hass: HomeAssistant, latitude: float, longitude: float
) -> str | None:
    """Resolve coordinates to a short place label through Nominatim.

    Open-Meteo's public Geocoding API is forward-geocoding only, so v2 no longer
    sends a guaranteed-to-fail request to a non-existent Open-Meteo reverse endpoint.
    """
    session = async_get_clientsession(hass)
    language = (hass.config.language or "en").strip() or "en"

    try:
        async with session.get(
            NOMINATIM_REVERSE_URL,
            params={
                "format": "jsonv2",
                "lat": str(latitude),
                "lon": str(longitude),
                "zoom": "10",
                "addressdetails": "1",
                "accept-language": language,
            },
            headers={"User-Agent": HTTP_USER_AGENT},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as response:
            if response.status != 200:
                return None
            payload: Any = await response.json()
    except (aiohttp.ClientError, asyncio.TimeoutError, TypeError, ValueError):
        return None

    if not isinstance(payload, dict):
        return None
    address = payload.get("address")
    if not isinstance(address, dict):
        address = {}

    name = (
        address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("municipality")
        or address.get("county")
        or payload.get("name")
    )
    if not name:
        return None

    country = str(address.get("country_code") or "").upper()
    return f"{name}, {country}" if country else str(name)
