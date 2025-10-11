"""Constants for Open-Meteo integration."""
from __future__ import annotations

from typing import Final

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

# HTTP
HTTP_USER_AGENT = "ha-openmeteo/1.6.0-alpha (https://github.com/shockwave9315/ha-openmeteo)"

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
# New: update interval expressed in minutes (UI)
CONF_UPDATE_INTERVAL_MIN = "update_interval_min"
# Backward-compat: legacy seconds key
CONF_UPDATE_INTERVAL = "update_interval"
CONF_UNITS = "units"
CONF_API_PROVIDER = "api_provider"
CONF_API_KEY = "api_key"
CONF_AREA_NAME_OVERRIDE = "area_name_override"
# Cooldowns
CONF_REVERSE_GEOCODE_COOLDOWN_MIN = "reverse_geocode_cooldown_min"
# New: express options save cooldown in minutes (UI shows minutes)
CONF_OPTIONS_SAVE_COOLDOWN_MIN = "options_save_cooldown_min"
# Backward-compat: legacy seconds key (still honored if present)
CONF_OPTIONS_SAVE_COOLDOWN_SEC = "options_save_cooldown_sec"

# Modes
MODE_STATIC = "static"
MODE_TRACK = "track"

# Legacy keys for backward compatibility
CONF_TRACKING_MODE = "tracking_mode"
CONF_TRACKED_ENTITY_ID = "tracked_entity_id"
# Option: use location name as device name
CONF_USE_PLACE_AS_DEVICE_NAME = "use_place_as_device_name"
DEFAULT_USE_PLACE_AS_DEVICE_NAME = True

TRACKING_MODE_FIXED = "fixed"
TRACKING_MODE_DEVICE = "device"

# Default values
DEFAULT_NAME = "Open-Meteo"
# Default update interval in seconds. Historical configs may use scan_interval.
DEFAULT_SCAN_INTERVAL = 600
DEFAULT_UPDATE_INTERVAL = DEFAULT_SCAN_INTERVAL  # legacy seconds
DEFAULT_UPDATE_INTERVAL_MIN = DEFAULT_SCAN_INTERVAL // 60  # minutes (10)
DEFAULT_MIN_TRACK_INTERVAL = 15  # minutes
DEFAULT_UNITS = "metric"
DEFAULT_API_PROVIDER = "open_meteo"
# Defaults for cooldowns
DEFAULT_REVERSE_GEOCODE_COOLDOWN_MIN = 15  # minutes
# New default in minutes
DEFAULT_OPTIONS_SAVE_COOLDOWN_MIN = 1  # minute
# Legacy default (seconds) retained for migration/back-compat only
DEFAULT_OPTIONS_SAVE_COOLDOWN_SEC = 60  # seconds

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

# Air Quality API keys mapping
AQ_HOURLY_KEYS = {
    "pm2_5": "pm2_5",
    "pm10": "pm10",
    "co": "carbon_monoxide",
    "no2": "nitrogen_dioxide",
    "so2": "sulphur_dioxide",
    "o3": "ozone",
    "aqi_us": "us_aqi",
    "aqi_eu": "european_aqi",
}

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

# --- Sensor selection (grouped) ---
CONF_ENABLED_SENSORS = "enabled_sensors"  # legacy (single list) – do not remove (compat)
CONF_ENABLED_WEATHER_SENSORS = "enabled_weather_sensors"
CONF_ENABLED_AQ_SENSORS = "enabled_aq_sensors"

ALL_SENSOR_KEYS = [
    "temperature",
    "apparent_temperature",
    "humidity",
    "pressure",
    "dew_point",
    "wind_speed",
    "wind_gust",
    "wind_bearing",
    "precipitation_sum",
    "precipitation_daily_sum",
    "precipitation_last_3h",
    "precipitation_probability",
    "visibility",
    "sunrise",
    "sunset",
    "uv_index",
    "uv_index_max",
    "location",
    "pm2_5",
    "pm10",
    "co",
    "no2",
    "so2",
    "o3",
    "aqi_us",
    "aqi_eu",
]

WEATHER_SENSOR_KEYS = [
    "temperature",
    "apparent_temperature",
    "humidity",
    "pressure",
    "dew_point",
    "wind_speed",
    "wind_gust",
    "wind_bearing",
    "precipitation_sum",
    "precipitation_daily_sum",
    "precipitation_last_3h",
    "precipitation_probability",
    "visibility",
    "sunrise",
    "sunset",
    "uv_index",
    "uv_index_max",
    "location",
]

AQ_SENSOR_KEYS = [
    "pm2_5",
    "pm10",
    "co",
    "no2",
    "so2",
    "o3",
    "aqi_us",
    "aqi_eu",
]

SENSOR_LABELS = {
    "temperature": {"pl": "Temperatura", "en": "Temperature"},
    "apparent_temperature": {"pl": "Temp. odczuwalna", "en": "Apparent temperature"},
    "humidity": {"pl": "Wilgotność", "en": "Humidity"},
    "pressure": {"pl": "Ciśnienie", "en": "Pressure"},
    "dew_point": {"pl": "Punkt rosy", "en": "Dew point"},
    "wind_speed": {"pl": "Prędkość wiatru", "en": "Wind speed"},
    "wind_gust": {"pl": "Porywy wiatru", "en": "Wind gust"},
    "wind_bearing": {"pl": "Kierunek wiatru", "en": "Wind bearing"},
    "precipitation_sum": {"pl": "Opad (bieżąca godzina)", "en": "Precipitation (this hour)"},
    "precipitation_daily_sum": {
        "pl": "Suma opadów (dzienna)",
        "en": "Precipitation (daily sum)",
    },
    "precipitation_last_3h": {
        "pl": "Opad (ostatnie 3h)",
        "en": "Precipitation (last 3h)",
    },
    "precipitation_probability": {
        "pl": "Prawdopodobieństwo opadów",
        "en": "Precipitation probability",
    },
    "visibility": {"pl": "Widzialność", "en": "Visibility"},
    "sunrise": {"pl": "Wschód słońca", "en": "Sunrise"},
    "sunset": {"pl": "Zachód słońca", "en": "Sunset"},
    "uv_index": {"pl": "UV index", "en": "UV index"},
    "uv_index_max": {"pl": "UV index (max)", "en": "UV index (max)"},
    "pm2_5": {"pl": "PM2.5", "en": "PM2.5"},
    "pm10": {"pl": "PM10", "en": "PM10"},
    "co": {"pl": "Tlenek węgla (CO)", "en": "Carbon monoxide (CO)"},
    "no2": {"pl": "Dwutlenek azotu (NO₂)", "en": "Nitrogen dioxide (NO₂)"},
    "so2": {"pl": "Dwutlenek siarki (SO₂)", "en": "Sulphur dioxide (SO₂)"},
    "o3": {"pl": "Ozon (O₃)", "en": "Ozone (O₃)"},
    "aqi_us": {"pl": "US AQI", "en": "US AQI"},
    "aqi_eu": {"pl": "EU AQI", "en": "EU AQI"},
    "location": {"pl": "Lokalizacja (lat,lon)", "en": "Location (lat,lon)"},
}

CONF_SELECT_ALL_WEATHER: Final = "select_all_weather"
CONF_SELECT_ALL_AQ: Final = "select_all_aq"
