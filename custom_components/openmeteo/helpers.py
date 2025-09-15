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

from homeassistant.util import dt as dt_util

def hourly_at_now(data: dict, key: str):
    """Return hourly value for *current hour* (timezone-aware), or closest if exact not found.

    Looks into data["hourly"][key] and aligns timestamps to the provider timezone given in data["timezone"].
    First tries an exact hour match; if none, returns the nearest-hour value.
    """
    hourly = (data or {}).get("hourly", {})
    times = hourly.get("time") or []
    values = hourly.get(key) or []
    if not times or not values:
        return None

    tz = dt_util.get_time_zone((data or {}).get("timezone")) or dt_util.UTC
    now = dt_util.now(tz).replace(minute=0, second=0, microsecond=0)

    # exact match first
    for t_str, val in zip(times, values):
        try:
            dt = dt_util.parse_datetime(t_str)
            if not dt:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=tz)
            if dt.replace(minute=0, second=0, microsecond=0) == now:
                return val
        except Exception:
            continue

    # else nearest hour
    best_val = None
    best_diff = None
    for t_str, val in zip(times, values):
        try:
            dt = dt_util.parse_datetime(t_str)
            if not dt:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=tz)
            diff = abs((dt.replace(minute=0, second=0, microsecond=0) - now).total_seconds())
            if best_diff is None or diff < best_diff:
                best_diff = diff
                best_val = val
        except Exception:
            continue
    return best_val
