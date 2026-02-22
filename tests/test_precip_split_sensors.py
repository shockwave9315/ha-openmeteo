def test_precipitation_split_current_hour_values():
    from custom_components.openmeteo.sensor import SENSOR_TYPES

    data = {
        "hourly": {
            "time": ["2024-01-01T12:00"],
            "precipitation": [3.2],
            "rain": [2.0],
            "snowfall": [1.2],
        }
    }

    assert SENSOR_TYPES["precipitation_sum"].value_fn(data) == 4.4
    assert SENSOR_TYPES["rain_current_hour"].value_fn(data) == 2.0
    assert SENSOR_TYPES["snow_current_hour"].value_fn(data) == 1.2


def test_no_legacy_generation_sensors_present():
    from custom_components.openmeteo.sensor import SENSOR_TYPES

    for key in SENSOR_TYPES:
        assert not key.startswith("p" + "v_")
