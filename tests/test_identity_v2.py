from __future__ import annotations

from custom_components.openmeteo.const import CONF_ENTITY_ID, CONF_MODE, MODE_TRACK
from custom_components.openmeteo.identity import (
    CONF_SOURCE_KEY,
    derive_source_key,
    sensor_object_id,
    sensor_unique_id,
    weather_object_id,
    weather_unique_id,
)


def test_tracking_identity_never_depends_on_current_city() -> None:
    data = {CONF_MODE: MODE_TRACK, CONF_ENTITY_ID: "device_tracker.poco_x8"}

    first = derive_source_key(entry_id="abc123", title="Lotte, DE", data=data)
    second = derive_source_key(entry_id="abc123", title="Dortmund, DE", data=data)

    assert first == second == "poco_x8"
    assert weather_object_id(first) == "open_meteo_poco_x8"
    assert sensor_object_id(first, "temperatura") == "open_meteo_poco_x8_temperatura"


def test_persisted_source_key_wins_over_every_display_change() -> None:
    data = {
        CONF_MODE: MODE_TRACK,
        CONF_ENTITY_ID: "device_tracker.other_phone",
        CONF_SOURCE_KEY: "my_mobile_source",
    }
    assert (
        derive_source_key(entry_id="abc123", title="Berlin, DE", data=data)
        == "my_mobile_source"
    )


def test_unique_ids_are_entry_scoped_and_location_free() -> None:
    assert weather_unique_id("entry-1") == "entry-1:weather"
    assert sensor_unique_id("entry-1", "temperature") == "entry-1:temperature"
