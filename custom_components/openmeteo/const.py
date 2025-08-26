# SPDX-License-Identifier: Apache-2.0
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
    ATTR_CONDITION_SNOWY_RAINY,
    ATTR_CONDITION_SNOWY,
    ATTR_CONDITION_SUNNY,
)

# Basic metadata
DOMAIN = "openmeteo"
ATTRIBUTION = "Weather data provided by Open-Meteo"
MANUFACTURER = "Open-Meteo"
NAME = "Open-Meteo"

"""Configuration keys and defaults."""
CONF_NAME = "name"
CONF_DAILY_VARIABLES = "daily_variables"
CONF_HOURLY_VARIABLES = "hourly_variables"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_ALTITUDE = "altitude"
CONF_TIME_ZONE = "time_zone"
CONF_SCAN_INTERVAL = "scan_interval"
# New options for dynamic tracking
CONF_MODE = "mode"
CONF_ENTITY_ID = "entity_id"
CONF_MIN_TRACK_INTERVAL = "min_track_interval"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_UNITS = "units"
CONF_API_PROVIDER = "api_provider"
CONF_API_KEY = "api_key"
CONF_AREA_NAME_OVERRIDE = "area_name_override"
CONF_UV_INDEX = "uv_index"
CONF_USE_PLACE_AS_DEVICE_NAME = "use_place_as_device_name"
CONF_SHOW_PLACE_NAME = "show_place_name"
CONF_GEOCODE_INTERVAL_MIN = "geocode_interval_min"
CONF_GEOCODE_MIN_DISTANCE_M = "geocode_min_distance_m"
CONF_GEOCODER_PROVIDER = "geocoder_provider"
CONF_EXTRA_SENSORS = "extra_sensors"

# Modes
MODE_STATIC = "static"
MODE_TRACK = "track"

# Legacy keys for backward compatibility
CONF_TRACKING_MODE = "tracking_mode"
CONF_TRACKED_ENTITY_ID = "tracked_entity_id"
TRACKING_MODE_FIXED = "fixed"
TRACKING_MODE_DEVICE = "device"

# Default values
DEFAULT_NAME = "Open-Meteo"
# Default update interval in seconds. Historical configs may use scan_interval.
DEFAULT_SCAN_INTERVAL = 600
DEFAULT_UPDATE_INTERVAL = DEFAULT_SCAN_INTERVAL
DEFAULT_MIN_TRACK_INTERVAL = 15  # minutes
DEFAULT_UNITS = "metric"
DEFAULT_API_PROVIDER = "open_meteo"
DEFAULT_USE_PLACE_AS_DEVICE_NAME = True
DEFAULT_SHOW_PLACE_NAME = True
DEFAULT_GEOCODE_INTERVAL_MIN = 120
DEFAULT_GEOCODE_MIN_DISTANCE_M = 500
DEFAULT_GEOCODER_PROVIDER = "osm_nominatim"
DEFAULT_EXTRA_SENSORS = False

DEFAULT_DAILY_VARIABLES = [
    "temperature_2m_max",
    "temperature_2m_min",
    "weathercode",
    "precipitation_sum",
    "wind_speed_10m_max",
    "wind_direction_10m_dominant",
    "sunrise",
    "sunset",
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
    "cloud_cover",
    "is_day",
    "apparent_temperature",
    "uv_index",
]

# API
URL = "https://api.open-meteo.com/v1/forecast"
API_URL = URL  # alias dla starszych importów

# Platforms
PLATFORMS = ["weather", "sensor"]

# Weather code → HA condition mapping
CONDITION_MAP = {
    0: ATTR_CONDITION_SUNNY,  # Clear sky
    1: ATTR_CONDITION_PARTLYCLOUDY,  # Mainly clear
    2: ATTR_CONDITION_PARTLYCLOUDY,  # Partly cloudy
    3: ATTR_CONDITION_CLOUDY,  # Overcast
    45: ATTR_CONDITION_FOG,  # Fog
    48: ATTR_CONDITION_FOG,  # Depositing rime fog
    51: ATTR_CONDITION_RAINY,  # Light drizzle
    53: ATTR_CONDITION_RAINY,  # Moderate drizzle
    55: ATTR_CONDITION_POURING,  # Dense drizzle
    56: ATTR_CONDITION_SNOWY_RAINY,  # Light freezing drizzle
    57: ATTR_CONDITION_SNOWY_RAINY,  # Dense freezing drizzle
    61: ATTR_CONDITION_RAINY,  # Slight rain
    63: ATTR_CONDITION_RAINY,  # Moderate rain
    65: ATTR_CONDITION_POURING,  # Heavy rain
    66: ATTR_CONDITION_SNOWY_RAINY,  # Light freezing rain
    67: ATTR_CONDITION_SNOWY_RAINY,  # Heavy freezing rain
    71: ATTR_CONDITION_SNOWY,  # Slight snow fall
    73: ATTR_CONDITION_SNOWY,  # Moderate snow fall
    75: ATTR_CONDITION_SNOWY,  # Heavy snow fall
    77: ATTR_CONDITION_SNOWY,  # Snow grains
    80: ATTR_CONDITION_RAINY,  # Slight rain showers
    81: ATTR_CONDITION_RAINY,  # Moderate rain showers
    82: ATTR_CONDITION_POURING,  # Violent rain showers
    85: ATTR_CONDITION_SNOWY,  # Slight snow showers
    86: ATTR_CONDITION_SNOWY,  # Heavy snow showers
    95: ATTR_CONDITION_LIGHTNING_RAINY,  # Thunderstorm
    96: ATTR_CONDITION_LIGHTNING_RAINY,  # Thunderstorm with slight hail
    99: ATTR_CONDITION_LIGHTNING_RAINY,  # Thunderstorm with heavy hail
}
