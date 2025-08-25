import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

A_LAT, A_LON = 50.0, 20.0


class DummyCoordinator(SimpleNamespace):
    def __init__(self, hass):
        super().__init__(hass=hass, data={}, last_update_success=True, provider="test")

    def async_add_listener(self, cb, *_args):  # pragma: no cover - trivial
        return lambda: None


@pytest.mark.asyncio
async def test_sensor_has_entity_name_label():
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import (
        MockConfigEntry,
        async_test_home_assistant,
    )
    from custom_components.openmeteo.sensor import OpenMeteoSensor, SENSOR_TYPES
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
            coordinator = DummyCoordinator(hass)
            sensor = OpenMeteoSensor(coordinator, entry, "temperature")
            assert SENSOR_TYPES["temperature"].name == "Temperatura"
            assert sensor._attr_has_entity_name is True
            assert sensor.name == "Temperatura"
            assert "Open-Meteo" not in sensor.name
            assert f"{A_LAT:.5f}" not in sensor.name
            assert all("Open-Meteo" not in (desc.name or "") for desc in SENSOR_TYPES.values())
            await hass.async_stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_device_name_follows_place_and_respects_user_rename(expected_lingering_timers):
    from homeassistant.util import dt as dt_util
    from homeassistant.helpers import device_registry as dr
    from pytest_homeassistant_custom_component.common import (
        MockConfigEntry,
        async_test_home_assistant,
    )
    from custom_components.openmeteo.weather import OpenMeteoWeather
    from custom_components.openmeteo.helpers import maybe_update_device_name
    from custom_components.openmeteo.const import (
        CONF_LATITUDE,
        CONF_LONGITUDE,
        CONF_MODE,
        CONF_USE_PLACE_AS_DEVICE_NAME,
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
            entry.add_to_hass(hass)
            dev_reg = dr.async_get(hass)
            device = dev_reg.async_get_or_create(
                config_entry_id=entry.entry_id,
                identifiers={(DOMAIN, entry.entry_id)},
            )
            await maybe_update_device_name(hass, entry, "Radłów")
            device = dev_reg.async_get(device.id)
            assert device.name == "Radłów"

            weather = OpenMeteoWeather(DummyCoordinator(hass), entry)
            weather.hass = hass
            weather.entity_id = "weather.test"
            await weather.async_added_to_hass()
            assert weather.name == "Radłów"
            assert "Open-Meteo" not in weather.name

            dev_reg.async_update_device(device.id, name_by_user="My Station")
            device = dev_reg.async_get(device.id)
            assert device.name == "Radłów"
            assert device.name_by_user == "My Station"
            await maybe_update_device_name(hass, entry, "Kraków")
            device = dev_reg.async_get(device.id)
            assert device.name == "Radłów"
            assert device.name_by_user == "My Station"
            await hass.async_stop()


@pytest.mark.asyncio
async def test_options_flow_static_has_no_use_place():
    from pytest_homeassistant_custom_component.common import (
        MockConfigEntry,
        async_test_home_assistant,
    )
    from custom_components.openmeteo.config_flow import OpenMeteoOptionsFlow
    from homeassistant.util import dt as dt_util
    from custom_components.openmeteo.const import (
        CONF_API_PROVIDER,
        CONF_LATITUDE,
        CONF_LONGITUDE,
        CONF_MODE,
        CONF_UNITS,
        CONF_UPDATE_INTERVAL,
        CONF_USE_PLACE_AS_DEVICE_NAME,
        DEFAULT_API_PROVIDER,
        DEFAULT_UNITS,
        DEFAULT_UPDATE_INTERVAL,
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
            entry.add_to_hass(hass)
            flow = OpenMeteoOptionsFlow(entry)
            flow.hass = hass
            await flow.async_step_init({CONF_MODE: MODE_STATIC})
            result = await flow.async_step_mode_details()
            assert CONF_USE_PLACE_AS_DEVICE_NAME not in result["data_schema"].schema
            await hass.async_stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("expected_lingering_timers", [True])
async def test_weather_entity_name_from_reverse_geocode(expected_lingering_timers):
    from pytest_homeassistant_custom_component.common import (
        MockConfigEntry,
        async_test_home_assistant,
    )
    from homeassistant.util import dt as dt_util
    from custom_components.openmeteo.coordinator import OpenMeteoDataUpdateCoordinator
    from custom_components.openmeteo.weather import OpenMeteoWeather
    from custom_components.openmeteo.const import (
        CONF_LATITUDE,
        CONF_LONGITUDE,
        CONF_MODE,
        DOMAIN,
        MODE_STATIC,
    )

    class DummyResp:
        status = 200

        async def json(self):
            return {"hourly": {"time": [], "uv_index": []}, "timezone": "UTC"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    class DummySession:
        def get(self, *args, **kwargs):
            return DummyResp()

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
                return_value="Radłów",
            ):
                coordinator = OpenMeteoDataUpdateCoordinator(hass, entry)
                await coordinator.async_config_entry_first_refresh()
            weather = OpenMeteoWeather(coordinator, entry)
            weather.hass = hass
            weather.entity_id = "weather.test"
            await weather.async_added_to_hass()
            assert weather.name == "Radłów"
            await hass.async_stop()
