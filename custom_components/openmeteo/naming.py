"""Central naming policy for Open-Meteo entities, devices and entries."""
from __future__ import annotations

from typing import Any

from .const import CONF_AREA_NAME_OVERRIDE


def coords_label(lat: float, lon: float, *, precision: int = 2) -> str:
    """Return a deterministic coordinate fallback label."""
    return f"{lat:.{precision}f},{lon:.{precision}f}"


def stable_weather_unique_id(entry_id: str) -> str:
    """Return stable weather unique_id based only on entry_id."""
    return f"{entry_id}-weather"


def stable_sensor_unique_id(entry_id: str, sensor_key: str) -> str:
    """Return stable sensor unique_id based only on entry_id and sensor key."""
    return f"{entry_id}:{sensor_key}"


def build_location_display_name(
    *,
    area_override: str | None,
    reverse_geocoded_place: str | None,
    lat: float,
    lon: float,
) -> str:
    """Resolve display location name with one policy.

    Priority:
    1) area override,
    2) reverse-geocoded place,
    3) coordinates fallback.
    """
    override = (area_override or "").strip()
    if override:
        return override

    place = (reverse_geocoded_place or "").strip()
    if place:
        return place

    return coords_label(lat, lon)


def should_update_entry_title(
    *,
    current_title: str | None,
    new_title: str | None,
    fallback_label: str | None,
    area_override: str | None,
) -> bool:
    """Determine if config entry title should be auto-updated."""
    if not new_title:
        return False

    current = (current_title or "").strip()
    if new_title == current:
        return False

    if (area_override or "").strip():
        return True

    if not current:
        return True

    normalized = current.lower()
    if normalized.startswith("open-meteo"):
        return True

    if fallback_label and normalized == fallback_label.lower():
        return True

    return False


def default_device_name(entry_title: str | None) -> str:
    """Default registry device name for the integration device."""
    title = (entry_title or "").strip()
    return title or "Open-Meteo"


def flow_title_from_tracker(
    *,
    area_override: str | None,
    reverse_geocoded_place: str | None,
    tracker_friendly_name: str | None,
    lat: float | None,
    lon: float | None,
) -> str:
    """Build config flow title in track mode."""
    override = (area_override or "").strip()
    if override:
        return override

    if lat is not None and lon is not None:
        return build_location_display_name(
            area_override=None,
            reverse_geocoded_place=reverse_geocoded_place,
            lat=lat,
            lon=lon,
        )

    fallback = (tracker_friendly_name or "").strip() or "Śledzenie"
    return f"Open-Meteo: {fallback}"


def resolve_area_override(data: dict[str, Any]) -> str | None:
    """Read area override from merged entry data/options."""
    value = data.get(CONF_AREA_NAME_OVERRIDE)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
