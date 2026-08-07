from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant import config_entries
from homeassistant.const import CONF_LATITUDE, CONF_LOCATION, CONF_LONGITUDE
from homeassistant.data_entry_flow import FlowResultType

from custom_components.openmeteo.const import (
    CONF_ENABLED_AQ_SENSORS,
    CONF_ENABLED_WEATHER_SENSORS,
    CONF_ENTITY_ID,
    CONF_MIN_TRACK_INTERVAL,
    CONF_MODE,
    CONF_REVERSE_GEOCODE_COOLDOWN_MIN,
    CONF_UPDATE_INTERVAL_MIN,
    DOMAIN,
    MODE_STATIC,
    MODE_TRACK,
)
from custom_components.openmeteo.identity import CONF_SOURCE_KEY


pytestmark = pytest.mark.asyncio


async def test_tracking_user_flow_uses_tracker_identity_not_current_city(hass) -> None:
    hass.states.async_set(
        "device_tracker.phone",
        "not_home",
        {
            "friendly_name": "Telefon",
            "latitude": 51.5136,
            "longitude": 7.4653,
        },
    )

    with patch(
        "custom_components.openmeteo.async_setup_entry",
        new=AsyncMock(return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_MODE: MODE_TRACK}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "details"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_ENTITY_ID: "device_tracker.phone",
                CONF_MIN_TRACK_INTERVAL: 15,
                CONF_UPDATE_INTERVAL_MIN: 10,
                CONF_REVERSE_GEOCODE_COOLDOWN_MIN: 15,
                CONF_ENABLED_WEATHER_SENSORS: ["temperature", "humidity", "location"],
                CONF_ENABLED_AQ_SENSORS: ["aqi_eu"],
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Open-Meteo: Telefon"
    assert result["data"][CONF_MODE] == MODE_TRACK
    assert result["data"][CONF_ENTITY_ID] == "device_tracker.phone"
    assert result["data"][CONF_SOURCE_KEY] == "phone"
    assert "Dortmund" not in result["data"][CONF_SOURCE_KEY]


async def test_static_user_flow_uses_native_location_selector(hass) -> None:
    with patch(
        "custom_components.openmeteo.config_flow.async_reverse_geocode",
        new=AsyncMock(return_value="Radłów, PL"),
    ), patch(
        "custom_components.openmeteo.async_setup_entry",
        new=AsyncMock(return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_MODE: MODE_STATIC}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "details"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_LOCATION: {
                    CONF_LATITUDE: 50.085,
                    CONF_LONGITUDE: 20.849,
                },
                CONF_UPDATE_INTERVAL_MIN: 10,
                CONF_REVERSE_GEOCODE_COOLDOWN_MIN: 15,
                CONF_ENABLED_WEATHER_SENSORS: ["temperature", "pressure", "location"],
                CONF_ENABLED_AQ_SENSORS: [],
            },
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Radłów, PL"
    assert result["data"][CONF_MODE] == MODE_STATIC
    assert result["data"][CONF_LATITUDE] == pytest.approx(50.085)
    assert result["data"][CONF_LONGITUDE] == pytest.approx(20.849)
    assert CONF_LOCATION not in result["data"]
