from __future__ import annotations

from custom_components.openmeteo.api import CURRENT_FIELDS, DAILY_FIELDS, HOURLY_FIELDS


def test_open_meteo_api_uses_current_field_names() -> None:
    assert "weather_code" in CURRENT_FIELDS
    assert "weather_code" in HOURLY_FIELDS
    assert "weather_code" in DAILY_FIELDS
    assert "weathercode" not in CURRENT_FIELDS
    assert "weathercode" not in HOURLY_FIELDS
    assert "weathercode" not in DAILY_FIELDS


def test_v2_requests_data_needed_by_exposed_sensors() -> None:
    assert "dew_point_2m" in HOURLY_FIELDS
    assert "uv_index" in HOURLY_FIELDS
    assert "uv_index_max" in DAILY_FIELDS
    assert "sunrise" in DAILY_FIELDS
    assert "sunset" in DAILY_FIELDS
