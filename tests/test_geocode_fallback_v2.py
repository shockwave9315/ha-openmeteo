from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.util import dt as dt_util

from custom_components.openmeteo.const import DOMAIN
from custom_components.openmeteo.coordinator import OpenMeteoDataUpdateCoordinator
from custom_components.openmeteo.location import coordinate_label


class FakeStore:
    async def async_save(self, data) -> None:
        return None


@pytest.mark.asyncio
async def test_large_jump_geocode_failure_does_not_keep_previous_city(hass) -> None:
    now = dt_util.utcnow()
    entry = MockConfigEntry(domain=DOMAIN, title="Lotte, DE", version=3, minor_version=2)
    entry.add_to_hass(hass)
    coordinator = OpenMeteoDataUpdateCoordinator(
        hass,
        entry,
        FakeStore(),
        {
            "latitude": 52.2833,
            "longitude": 7.4333,
            "location_name": "Lotte, DE",
            "geocoded_at": now.isoformat(),
        },
    )

    latitude = 51.5136
    longitude = 7.4653
    expected = coordinate_label(latitude, longitude)

    with patch(
        "custom_components.openmeteo.coordinator.async_reverse_geocode",
        new=AsyncMock(return_value=None),
    ):
        name, changed = await coordinator._resolve_location_name(
            latitude,
            longitude,
            now=now,
            coordinates_changed=True,
            movement_km=85.0,
        )

    assert name == expected
    assert name != "Lotte, DE"
    assert changed is True
    await coordinator.async_shutdown()
