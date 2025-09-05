import pytest

import pytest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

pytest_plugins = "pytest_homeassistant_custom_component"

from custom_components.openmeteo.config_flow import (
    OpenMeteoConfigFlow,
    OpenMeteoOptionsFlowHandler,
)
from custom_components.openmeteo.const import (
    DOMAIN,
    CONF_MODE,
    MODE_STATIC,
    MODE_TRACK,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_ENTITY_ID,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_test_home_assistant
from unittest.mock import patch
from homeassistant.util import dt as dt_util


@pytest.mark.asyncio
async def test_config_flow_track_form_no_default():
    with patch("homeassistant.util.dt.get_time_zone", return_value=dt_util.UTC):
        async with async_test_home_assistant() as hass:
            flow = OpenMeteoConfigFlow()
            flow.hass = hass
            # choose track mode
            result = await flow.async_step_user({CONF_MODE: MODE_TRACK})
            assert result["type"] == "form"
            assert result["step_id"] == "mode_details"
            await hass.async_stop()


@pytest.mark.asyncio
async def test_options_flow_static_without_entity():
    with patch("homeassistant.util.dt.get_time_zone", return_value=dt_util.UTC):
        async with async_test_home_assistant() as hass:
            entry = MockConfigEntry(
                domain=DOMAIN,
                data={CONF_MODE: MODE_STATIC, CONF_LATITUDE: 1.0, CONF_LONGITUDE: 2.0},
                options={},
            )
            entry.add_to_hass(hass)
            flow = OpenMeteoOptionsFlowHandler(entry)
            flow.hass = hass
            result = await flow.async_step_init()
            assert result["type"] == "form"
            await hass.async_stop()


@pytest.mark.asyncio
async def test_options_flow_track_with_entity():
    with patch("homeassistant.util.dt.get_time_zone", return_value=dt_util.UTC):
        async with async_test_home_assistant() as hass:
            entry = MockConfigEntry(
                domain=DOMAIN,
                data={CONF_MODE: MODE_TRACK, CONF_ENTITY_ID: "device_tracker.demo"},
                options={},
            )
            entry.add_to_hass(hass)
            flow = OpenMeteoOptionsFlowHandler(entry)
            flow.hass = hass
            result = await flow.async_step_init()
            assert result["type"] == "form"
            await hass.async_stop()


@pytest.mark.asyncio
async def test_config_flow_uses_hass_coords_as_defaults():
    with patch("homeassistant.util.dt.get_time_zone", return_value=dt_util.UTC):
        async with async_test_home_assistant() as hass:
            hass.config.latitude = 12.34
            hass.config.longitude = 56.78
            flow = OpenMeteoConfigFlow()
            flow.hass = hass
            await flow.async_step_user({CONF_MODE: MODE_STATIC})
            result = await flow.async_step_mode_details()
            schema = result["data_schema"].schema
            lat_default = next(
                (k.default() if callable(k.default) else k.default)
                for k in schema
                if k.schema == CONF_LATITUDE
            )
            lon_default = next(
                (k.default() if callable(k.default) else k.default)
                for k in schema
                if k.schema == CONF_LONGITUDE
            )
            assert lat_default == 12.34
            assert lon_default == 56.78
            await hass.async_stop()


@pytest.mark.asyncio
async def test_options_flow_can_edit_lat_lon():
    with patch("homeassistant.util.dt.get_time_zone", return_value=dt_util.UTC):
        async with async_test_home_assistant() as hass:
            entry = MockConfigEntry(
                domain=DOMAIN,
                data={CONF_MODE: MODE_STATIC, CONF_LATITUDE: 1.0, CONF_LONGITUDE: 2.0},
                options={},
            )
            entry.add_to_hass(hass)
            flow = OpenMeteoOptionsFlowHandler(entry)
            flow.hass = hass
            result = await flow.async_step_init()
            schema = result["data_schema"].schema
            lat_default = next(
                (k.default() if callable(k.default) else k.default)
                for k in schema
                if k.schema == CONF_LATITUDE
            )
            lon_default = next(
                (k.default() if callable(k.default) else k.default)
                for k in schema
                if k.schema == CONF_LONGITUDE
            )
            assert lat_default == 1.0
            assert lon_default == 2.0
            result = await flow.async_step_init({CONF_LATITUDE: 3.0, CONF_LONGITUDE: 4.0})
            assert result["type"] == "create_entry"
            assert result["data"][CONF_LATITUDE] == 3.0
            assert result["data"][CONF_LONGITUDE] == 4.0
            await hass.async_stop()
