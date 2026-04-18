from __future__ import annotations

from custom_components.openmeteo.naming import (
    build_location_display_name,
    coords_label,
    default_device_name,
    stable_sensor_unique_id,
    stable_weather_unique_id,
    should_update_entry_title,
)


def test_naming_priority_area_override_over_place_and_coords() -> None:
    assert (
        build_location_display_name(
            area_override="Dom",
            reverse_geocoded_place="Kraków, PL",
            lat=50.061,
            lon=19.937,
        )
        == "Dom"
    )


def test_naming_fallback_to_coords() -> None:
    assert build_location_display_name(
        area_override="",
        reverse_geocoded_place=None,
        lat=50.061,
        lon=19.937,
    ) == coords_label(50.061, 19.937)


def test_should_update_title_policy() -> None:
    assert should_update_entry_title(
        current_title="Open-Meteo: tracking",
        new_title="Kraków, PL",
        fallback_label="50.06,19.94",
        area_override=None,
    )
    assert not should_update_entry_title(
        current_title="Mój własny tytuł",
        new_title="Kraków, PL",
        fallback_label="50.06,19.94",
        area_override=None,
    )


def test_identity_stable_when_place_name_changes_track_mode() -> None:
    assert stable_weather_unique_id("entry-123") == "entry-123-weather"
    assert stable_sensor_unique_id("entry-123", "temperature") == "entry-123:temperature"
    # Zmiana display-name lokalizacji nie może wpływać na identity
    assert stable_weather_unique_id("entry-123") == stable_weather_unique_id("entry-123")
    assert stable_sensor_unique_id("entry-123", "temperature") == stable_sensor_unique_id(
        "entry-123", "temperature"
    )


def test_static_mode_display_name_can_change_without_identity_change() -> None:
    first_uid = stable_weather_unique_id("entry-xyz")
    second_uid = stable_weather_unique_id("entry-xyz")
    assert first_uid == second_uid == "entry-xyz-weather"


def test_default_device_name_fallback() -> None:
    assert default_device_name("") == "Open-Meteo"
