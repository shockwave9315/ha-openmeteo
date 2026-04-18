from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch
from pathlib import Path
import sys

import pytest
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_test_home_assistant

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from custom_components.openmeteo import DOMAIN
from custom_components.openmeteo.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_MODE, MODE_STATIC
from custom_components.openmeteo.coordinator import OpenMeteoDataUpdateCoordinator


@pytest.fixture
def expected_lingering_timers():
    """Allow lingering timers in lightweight coordinator tests."""
    return True


@pytest.mark.asyncio
async def test_aq_missing_hourly_does_not_log_warning(
    caplog: pytest.LogCaptureFixture, event_loop
):
    with patch("homeassistant.util.dt.get_time_zone", return_value=dt_util.UTC):
        hass = await async_test_home_assistant(event_loop)
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_MODE: MODE_STATIC, CONF_LATITUDE: 50.0, CONF_LONGITUDE: 20.0},
            options={},
        )
        entry.add_to_hass(hass)

        coordinator = OpenMeteoDataUpdateCoordinator(hass, entry)

        with patch.object(
            coordinator, "_fetch_weather_data", AsyncMock(return_value={})
        ), patch.object(
            coordinator, "_fetch_air_quality", AsyncMock(return_value={"foo": "bar"})
        ), patch.object(
            coordinator, "_update_location_name", AsyncMock(return_value="Test place")
        ), patch.object(
            coordinator, "_should_update_entry_title", return_value=False
        ):
            with caplog.at_level(logging.WARNING):
                result = await coordinator._async_update_data()

        assert "aq" not in result
        assert not any("air quality" in record.getMessage().lower() for record in caplog.records)
