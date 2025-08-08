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

DOMAIN = "openmeteo"
DEFAULT_NAME = "Open-Meteo"
URL = "https://api.open-meteo.com/v1/forecast"

# Konfiguracja
CONF_NAME = "name"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_TIME_ZONE = "time_zone"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_DAILY_VARIABLES = "daily_variables"
CONF_HOURLY_VARIABLES = "hourly_variables"
CONF_AREA_OVERRIDES = "area_overrides"
CONF_USE_DEVICE_NAMES = "use_device_names"
CONF_TRACK_DEVICES = "track_devices"

DEFAULT_SCAN_INTERVAL = 15  # minutes
DEFAULT_USE_DEVICE_NAMES = False

# Domyślne zmienne dzienne i godzinowe
DEFAULT_DAILY_VARIABLES = [
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "windspeed_10m_max",
    "winddirection_10m_dominant",
    "sunrise",
    "sunset",
]
DEFAULT_HOURLY_VARIABLES = [
    "temperature_2m",
    "relative_humidity_2m",
    "pressure_msl",
    "wind_speed_10m",
    "wind_gusts_10m",
    "wind_direction_10m",
    "precipitation",
    "weather_code",
    "uv_index",
    "is_day",
]

# Mapowanie kodów WMO -> warunki HA
WMO_WEATHER_TO_HA_CONDITION = {
    0: ATTR_CONDITION_SUNNY,  # Clear sky
    1: ATTR_CONDITION_PARTLYCLOUDY,  # Mainly clear
    2: ATTR_CONDITION_PARTLYCLOUDY,  # Partly cloudy
    3: ATTR_CONDITION_CLOUDY,  # Overcast
    45: ATTR_CONDITION_FOG,  # Fog
    48: ATTR_CONDITION_FOG,  # Depositing rime fog
    51: ATTR_CONDITION_RAINY,  # Drizzle: Light
    53: ATTR_CONDITION_RAINY,  # Drizzle: Moderate
    55: ATTR_CONDITION_RAINY,  # Drizzle: Dense intensity
    56: ATTR_CONDITION_RAINY,  # Freezing Drizzle: Light
    57: ATTR_CONDITION_RAINY,  # Freezing Drizzle: Dense intensity
    61: ATTR_CONDITION_RAINY,  # Rain: Slight
    63: ATTR_CONDITION_RAINY,  # Rain: Moderate
    65: ATTR_CONDITION_POURING,  # Rain: Heavy intensity
    66: ATTR_CONDITION_RAINY,  # Freezing Rain: Light
    67: ATTR_CONDITION_RAINY,  # Freezing Rain: Heavy intensity
    71: ATTR_CONDITION_SNOWY,  # Snow fall: Slight
    73: ATTR_CONDITION_SNOWY,  # Snow fall: Moderate
    75: ATTR_CONDITION_SNOWY,  # Snow fall: Heavy intensity
    77: ATTR_CONDITION_SNOWY,  # Snow grains
    80: ATTR_CONDITION_RAINY,  # Rain showers: Slight
    81: ATTR_CONDITION_RAINY,  # Rain showers: Moderate
    82: ATTR_CONDITION_POURING,  # Rain showers: Violent
    85: ATTR_CONDITION_SNOWY,  # Snow showers: Slight
    86: ATTR_CONDITION_SNOWY,  # Snow showers: Heavy
    95: ATTR_CONDITION_LIGHTNING_RAINY,  # Thunderstorm
    96: ATTR_CONDITION_LIGHTNING_RAINY,  # Thunderstorm with slight hail
    99: ATTR_CONDITION_LIGHTNING_RAINY,  # Thunderstorm with heavy hail
}

# Tłumaczenia nazw zmiennych (dla multi_select w UI)
TRANSLATED_VARIABLES = {
    # Daily
    "temperature_2m_max": "Temperatura maksymalna",
    "temperature_2m_min": "Temperatura minimalna",
    "precipitation_sum": "Suma opadów (dzienna)",
    "windspeed_10m_max": "Maksymalna prędkość wiatru",
    "winddirection_10m_dominant": "Dominujący kierunek wiatru",
    "sunrise": "Wschód słońca",
    "sunset": "Zachód słońca",
    # Hourly
    "temperature_2m": "Temperatura",
    "relative_humidity_2m": "Wilgotność względna",
    "pressure_msl": "Ciśnienie (MSL)",
    "wind_speed_10m": "Prędkość wiatru",
    "wind_gusts_10m": "Porywy wiatru",
    "wind_direction_10m": "Kierunek wiatru",
    "precipitation": "Opad (godzinowy)",
    "weather_code": "Kod pogody (WMO)",
    "is_day": "Czy jest dzień?",
    "uv_index": "Indeks UV",
}

# ---- Networking options (OptionsFlow) ----
CONF_REQUEST_CONNECT_TIMEOUT = "connect_timeout"
CONF_REQUEST_TOTAL_TIMEOUT = "total_timeout"
CONF_API_MAX_RETRIES = "api_max_retries"
CONF_API_RETRY_BASE = "api_retry_base"

DEFAULT_REQUEST_CONNECT_TIMEOUT = 5
DEFAULT_REQUEST_TOTAL_TIMEOUT = 15
DEFAULT_API_MAX_RETRIES = 2
DEFAULT_API_RETRY_BASE = 1.0
