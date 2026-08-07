from __future__ import annotations

from homeassistant.const import UnitOfRatio

from custom_components.openmeteo.coordinator import HOURLY_FIELDS
from custom_components.openmeteo.sensor import SENSORS


def test_uses_current_open_meteo_dew_point_field() -> None:
    assert "dew_point_2m" in HOURLY_FIELDS
    assert "dewpoint_2m" not in HOURLY_FIELDS


def test_carbon_monoxide_uses_current_home_assistant_ppm_unit() -> None:
    assert SENSORS["co"].native_unit_of_measurement == UnitOfRatio.PARTS_PER_MILLION


def test_location_sensor_reports_place_not_coordinate_string() -> None:
    data = {
        "location_name": "Dortmund, DE",
        "location": {"latitude": 51.51, "longitude": 7.46},
        "last_location_update": "2026-08-07T05:40:00+00:00",
        "mode": "track",
    }
    description = SENSORS["location"]
    assert description.value_fn(data) == "Dortmund, DE"
    attrs = description.attributes_fn(data)
    assert attrs["latitude"] == 51.51
    assert attrs["longitude"] == 7.46
