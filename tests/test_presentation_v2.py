from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.util import dt as dt_util

from custom_components.openmeteo.const import (
    CONF_AREA_NAME_OVERRIDE,
    CONF_ENTITY_ID,
    CONF_MODE,
    DOMAIN,
    MODE_TRACK,
)
from custom_components.openmeteo.coordinator import OpenMeteoDataUpdateCoordinator
from custom_components.openmeteo.sensor import SENSORS


class FakeStore:
    async def async_save(self, data):
        return None


@pytest.mark.asyncio
async def test_presentation_override_does_not_replace_real_location(hass) -> None:
    now = dt_util.utcnow()
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Telefon Hubert",
        data={
            CONF_MODE: MODE_TRACK,
            CONF_ENTITY_ID: "device_tracker.phone",
            CONF_AREA_NAME_OVERRIDE: "Telefon Hubert",
        },
    )
    entry.add_to_hass(hass)
    hass.states.async_set(
        "device_tracker.phone",
        "not_home",
        {"latitude": 51.5136, "longitude": 7.4653},
    )

    coordinator = OpenMeteoDataUpdateCoordinator(
        hass,
        entry,
        FakeStore(),
        {
            "latitude": 52.2833,
            "longitude": 7.4333,
            "accepted_at": now.isoformat(),
            "location_name": "Lotte, DE",
        },
    )
    coordinator._client.async_weather = AsyncMock(
        return_value={"timezone": "Europe/Berlin", "current": {}, "hourly": {}, "daily": {}}
    )
    coordinator._client.async_air_quality = AsyncMock(return_value={})

    with patch(
        "custom_components.openmeteo.coordinator.async_reverse_geocode",
        new=AsyncMock(return_value="Dortmund, DE"),
    ):
        payload = await coordinator._async_update_data()

    assert payload["location_name"] == "Dortmund, DE"
    assert payload["presentation_name"] == "Telefon Hubert"
    assert coordinator.presentation_name == "Telefon Hubert"
    assert entry.title == "Telefon Hubert"
    assert SENSORS["location"].value_fn(payload) == "Dortmund, DE"

    await coordinator.async_shutdown()


@pytest.mark.asyncio
async def test_shutdown_releases_openmeteo_and_core_coordinator_state(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_MODE: MODE_TRACK, CONF_ENTITY_ID: "device_tracker.phone"},
    )
    entry.add_to_hass(hass)
    coordinator = OpenMeteoDataUpdateCoordinator(hass, entry, FakeStore(), {})
    await coordinator.async_start_tracking()

    assert coordinator._tracker_unsub is not None
    assert coordinator._shutdown_requested is False

    await coordinator.async_shutdown()

    assert coordinator._tracker_unsub is None
    assert coordinator._delayed_refresh_unsub is None
    assert coordinator._shutdown_requested is True
