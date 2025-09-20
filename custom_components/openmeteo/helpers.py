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

from .const import DOMAIN


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
        "count": max(1, min(int(count), 15)),
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
