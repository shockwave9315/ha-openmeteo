from __future__ import annotations

import pytest
from unittest.mock import patch

from datetime import timedelta
from pathlib import Path
import sys

from homeassistant import config_entries
from homeassistant.util import dt as dt_util

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_test_home_assistant,
    INSTANCES,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from custom_components.openmeteo import DOMAIN
from custom_components.openmeteo.const import (
    CONF_ENTITY_ID,
    CONF_MODE,
    MODE_TRACK,
)
from custom_components.openmeteo.coordinator import (
    OpenMeteoDataUpdateCoordinator,
    OPT_LAST_LAT,
    OPT_LAST_LON,
    OPT_LAST_LOCATION_NAME,
)


A_LAT, A_LON = 50.1234, 19.9876


@pytest.fixture
def expected_lingering_timers():
    """Allow lingering timers; the integration is not fully unloaded in these tests."""
    return True


class _FakeResponse:
    status = 200

    async def json(self):
        return {}

    async def text(self):
        return ""

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSession:
    def get(self, *args, **kwargs):
        return _FakeResponse()


@pytest.mark.asyncio
async def test_loads_last_coords_from_entry_data():
    """Coordinator should hydrate cached coordinates from entry data when options are empty."""

    with patch("homeassistant.util.dt.get_time_zone", return_value=dt_util.UTC):
        async with async_test_home_assistant() as hass:
            entry = MockConfigEntry(
                domain=DOMAIN,
                data={
                    CONF_MODE: MODE_TRACK,
                    OPT_LAST_LAT: A_LAT,
                    OPT_LAST_LON: A_LON,
                    OPT_LAST_LOCATION_NAME: "Saved place",
                },
                options={},
            )
            entry.add_to_hass(hass)

            token = config_entries.current_entry.set(entry)
            try:
                coordinator = OpenMeteoDataUpdateCoordinator(hass, entry)
            finally:
                config_entries.current_entry.reset(token)

            assert coordinator._cached == pytest.approx((A_LAT, A_LON))  # type: ignore[attr-defined]
            assert coordinator.location_name == "Saved place"
            assert coordinator.last_location_update is not None

            async_fire_time_changed(hass, dt_util.utcnow() + timedelta(days=1))
            await hass.async_block_till_done()

            await hass.async_stop()
            try:
                INSTANCES.remove(hass)
            except ValueError:
                pass


@pytest.mark.asyncio
async def test_persists_last_coords_into_entry_data_and_options():
    """Coordinator should persist accepted coordinates to both entry options and data."""

    with patch("homeassistant.util.dt.get_time_zone", return_value=dt_util.UTC):
        async with async_test_home_assistant() as hass:
            entry = MockConfigEntry(
                domain=DOMAIN,
                data={CONF_MODE: MODE_TRACK},
                options={CONF_ENTITY_ID: "device_tracker.phone"},
            )
            entry.add_to_hass(hass)

            hass.states.async_set(
                "device_tracker.phone",
                "not_home",
                {"latitude": A_LAT, "longitude": A_LON},
            )

            token = config_entries.current_entry.set(entry)
            try:
                coordinator = OpenMeteoDataUpdateCoordinator(hass, entry)
            finally:
                config_entries.current_entry.reset(token)

            fake_session = _FakeSession()

            with patch(
                "custom_components.openmeteo.coordinator.async_get_clientsession",
                return_value=fake_session,
            ), patch(
                "custom_components.openmeteo.coordinator.async_reverse_geocode",
                return_value="Tracked place",
            ), patch.object(
                OpenMeteoDataUpdateCoordinator,
                "async_update_entry_no_reload",
                autospec=True,
            ) as mock_update_entry:
                mock_update_entry.return_value = None

                await coordinator._async_update_data()

            assert mock_update_entry.call_count == 1
            kwargs = mock_update_entry.call_args.kwargs

            assert kwargs["options"][OPT_LAST_LAT] == pytest.approx(A_LAT)
            assert kwargs["options"][OPT_LAST_LON] == pytest.approx(A_LON)
            assert kwargs["options"][OPT_LAST_LOCATION_NAME] == "Tracked place"

            assert kwargs["data"][OPT_LAST_LAT] == pytest.approx(A_LAT)
            assert kwargs["data"][OPT_LAST_LON] == pytest.approx(A_LON)
            assert kwargs["data"][OPT_LAST_LOCATION_NAME] == "Tracked place"

            # Ensure timers advance without pending tasks at shutdown
            async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
            await hass.async_block_till_done()

            await hass.async_stop()
            try:
                INSTANCES.remove(hass)
            except ValueError:
                pass

