from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN


async def maybe_update_device_name(hass: HomeAssistant, config_entry: ConfigEntry, new_name: str | None) -> None:
    """Ustaw nazwę urządzenia na `new_name`, jeśli użytkownik nie zmienił jej ręcznie.

    - Szukamy urządzenia po identifiers {(DOMAIN, entry_id)}.
    - Jeśli user ustawił własną nazwę (name_by_user) — nie ruszamy.
    - Aktualizujemy tylko, gdy device.name różni się od new_name.
    """
    if not new_name:
        return

    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_device(identifiers={(DOMAIN, config_entry.entry_id)})
    if not device:
        return

    # Szanujemy ręczną zmianę użytkownika
    if device.name_by_user:
        return

    if device.name != new_name:
        dev_reg.async_update_device(device_id=device.id, name=new_name)

from typing import Any, Iterable, Optional
from homeassistant.util import dt as dt_util

def _parse_hour(ts: str, tz):
    try:
        dt = dt_util.parse_datetime(ts)
        if not dt:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        return dt.replace(minute=0, second=0, microsecond=0)
    except Exception:
        return None

def hourly_at_now(data: dict, key: str):
    """Return hourly[key] value for current hour (timezone-aware), or nearest if exact missing."""
    if not isinstance(data, dict):
        return None
    hourly = (data.get("hourly") or {})
    times = hourly.get("time") or []
    values = hourly.get(key) or []
    if not times or not values:
        return None
    tz = dt_util.get_time_zone(data.get("timezone")) or dt_util.UTC
    now = dt_util.now(tz).replace(minute=0, second=0, microsecond=0)

    parsed_times = []
    exact_idx = None
    for idx, t in enumerate(times):
        dt_hr = _parse_hour(t, tz)
        parsed_times.append(dt_hr)
        if dt_hr == now:
            exact_idx = idx
            break
    if exact_idx is not None and exact_idx < len(values):
        return values[exact_idx]

    best_val = None
    best_diff = None
    for dt_hr, val in zip(parsed_times, values):
        if dt_hr is None:
            continue
        diff = abs((dt_hr - now).total_seconds())
        if best_diff is None or diff < best_diff:
            best_diff = diff
            best_val = val
    return best_val
