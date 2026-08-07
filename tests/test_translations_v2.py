from __future__ import annotations

import json
from pathlib import Path


COMPONENT_DIR = Path("custom_components/openmeteo")


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def test_base_strings_define_config_and_options_form_labels() -> None:
    strings = _load_json(COMPONENT_DIR / "strings.json")

    config_data = strings["config"]["step"]["details"]["data"]
    options_data = strings["options"]["step"]["details"]["data"]

    expected = {
        "location",
        "entity_id",
        "min_track_interval",
        "update_interval_min",
        "area_name_override",
        "reverse_geocode_cooldown_min",
        "enabled_weather_sensors",
        "enabled_aq_sensors",
    }
    assert expected <= set(config_data)
    assert expected <= set(options_data)


def test_polish_translation_covers_v2_form_labels() -> None:
    translation = _load_json(COMPONENT_DIR / "translations/pl.json")
    details = translation["config"]["step"]["details"]

    assert details["data"]["entity_id"] == "Źródło lokalizacji"
    assert details["data"]["update_interval_min"] == "Odświeżanie pogody (min)"
    assert "GPS" in details["data_description"]["entity_id"]
