# SPDX-License-Identifier: Apache-2.0
"""Helper utilities for Open-Meteo integration."""
from __future__ import annotations

from typing import Any, Iterable, Optional, Sequence

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import async_timeout
import math

from .const import DOMAIN, HTTP_USER_AGENT


async def maybe_update_device_name(
    hass: HomeAssistant, config_entry: ConfigEntry, new_name: Optional[str]
) -> None:
    """Set device name to `new_name` if user didn't override it.
    - Finds device by identifiers {(DOMAIN, entry_id)}.
    - If user set name_by_user -> keep it.
    - Update only if device exists and name differs.
    """
    if not new_name:
        return

    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_device(identifiers={(DOMAIN, config_entry.entry_id)})
    if not device:
        return
    if device.name_by_user:
        return
    if device.name == new_name:
        return

    dev_reg.async_update_device(device_id=device.id, name=new_name)


def _parse_hour(ts: str, tz) -> Optional[dt_util.dt.datetime]:
    """Parse an ISO8601 string into a timezone-aware hour-aligned datetime."""
    try:
        dt = dt_util.parse_datetime(ts)
        if not dt:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        # Align to full hour
        return dt.replace(minute=0, second=0, microsecond=0)
    
    except Exception:
        return None

# --- Simple in-memory cache for reverse postcodes (rounded 3 decimals) ---
_postcode_cache: dict[tuple[float, float], str] = {}


def _pcache_key(lat: float, lon: float) -> tuple[float, float]:
    return (round(float(lat), 3), round(float(lon), 3))


async def async_reverse_postcode_cached(
    hass: HomeAssistant,
    lat: float,
    lon: float,
    *,
    language: str | None = None,
) -> str | None:
    """Cached reverse postcode with fallbacks on Nominatim zoom levels."""
    try:
        key = _pcache_key(lat, lon)
    except Exception:
        key = None
    if key and key in _postcode_cache:
        return _postcode_cache[key]

    # Try default zoom
    pc = await async_reverse_postcode(hass, lat, lon, language=language)
    # Try fallbacks if needed
    if not pc:
        for z in (14, 10):
            try:
                pc = await async_reverse_postcode(hass, lat, lon, language=language, zoom=z)
            except Exception:
                pc = None
            if pc:
                break
    if key and pc:
        _postcode_cache[key] = pc
    return pc


async def async_reverse_postcode(
    hass: HomeAssistant,
    lat: float,
    lon: float,
    *,
    language: str | None = None,
    zoom: int | None = None,
) -> str | None:
    """Reverse geocode a postal code using Nominatim (no API key).

    Returns a postal code string or None.
    """
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except Exception:
        return None

    lang = (language or getattr(hass.config, "language", None) or "en").lower()
    url = "https://nominatim.openstreetmap.org/reverse"
    params = {
        "lat": f"{lat_f:.6f}",
        "lon": f"{lon_f:.6f}",
        "format": "json",
        "addressdetails": 1,
        "accept-language": lang,
    }
    if isinstance(zoom, int):
        params["zoom"] = zoom
    headers = {"User-Agent": HTTP_USER_AGENT}

    session = async_get_clientsession(hass)
    try:
        async with async_timeout.timeout(10):
            resp = await session.get(url, params=params, headers=headers)
            if resp.status != 200:
                return None
            data = await resp.json()
    except Exception:
        return None

    try:
        addr = (data or {}).get("address") or {}
        pc = addr.get("postcode")
        if isinstance(pc, str) and pc.strip():
            return pc.strip()
    except Exception:
        pass
    return None


async def async_reverse_postcode_info(
    hass: HomeAssistant,
    lat: float,
    lon: float,
    *,
    language: str | None = None,
    zoom: int | None = None,
) -> dict[str, Any] | None:
    """Reverse geocode to obtain postcode and state/admin1.

    Returns {"postcode": str|None, "state": str|None} or None on error.
    """
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except Exception:
        return None

    lang = (language or getattr(hass.config, "language", None) or "en").lower()
    url = "https://nominatim.openstreetmap.org/reverse"
    params = {
        "lat": f"{lat_f:.6f}",
        "lon": f"{lon_f:.6f}",
        "format": "json",
        "addressdetails": 1,
        "accept-language": lang,
    }
    if isinstance(zoom, int):
        params["zoom"] = zoom
    headers = {"User-Agent": HTTP_USER_AGENT}

    session = async_get_clientsession(hass)
    try:
        async with async_timeout.timeout(10):
            resp = await session.get(url, params=params, headers=headers)
            if resp.status != 200:
                return None
            data = await resp.json()
    except Exception:
        return None

    addr = (data or {}).get("address") or {}
    return {
        "postcode": (addr.get("postcode") or None),
        "state": (addr.get("state") or addr.get("county") or None),
    }


async def async_reverse_postcode_info_cached(
    hass: HomeAssistant,
    lat: float,
    lon: float,
    *,
    language: str | None = None,
) -> dict[str, Any] | None:
    """Cached reverse postcode+state with zoom fallbacks."""
    try:
        key = _pcache_key(lat, lon)
    except Exception:
        key = None

    # Reuse postcode cache if present
    if key and key in _postcode_cache:
        return {"postcode": _postcode_cache[key], "state": None}

    info = await async_reverse_postcode_info(hass, lat, lon, language=language)
    if not (info and info.get("postcode")):
        for z in (14, 10):
            info = await async_reverse_postcode_info(hass, lat, lon, language=language, zoom=z)
            if info and info.get("postcode"):
                break
    if key and info and info.get("postcode"):
        _postcode_cache[key] = str(info["postcode"])  # populate postcode cache too
    return info


async def async_best_effort_postcode_cached(
    hass: HomeAssistant,
    lat: float,
    lon: float,
    *,
    language: str | None = None,
) -> tuple[str | None, bool]:
    """Try to get the most appropriate postcode for given coords.

    Strategy:
    - First, get postcode at the exact point (cached).
    - If missing, probe a few nearby offsets and choose the most frequent postcode.
    - Uses cached reverse lookups internally to minimize requests.
    """
    # 1) Center point
    info = await async_reverse_postcode_info_cached(hass, lat, lon, language=language)
    if info and isinstance(info.get("postcode"), str) and info["postcode"].strip():
        return str(info["postcode"]).strip(), False

    # 2) Probe small neighborhood (approx 400–700 m offsets)
    offsets = [(0.004, 0.0), (-0.004, 0.0), (0.0, 0.006), (0.0, -0.006)]
    seen: dict[str, int] = {}
    for dlat, dlon in offsets:
        probe = await async_reverse_postcode_info_cached(
            hass, float(lat) + dlat, float(lon) + dlon, language=language
        )
        pc = (probe or {}).get("postcode")
        if isinstance(pc, str) and pc.strip():
            k = pc.strip()
            seen[k] = seen.get(k, 0) + 1

    if not seen:
        return None, False
    # return the postcode with highest frequency (mode)
    return max(seen.items(), key=lambda kv: kv[1])[0], True


async def async_prefer_user_zip_postcode(
    hass: HomeAssistant,
    lat: float,
    lon: float,
    *,
    country_code: str | None,
    postal_code: str | None,
    language: str | None = None,
    max_distance_km: float = 15.0,
) -> tuple[str | None, bool]:
    """Prefer user's postal code when it's geographically close; otherwise best-effort.

    Returns (postcode, approx_flag). approx_flag is True when the result is inferred
    (either user ZIP preference or best-effort neighborhood), False when it comes
    from the exact point reverse geocode.
    """
    try:
        latf = float(lat)
        lonf = float(lon)
    except Exception:
        return None, False

    # If we have a user ZIP and country, check proximity
    cc = (country_code or "").strip().upper()
    pc_in = (postal_code or "").strip()
    if cc and pc_in:
        center = await async_zip_to_coords(hass, cc, pc_in)
        if center is not None:
            zlat, zlon = center
            try:
                dist = haversine_km(latf, lonf, float(zlat), float(zlon))
            except Exception:
                dist = None
            if dist is not None and dist <= max_distance_km:
                # Close enough: prefer user's ZIP, mark as approx
                return pc_in, True

    # Otherwise, use best-effort postcode around the point
    return await async_best_effort_postcode_cached(hass, latf, lonf, language=language)


def hourly_index_at_now(data: dict) -> Optional[int]:
    """Return the index in hourly['time'] that matches the current hour (exact or nearest)."""
    if not isinstance(data, dict):
        return None

    hourly = (data.get("hourly") or {})
    times: Iterable[str] = hourly.get("time") or []
    if not times:
        return None

    tz = dt_util.get_time_zone(data.get("timezone")) or dt_util.UTC
    now = dt_util.now(tz).replace(minute=0, second=0, microsecond=0)

    best_idx = None
    best_diff = None

    for idx, t in enumerate(times):
        dt_hr = _parse_hour(t, tz)
        if dt_hr is None:
            continue
        if dt_hr == now:
            return idx
        diff = abs((dt_hr - now).total_seconds())
        if best_diff is None or diff < best_diff:
            best_diff = diff
            best_idx = idx

    return best_idx


def hourly_at_now(data: dict, key: str) -> Any:
    """Return hourly[key] value for the hour closest to 'now' (respects timezone)."""
    if not isinstance(data, dict):
        return None

    hourly = (data.get("hourly") or {})
    values: Iterable[Any] = hourly.get(key) or []
    if not values:
        return None

    idx = hourly_index_at_now(data)
    if idx is None:
        return None

    values_list = list(values)
    if 0 <= idx < len(values_list):
        return values_list[idx]
    return None


def hourly_sum_last_n(data: dict, keys: Sequence[str], n_hours: int) -> Optional[float]:
    """Sum last N hours for given hourly keys (e.g., ['precipitation','snowfall']).
    Includes the current hour (closest to 'now'). Ignores non-numeric entries.
    """
    if not isinstance(data, dict) or not isinstance(n_hours, int) or n_hours <= 0:
        return None

    hourly = (data.get("hourly") or {})
    times = hourly.get("time") or []
    if not times:
        return None

    idx = hourly_index_at_now(data)
    if idx is None:
        return None

    start = max(0, idx - (n_hours - 1))
    total = 0.0
    found = False

    for i in range(start, idx + 1):
        for key in keys:
            arr = hourly.get(key) or []
            if i < len(arr):
                val = arr[i]
                if isinstance(val, (int, float)):
                    total += float(val)
                    found = True

    return round(total, 2) if found else None


def extra_attrs(data: dict) -> dict[str, Any]:
    """Build extra attributes for sensors from API payload (safe, minimal)."""
    attrs: dict[str, Any] = {}
    try:
        loc = data.get("location") or {}
        tz = data.get("timezone")
        if tz:
            attrs["timezone"] = tz
        lat = loc.get("latitude") or data.get("latitude")
        lon = loc.get("longitude") or data.get("longitude")
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            attrs["latitude"] = round(float(lat), 5)
            attrs["longitude"] = round(float(lon), 5)
        elev = (data.get("elevation") or loc.get("elevation"))
        if isinstance(elev, (int, float)):
            attrs["elevation"] = elev
    except Exception:
        # be resilient; attributes are optional
        pass
    return attrs


async def async_forward_geocode(
    hass: HomeAssistant,
    name: str,
    *,
    count: int = 10,
) -> list[dict[str, Any]]:
    """Query Open-Meteo Geocoding API for a place name (forward geocoding).

    Returns a simplified list of results with keys:
    - name, admin1, admin2, country_code, latitude, longitude
    """

    if not name or not isinstance(name, str):
        return []

    lang = (getattr(hass.config, "language", None) or "en").lower()
    url = "https://geocoding-api.open-meteo.com/v1/search"
    params = {
        "name": name,
        "count": max(1, min(int(count), 50)),
        "language": lang,
        "format": "json",
    }

    session = async_get_clientsession(hass)
    try:
        async with async_timeout.timeout(10):
            resp = await session.get(url, params=params)
            if resp.status != 200:
                return []
            data = await resp.json()
    except Exception:
        return []

    results = []
    for r in (data or {}).get("results", []) or []:
        try:
            results.append(
                {
                    "name": r.get("name"),
                    "admin1": r.get("admin1"),
                    "admin2": r.get("admin2"),
                    "country_code": r.get("country_code"),
                    "latitude": r.get("latitude"),
                    "longitude": r.get("longitude"),
                }
            )
        except Exception:
            continue

    return results


def _deg2rad(x: float) -> float:
    return x * math.pi / 180.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance (km) between two WGS84 points (approx)."""
    R = 6371.0
    dlat = _deg2rad(lat2 - lat1)
    dlon = _deg2rad(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(_deg2rad(lat1)) * math.cos(_deg2rad(lat2)) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


async def async_zip_to_coords(
    hass: HomeAssistant,
    country_code: str,
    postal_code: str,
) -> tuple[float, float] | None:
    """Resolve postal code to approximate coordinates using zippopotam.us.

    Returns (lat, lon) or None.
    """
    if not country_code or not postal_code:
        return None

    cc = country_code.strip().upper()
    zip_clean = postal_code.strip().replace(" ", "")

    url = f"https://api.zippopotam.us/{cc}/{zip_clean}"
    session = async_get_clientsession(hass)
    try:
        async with async_timeout.timeout(10):
            resp = await session.get(url)
            if resp.status != 200:
                return None
            data = await resp.json()
    except Exception:
        return None

    places = (data or {}).get("places") or []
    if not places:
        return None
    try:
        # take first place center
        lat = float(places[0].get("latitude"))
        lon = float(places[0].get("longitude"))
        return (lat, lon)
    except Exception:
        return None


def format_postal(country_code: str | None, postal: str | None) -> str | None:
    """Format postal code nicely depending on country.

    - PL: enforce NN-NNN
    - others: return as-is (stripped) if non-empty
    """
    if not country_code or not postal:
        return postal.strip() if postal else None

    country = (country_code or "").upper()
    pc = postal.strip()

    if country == "PL" and len(pc) >= 5:
        # PL: ensure NN-NNN format (e.g., 00-001)
        pc = pc.replace("-", "")
        if len(pc) >= 5:
            return f"{pc[:2]}-{pc[2:5]}"
    return pc


def aq_hour_value(data: dict, key: str) -> Any:
    """Get air quality value for the current hour from the data structure.

    Args:
        data: The data dictionary containing 'aq' key with 'hourly' data
        key: The air quality key to retrieve (e.g., 'pm2_5', 'pm10')

    Returns:
        The value for the current hour, or None if not available
    """
    aq = (data or {}).get("aq") or {}
    hourly = aq.get("hourly") or {}
    times = hourly.get("time") or []

    # Use the same timezone and hour calculation as the main data
    idx = hourly_index_at_now({"hourly": {"time": times}, "timezone": data.get("timezone")})
    if idx is None:
        return None

    values = hourly.get(key)
    if not values or not isinstance(values, (list, tuple)) or idx >= len(values):
        return None

    return values[idx]
