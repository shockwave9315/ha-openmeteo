from __future__ import annotations

import json
from pathlib import Path


COMPONENT_DIR = Path("custom_components/openmeteo")


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def test_base_strings_define_config_and_options_form_labels() -> None:
    strings = _load_json(COMPONENT_DIR / "strings.json")

    config_steps = strings["config"]["step"]
    options_steps = strings["options"]["step"]
    config_data = config_steps["details"]["data"]
    options_data = options_steps["details"]["data"]

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

    static_steps = {
        "static_source": "static_location_method",
        "static_entity": "static_location_entity",
        "static_search": "search_query",
        "static_search_result": "search_result",
    }
    for step, key in static_steps.items():
        assert key in config_steps[step]["data"]
        assert key in options_steps[step]["data"]


def test_polish_translation_covers_v2_form_labels() -> None:
    translation = _load_json(COMPONENT_DIR / "translations/pl.json")
    steps = translation["config"]["step"]
    details = steps["details"]

    assert details["data"]["entity_id"] == "Źródło lokalizacji"
    assert details["data"]["update_interval_min"] == "Odświeżanie pogody (min)"
    assert "GPS" in details["data_description"]["entity_id"]
    assert steps["static_source"]["data"]["static_location_method"] == "Sposób ustawienia lokalizacji"
    assert steps["static_entity"]["data"]["static_location_entity"] == "Osoba lub urządzenie"
    assert steps["static_search"]["data"]["search_query"] == "Miejscowość lub adres"
