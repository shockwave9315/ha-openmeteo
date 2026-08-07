from __future__ import annotations

from datetime import timedelta

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.util import dt as dt_util

from custom_components.openmeteo.const import (
    CONF_ENTITY_ID,
    CONF_MIN_TRACK_INTERVAL,
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
async def test_large_city_jump_bypasses_tracking_throttle(hass) -> None:
    now = dt_util.utcnow()
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_MODE: MODE_TRACK,
            CONF_ENTITY_ID: "device_tracker.phone",
            CONF_MIN_TRACK_INTERVAL: 60,
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

    lat, lon, changed, distance = await coordinator._resolve_tracking_coordinates(now)

    assert changed is True
    assert distance > 10
    assert lat == pytest.approx(51.5136)
    assert lon == pytest.approx(7.4653)
    await coordinator.async_shutdown()


@pytest.mark.asyncio
async def test_small_move_is_throttled_but_schedules_followup(hass) -> None:
    now = dt_util.utcnow()
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_MODE: MODE_TRACK,
            CONF_ENTITY_ID: "device_tracker.phone",
            CONF_MIN_TRACK_INTERVAL: 30,
        },
    )
    entry.add_to_hass(hass)
    hass.states.async_set(
        "device_tracker.phone",
        "not_home",
        {"latitude": 50.001, "longitude": 19.001},
    )

    coordinator = OpenMeteoDataUpdateCoordinator(
        hass,
        entry,
        FakeStore(),
        {
            "latitude": 50.0,
            "longitude": 19.0,
            "accepted_at": now.isoformat(),
            "location_name": "Old place, PL",
        },
    )

    lat, lon, changed, distance = await coordinator._resolve_tracking_coordinates(now)

    assert 0.05 < distance < 10
    assert changed is False
    assert lat == pytest.approx(50.0)
    assert lon == pytest.approx(19.0)
    assert coordinator._delayed_refresh_unsub is not None
    await coordinator.async_shutdown()


@pytest.mark.asyncio
async def test_elapsed_throttle_accepts_small_move(hass) -> None:
    now = dt_util.utcnow()
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_MODE: MODE_TRACK,
            CONF_ENTITY_ID: "device_tracker.phone",
            CONF_MIN_TRACK_INTERVAL: 15,
        },
    )
    entry.add_to_hass(hass)
    hass.states.async_set(
        "device_tracker.phone",
        "not_home",
        {"latitude": 50.001, "longitude": 19.001},
    )

    coordinator = OpenMeteoDataUpdateCoordinator(
        hass,
        entry,
        FakeStore(),
        {
            "latitude": 50.0,
            "longitude": 19.0,
            "accepted_at": (now - timedelta(minutes=20)).isoformat(),
        },
    )

    lat, lon, changed, _distance = await coordinator._resolve_tracking_coordinates(now)
    assert changed is True
    assert lat == pytest.approx(50.001)
    assert lon == pytest.approx(19.001)
    await coordinator.async_shutdown()
