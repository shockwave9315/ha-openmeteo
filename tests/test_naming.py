from types import SimpleNamespace
from pathlib import Path
import sys
from unittest.mock import patch
from types import SimpleNamespace

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

A_LAT, A_LON = 50.0, 20.0


class DummyCoordinator(SimpleNamespace):
    def __init__(self, hass):
        super().__init__(
            hass=hass,
            data={},
            last_update_success=True,
            provider="test",
            location_name="Radłów, PL",
            latitude=A_LAT,
            longitude=A_LON,
        )

    def async_add_listener(self, cb, *_):
        return lambda: None


@pytest.mark.asyncio
@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_sensor_dynamic_name(expected_lingering_timers):
    from pytest_homeassistant_custom_component.common import (
        MockConfigEntry,
        async_test_home_assistant,
    )
    from custom_components.openmeteo.sensor import OpenMeteoSensor
    from custom_components.openmeteo.const import (
        DOMAIN,
        CONF_MODE,
        MODE_STATIC,
        CONF_LATITUDE,
        CONF_LONGITUDE,
    )

    from homeassistant.util import dt as dt_util

    with patch("homeassistant.util.dt.get_time_zone", return_value=dt_util.UTC):
        async with async_test_home_assistant() as hass:
            entry = MockConfigEntry(
                domain=DOMAIN,
                data={CONF_MODE: MODE_STATIC, CONF_LATITUDE: A_LAT, CONF_LONGITUDE: A_LON},
                options={},
                title="X",
            )
            coordinator = DummyCoordinator(hass)
            sensor = OpenMeteoSensor(coordinator, entry, "uv_index")
            sensor.hass = hass
            sensor.entity_id = f"sensor.{sensor._attr_suggested_object_id}"
            assert sensor.entity_id == "sensor.open_meteo_uv_index"
            assert sensor.name == "Indeks UV — Radłów, PL"
            await hass.async_stop()


@pytest.mark.asyncio
async def test_weather_name_fallback_coords():
    from pytest_homeassistant_custom_component.common import (
        MockConfigEntry,
        async_test_home_assistant,
    )
    from custom_components.openmeteo.weather import OpenMeteoWeather
    from custom_components.openmeteo.const import (
        DOMAIN,
        CONF_MODE,
        MODE_STATIC,
        CONF_LATITUDE,
        CONF_LONGITUDE,
    )
    from custom_components.openmeteo.coordinator import OpenMeteoDataUpdateCoordinator

    class DummySession:
        def get(self, *args, **kwargs):
            class DummyResp:
                status = 200

                async def json(self):
                    return {"hourly": {"time": [], "uv_index": []}, "timezone": "UTC"}

                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    return False

            return DummyResp()

    from homeassistant.util import dt as dt_util

    with patch("homeassistant.util.dt.get_time_zone", return_value=dt_util.UTC):
        async with async_test_home_assistant() as hass:
            entry = MockConfigEntry(
                domain=DOMAIN,
                data={CONF_MODE: MODE_STATIC, CONF_LATITUDE: A_LAT, CONF_LONGITUDE: A_LON},
                options={},
                title="X",
            )
            entry.add_to_hass(hass)
            with patch(
                "custom_components.openmeteo.coordinator.async_get_clientsession",
                return_value=DummySession(),
            ), patch(
                "custom_components.openmeteo.coordinator.async_reverse_geocode",
                return_value=None,
            ):
                coordinator = OpenMeteoDataUpdateCoordinator(hass, entry)
                coordinator.latitude = A_LAT
                coordinator.longitude = A_LON
                await coordinator.async_refresh()
            weather = OpenMeteoWeather(coordinator, entry)
            weather.hass = hass
            name = weather.name
            assert name.startswith("Open Meteo — ")
            assert f"{A_LAT:.5f}" in name
            await hass.async_stop()

