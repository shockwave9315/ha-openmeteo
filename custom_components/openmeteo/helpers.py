"""Small data helpers shared by Open-Meteo v2 entities."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util


def _parse_hour(value: Any, timezone) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = dt_util.parse_datetime(value)
    else:
        return None

    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone)
    return parsed.replace(minute=0, second=0, microsecond=0)


def _timezone_for(data: Mapping[str, Any]):
    name = data.get("timezone")
    if isinstance(name, str) and name:
        timezone = dt_util.get_time_zone(name)
        if timezone is not None:
            return timezone
    return dt_util.UTC


def hourly_index_at_now(data: Mapping[str, Any]) -> int | None:
    """Return the index of the hourly sample closest to the current local hour."""
    hourly = data.get("hourly")
    if not isinstance(hourly, Mapping):
        return None
    times = hourly.get("time")
    if not isinstance(times, (list, tuple)) or not times:
        return None

    timezone = _timezone_for(data)
    now = dt_util.now(timezone).replace(minute=0, second=0, microsecond=0)
    best_index: int | None = None
    best_difference: float | None = None

    for index, raw_time in enumerate(times):
        sample = _parse_hour(raw_time, timezone)
        if sample is None:
            continue
        if sample == now:
            return index
        difference = abs((sample - now).total_seconds())
        if best_difference is None or difference < best_difference:
            best_index = index
            best_difference = difference

    return best_index


def hourly_at_now(data: Mapping[str, Any], key: str) -> Any:
    """Return an hourly field value for the sample closest to now."""
    hourly = data.get("hourly")
    if not isinstance(hourly, Mapping):
        return None
    values = hourly.get(key)
    if not isinstance(values, (list, tuple)):
        return None
    index = hourly_index_at_now(data)
    if index is None or index >= len(values):
        return None
    return values[index]


def hourly_sum_last_n(
    data: Mapping[str, Any], keys: Sequence[str], n_hours: int
) -> float | None:
    """Sum numeric values from the current and previous N-1 hourly samples."""
    if n_hours <= 0:
        return None
    hourly = data.get("hourly")
    if not isinstance(hourly, Mapping):
        return None
    index = hourly_index_at_now(data)
    if index is None:
        return None

    start = max(0, index - n_hours + 1)
    total = 0.0
    found = False
    for sample_index in range(start, index + 1):
        for key in keys:
            values = hourly.get(key)
            if not isinstance(values, (list, tuple)) or sample_index >= len(values):
                continue
            value = values[sample_index]
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                total += float(value)
                found = True
    return round(total, 2) if found else None


def aq_hour_value(data: Mapping[str, Any], key: str) -> Any:
    """Return an air-quality value for the sample closest to now."""
    aq = data.get("aq")
    if not isinstance(aq, Mapping):
        return None
    hourly = aq.get("hourly")
    if not isinstance(hourly, Mapping):
        return None

    aq_view = {
        "timezone": aq.get("timezone") or data.get("timezone"),
        "hourly": hourly,
    }
    index = hourly_index_at_now(aq_view)
    values = hourly.get(key)
    if (
        index is None
        or not isinstance(values, (list, tuple))
        or index >= len(values)
    ):
        return None
    return values[index]
