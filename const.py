# SPDX-License-Identifier: Apache-2.0
"""Constants for Open-Meteo integration."""
from __future__ import annotations

from homeassistant.components.weather import (
    ATTR_CONDITION_CLEAR_NIGHT,
    ATTR_CONDITION_CLOUDY,
    ATTR_CONDITION_FOG,
    ATTR_CONDITION_LIGHTNING_RAINY,
    ATTR_CONDITION_PARTLYCLOUDY,
    ATTR_CONDITION_POURING,
    ATTR_CONDITION_RAINY,
    ATTR_CONDITION_SNOWY,
    ATTR_CONDITION_SNOWY_RAINY,
    ATTR_CONDITION_SUNNY,
)

DOMAIN = "openmeteo"
ATTRIBUTION = "Weather data provided by Open-Meteo"
MANUFACTURER = "Open-Meteo"

CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_MODE = "mode"
CONF_ENTITY_ID = "entity_id"
CONF_TRACKED_ENTITY_ID = "tracked_entity_id"
CONF_MIN_TRACK_INTERVAL = "min_track_interval"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_UNITS = "units"
CONF_USE_PLACE_AS_DEVICE_NAME = "use_place_as_device_name"
CONF_SHOW_PLACE_NAME = "show_place_name"

MODE_STATIC = "static"
MODE_TRACK = "track"

DEFAULT_UPDATE_INTERVAL = 60
DEFAULT_MIN_TRACK_INTERVAL = 15
DEFAULT_UNITS = "metric"
DEFAULT_USE_PLACE_AS_DEVICE_NAME = False
DEFAULT_SHOW_PLACE_NAME = True

DEFAULT_DAILY_VARIABLES = [
    "sunrise",
    "sunset",
    "temperature_2m_max",
    "temperature_2m_min",
    "weathercode",
    "precipitation_sum",
    "precipitation_probability_max",
    "wind_speed_10m_max",
    "wind_direction_10m_dominant",
]

DEFAULT_HOURLY_VARIABLES = [
    "temperature_2m",
    "relative_humidity_2m",
    "dewpoint_2m",
    "precipitation",
    "snowfall",
    "precipitation_probability",
    "weathercode",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "pressure_msl",
    "visibility",
    "is_day",
    "apparent_temperature",
    "uv_index",
]

URL = "https://api.open-meteo.com/v1/forecast"

PLATFORMS = ["weather", "sensor"]

CONDITION_MAP = {
    0: ATTR_CONDITION_SUNNY,
    1: ATTR_CONDITION_PARTLYCLOUDY,
    2: ATTR_CONDITION_PARTLYCLOUDY,
    3: ATTR_CONDITION_CLOUDY,
    45: ATTR_CONDITION_FOG,
    48: ATTR_CONDITION_FOG,
    51: ATTR_CONDITION_RAINY,
    53: ATTR_CONDITION_RAINY,
    55: ATTR_CONDITION_POURING,
    56: ATTR_CONDITION_SNOWY_RAINY,
    57: ATTR_CONDITION_SNOWY_RAINY,
    61: ATTR_CONDITION_RAINY,
    63: ATTR_CONDITION_RAINY,
    65: ATTR_CONDITION_POURING,
    66: ATTR_CONDITION_SNOWY_RAINY,
    67: ATTR_CONDITION_SNOWY_RAINY,
    71: ATTR_CONDITION_SNOWY,
    73: ATTR_CONDITION_SNOWY,
    75: ATTR_CONDITION_SNOWY,
    77: ATTR_CONDITION_SNOWY,
    80: ATTR_CONDITION_RAINY,
    81: ATTR_CONDITION_RAINY,
    82: ATTR_CONDITION_POURING,
    85: ATTR_CONDITION_SNOWY,
    86: ATTR_CONDITION_SNOWY,
    95: ATTR_CONDITION_LIGHTNING_RAINY,
    96: ATTR_CONDITION_LIGHTNING_RAINY,
    99: ATTR_CONDITION_LIGHTNING_RAINY,
}
