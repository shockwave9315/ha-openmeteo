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
ATTRIBUTION = "Weather data provided by Open-Meteo"
MANUFACTURER = "Open-Meteo"
NAME = "Open-Meteo"

# Configuration keys
CONF_NAME = "name"
CONF_DAILY_VARIABLES = "daily_variables"
CONF_HOURLY_VARIABLES = "hourly_variables"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_ALTITUDE = "altitude"
CONF_TIME_ZONE = "time_zone"  # Uwaga: w pliku __init__.py jest używane CONF_TIME_ZONE
CONF_SCAN_INTERVAL = "scan_interval"
# Default values
# Default values
DEFAULT_NAME = "Open-Meteo"  # Dodaj tę linię
DEFAULT_SCAN_INTERVAL = 600  # 10 minutes

DEFAULT_DAILY_VARIABLES = [
    "temperature_2m_max",
    "temperature_2m_min",
    "weathercode",
    "precipitation_sum",
    "windspeed_10m_max",
    "winddirection_10m_dominant",
]

DEFAULT_HOURLY_VARIABLES = [
    "temperature_2m",
    "relativehumidity_2m",
    "apparent_temperature",
    "apparent_temperature",
    "precipitation",
    "snowfall",
    "precipitation_probability",
    "weathercode",
    "windspeed_10m",
    "winddirection_10m",
    "windgusts_10m",
    "pressure_msl",
    "surface_pressure",
    "visibility",
    "precipitation_probability",
    "cloudcover",
    "is_day",
    "uv_index",
]

# API
URL = "https://api.open-meteo.com/v1/forecast"

# Platforms
PLATFORMS = ["weather", "sensor"]

# Weather condition mapping
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

# w pliku /custom_components/openmeteo/const.py
TRANSLATED_VARIABLES = {
    # Daily
    "temperature_2m_max": "Temperatura maksymalna",
    "temperature_2m_min": "Temperatura minimalna",
    "precipitation_sum": "Suma opadów (dzienna)",
    "windspeed_10m_max": "Maksymalna prędkość wiatru",
    "winddirection_10m_dominant": "Dominujący kierunek wiatru",
    # Hourly
    "temperature_2m": "Temperatura",
    "relativehumidity_2m": "Wilgotność",
    "apparent_temperature": "Temperatura odczuwalna",
    "precipitation": "Suma opadów (godzinowa)",
    "snowfall": "Opady śniegu",
    "weathercode": "Kod pogody",
    "windspeed_10m": "Prędkość wiatru",
    "winddirection_10m": "Kierunek wiatru",
    "windgusts_10m": "Porywy wiatru",
    "pressure_msl": "Ciśnienie (na poziomie morza)",
    "surface_pressure": "Ciśnienie (na powierzchni)",
    "visibility": "Widzialność",
    "precipitation_probability": "Prawdopodobieństwo opadów",
    "cloudcover": "Zachmurzenie",
    "is_day": "Czy jest dzień?",
    "uv_index": "Indeks UV",
}