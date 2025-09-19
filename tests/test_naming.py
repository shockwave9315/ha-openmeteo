import pytest
from unittest.mock import patch

A_LAT = 50.087220625849994
A_LON = 20.849695801734928

class DummyCoordinator:
    def __init__(self, hass, data=None):
        self.hass = hass
        self.data = data or {}
        self.last_update_success = True
        self.provider = "Open-Meteo"

@pytest.mark.asyncio
async def test_weather_device_info_uses_location_name():
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import (
        MockConfigEntry,
        async_test_home_assistant,
    )
    from custom_components.openmeteo.weather import OpenMeteoWeather
    from custom_components.openmeteo.const import (
        CONF_LATITUDE,
        CONF_LONGITUDE,
        CONF_MODE,
        DOMAIN,
        MODE_STATIC,
    )

    with patch("homeassistant.util.dt.get_time_zone", return_value=dt_util.UTC):
        async with async_test_home_assistant() as hass:
            entry = MockConfigEntry(
                domain=DOMAIN,
                data={CONF_MODE: MODE_STATIC, CONF_LATITUDE: A_LAT, CONF_LONGITUDE: A_LON},
                options={},
                title="Radłów",  # urządzenie = miejscowość w naszej logice
            )
            coordinator = DummyCoordinator(hass, {"location_name": "Radłów"})
            weather = OpenMeteoWeather(coordinator, entry)
            # device = miejscowość (z tytułu wpisu)
            assert weather.device_info["name"] == "Radłów"
            # ustawiamy friendly name po dodaniu encji do hass
            weather.hass = hass
            await weather.async_added_to_hass()
            assert weather.name == "Radłów"

@pytest.mark.asyncio
async def test_weather_entity_id_stable_and_friendly_name():
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import (
        MockConfigEntry,
        async_test_home_assistant,
    )
    from custom_components.openmeteo.weather import OpenMeteoWeather
    from custom_components.openmeteo.const import (
        CONF_LATITUDE,
        CONF_LONGITUDE,
        CONF_MODE,
        DOMAIN,
        MODE_STATIC,
    )

    with patch("homeassistant.util.dt.get_time_zone", return_value=dt_util.UTC):
        async with async_test_home_assistant() as hass:
            entry = MockConfigEntry(
                domain=DOMAIN,
                data={CONF_MODE: MODE_STATIC, CONF_LATITUDE: A_LAT, CONF_LONGITUDE: A_LON},
                options={},
                title="Radłów",
            )
            coordinator = DummyCoordinator(hass, {"location_name": "Radłów"})
            weather = OpenMeteoWeather(coordinator, entry)
            # ustaw stabilne entity_id
            weather.entity_id = "weather.open_meteo"
            assert weather.entity_id == "weather.open_meteo"
            # friendly = miejscowość (po dodaniu do hass)
            weather.hass = hass
            await weather.async_added_to_hass()
            assert weather.name == "Radłów"
