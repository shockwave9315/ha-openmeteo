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
NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"


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
    """Resolve coordinates to a short place label through Nominatim."""
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


async def async_forward_geocode(
    hass: HomeAssistant, query: str, *, limit: int = 5
) -> list[dict[str, Any]]:
    """Resolve a human place/address query to a small list of WGS84 candidates."""
    query = query.strip()
    if not query:
        return []

    session = async_get_clientsession(hass)
    language = (hass.config.language or "en").strip() or "en"
    safe_limit = max(1, min(int(limit), 10))

    try:
        async with session.get(
            NOMINATIM_SEARCH_URL,
            params={
                "format": "jsonv2",
                "q": query,
                "limit": str(safe_limit),
                "addressdetails": "1",
                "accept-language": language,
            },
            headers={"User-Agent": HTTP_USER_AGENT},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as response:
            if response.status != 200:
                return []
            payload: Any = await response.json()
    except (aiohttp.ClientError, asyncio.TimeoutError, TypeError, ValueError):
        return []

    if not isinstance(payload, list):
        return []

    results: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            latitude = float(item["lat"])
            longitude = float(item["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            continue

        label = str(
            item.get("display_name")
            or item.get("name")
            or coordinate_label(latitude, longitude)
        )
        results.append(
            {
                "label": label,
                "latitude": latitude,
                "longitude": longitude,
            }
        )

    return results
