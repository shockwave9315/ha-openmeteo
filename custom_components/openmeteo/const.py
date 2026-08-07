"""Constants for the Open-Meteo v2 integration."""
from __future__ import annotations

from homeassistant.components.weather import (
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
from homeassistant.const import Platform

DOMAIN = "openmeteo"
NAME = "Open-Meteo"
MANUFACTURER = "Open-Meteo"
ATTRIBUTION = "Weather data provided by Open-Meteo"
HTTP_USER_AGENT = "ha-openmeteo/2.0.2 (https://github.com/shockwave9315/ha-openmeteo)"

URL = "https://api.open-meteo.com/v1/forecast"
PLATFORMS = [Platform.WEATHER, Platform.SENSOR]

CONF_MODE = "mode"
CONF_ENTITY_ID = "entity_id"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_MIN_TRACK_INTERVAL = "min_track_interval"
CONF_UPDATE_INTERVAL_MIN = "update_interval_min"
CONF_AREA_NAME_OVERRIDE = "area_name_override"
CONF_REVERSE_GEOCODE_COOLDOWN_MIN = "reverse_geocode_cooldown_min"
CONF_ENABLED_WEATHER_SENSORS = "enabled_weather_sensors"
CONF_ENABLED_AQ_SENSORS = "enabled_aq_sensors"

MODE_STATIC = "static"
MODE_TRACK = "track"

DEFAULT_UPDATE_INTERVAL = 600
DEFAULT_MIN_TRACK_INTERVAL = 15
DEFAULT_REVERSE_GEOCODE_COOLDOWN_MIN = 15

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

WEATHER_SENSOR_KEYS = [
    "temperature",
    "apparent_temperature",
    "humidity",
    "pressure",
    "dew_point",
    "wind_speed",
    "wind_gust",
    "wind_bearing",
    "precipitation_probability",
    "visibility",
    "precipitation_sum",
    "rain_current_hour",
    "snow_current_hour",
    "sunrise",
    "sunset",
    "uv_index",
    "location",
]

AQ_SENSOR_KEYS = ["pm2_5", "pm10", "co", "no2", "so2", "o3", "aqi_us", "aqi_eu"]
ALL_SENSOR_KEYS = WEATHER_SENSOR_KEYS + AQ_SENSOR_KEYS

SENSOR_LABELS: dict[str, dict[str, str]] = {
    "temperature": {"pl": "Temperatura", "en": "Temperature"},
    "apparent_temperature": {"pl": "Temperatura odczuwalna", "en": "Apparent temperature"},
    "humidity": {"pl": "Wilgotność", "en": "Humidity"},
    "pressure": {"pl": "Ciśnienie", "en": "Pressure"},
    "dew_point": {"pl": "Punkt rosy", "en": "Dew point"},
    "wind_speed": {"pl": "Prędkość wiatru", "en": "Wind speed"},
    "wind_gust": {"pl": "Porywy wiatru", "en": "Wind gust"},
    "wind_bearing": {"pl": "Kierunek wiatru", "en": "Wind direction"},
    "precipitation_probability": {"pl": "Prawdopodobieństwo opadów", "en": "Precipitation probability"},
    "visibility": {"pl": "Widoczność", "en": "Visibility"},
    "precipitation_sum": {"pl": "Suma opadów", "en": "Precipitation sum"},
    "rain_current_hour": {"pl": "Deszcz (bieżąca godzina)", "en": "Rain (current hour)"},
    "snow_current_hour": {"pl": "Śnieg (bieżąca godzina)", "en": "Snow (current hour)"},
    "sunrise": {"pl": "Wschód słońca", "en": "Sunrise"},
    "sunset": {"pl": "Zachód słońca", "en": "Sunset"},
    "uv_index": {"pl": "Indeks UV", "en": "UV index"},
    "location": {"pl": "Lokalizacja", "en": "Location"},
    "pm2_5": {"pl": "PM2.5", "en": "PM2.5"},
    "pm10": {"pl": "PM10", "en": "PM10"},
    "co": {"pl": "Tlenek węgla", "en": "Carbon monoxide"},
    "no2": {"pl": "Dwutlenek azotu", "en": "Nitrogen dioxide"},
    "so2": {"pl": "Dwutlenek siarki", "en": "Sulphur dioxide"},
    "o3": {"pl": "Ozon", "en": "Ozone"},
    "aqi_us": {"pl": "US AQI", "en": "US AQI"},
    "aqi_eu": {"pl": "European AQI", "en": "European AQI"},
}
