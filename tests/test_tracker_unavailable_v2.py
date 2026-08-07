from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util

from custom_components.openmeteo.const import (
    CONF_ENTITY_ID,
    CONF_MODE,
    DOMAIN,
    MODE_TRACK,
)
from custom_components.openmeteo.coordinator import OpenMeteoDataUpdateCoordinator


class FakeStore:
    def __init__(self) -> None:
        self.saved = None

    async def async_save(self, data):
        self.saved = data


@pytest.mark.asyncio
async def test_missing_tracker_uses_last_accepted_runtime_location(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_MODE: MODE_TRACK, CONF_ENTITY_ID: "device_tracker.phone"},
    )
    entry.add_to_hass(hass)

    coordinator = OpenMeteoDataUpdateCoordinator(
        hass,
        entry,
        FakeStore(),
        {
            "latitude": 51.5136,
            "longitude": 7.4653,
            "accepted_at": dt_util.utcnow().isoformat(),
            "location_name": "Dortmund, DE",
        },
    )

    latitude, longitude, changed, movement = await coordinator._resolve_tracking_coordinates(
        dt_util.utcnow()
    )

    assert latitude == pytest.approx(51.5136)
    assert longitude == pytest.approx(7.4653)
    assert changed is False
    assert movement == 0.0
    await coordinator.async_shutdown()


@pytest.mark.asyncio
async def test_missing_tracker_without_runtime_location_never_falls_back_to_home(hass) -> None:
    hass.config.latitude = 50.085
    hass.config.longitude = 20.849
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_MODE: MODE_TRACK, CONF_ENTITY_ID: "device_tracker.phone"},
    )
    entry.add_to_hass(hass)

    coordinator = OpenMeteoDataUpdateCoordinator(hass, entry, FakeStore(), {})
    coordinator._client.async_weather = AsyncMock()
    coordinator._client.async_air_quality = AsyncMock()

    with pytest.raises(UpdateFailed, match="no GPS coordinates and no last known location"):
        await coordinator._async_update_data()

    coordinator._client.async_weather.assert_not_awaited()
    coordinator._client.async_air_quality.assert_not_awaited()
    assert coordinator._accepted_lat is None
    assert coordinator._accepted_lon is None
    await coordinator.async_shutdown()
