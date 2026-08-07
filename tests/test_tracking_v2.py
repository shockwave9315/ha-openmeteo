from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

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
from custom_components.openmeteo.identity import sensor_unique_id, weather_unique_id


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


@pytest.mark.asyncio
async def test_lotte_to_dortmund_updates_place_without_changing_identity_or_config(hass) -> None:
    """Regression for the v1 bug where the initial city became stale identity."""
    now = dt_util.utcnow()
    original_data = {
        CONF_MODE: MODE_TRACK,
        CONF_ENTITY_ID: "device_tracker.phone",
        CONF_MIN_TRACK_INTERVAL: 60,
    }
    original_options = {"update_interval_min": 10}
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Lotte, DE",
        data=original_data,
        options=original_options,
    )
    entry.add_to_hass(hass)
    hass.states.async_set(
        "device_tracker.phone",
        "not_home",
        {"latitude": 51.5136, "longitude": 7.4653},
    )

    store = FakeStore()
    coordinator = OpenMeteoDataUpdateCoordinator(
        hass,
        entry,
        store,
        {
            "latitude": 52.2833,
            "longitude": 7.4333,
            "accepted_at": now.isoformat(),
            "location_name": "Lotte, DE",
            "geocoded_at": now.isoformat(),
        },
    )

    coordinator._client.async_weather = AsyncMock(
        return_value={
            "timezone": "Europe/Berlin",
            "current": {},
            "hourly": {},
            "daily": {},
        }
    )
    coordinator._client.async_air_quality = AsyncMock(return_value={})

    weather_uid_before = weather_unique_id(entry.entry_id)
    temperature_uid_before = sensor_unique_id(entry.entry_id, "temperature")

    with patch(
        "custom_components.openmeteo.coordinator.async_reverse_geocode",
        new=AsyncMock(return_value="Dortmund, DE"),
    ):
        payload = await coordinator._async_update_data()

    assert payload["location_name"] == "Dortmund, DE"
    assert payload["location"]["latitude"] == pytest.approx(51.5136)
    assert payload["location"]["longitude"] == pytest.approx(7.4653)
    assert entry.title == "Dortmund, DE"

    # Runtime location must not mutate user configuration anymore.
    assert dict(entry.data) == original_data
    assert dict(entry.options) == original_options
    assert store.saved["location_name"] == "Dortmund, DE"

    # Location/display changes cannot create a new registry identity.
    assert weather_unique_id(entry.entry_id) == weather_uid_before
    assert sensor_unique_id(entry.entry_id, "temperature") == temperature_uid_before

    await coordinator.async_shutdown()


@pytest.mark.asyncio
async def test_tracker_event_filter_ignores_gps_jitter(hass) -> None:
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
    coordinator = OpenMeteoDataUpdateCoordinator(
        hass,
        entry,
        FakeStore(),
        {
            "latitude": 50.0,
            "longitude": 19.0,
            "accepted_at": now.isoformat(),
        },
    )

    assert coordinator._tracker_change_requires_refresh((50.00005, 19.00005), now) is False
    assert coordinator._delayed_refresh_unsub is None
    await coordinator.async_shutdown()


@pytest.mark.asyncio
async def test_tracker_event_filter_refreshes_large_jump_immediately(hass) -> None:
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
    coordinator = OpenMeteoDataUpdateCoordinator(
        hass,
        entry,
        FakeStore(),
        {
            "latitude": 52.2833,
            "longitude": 7.4333,
            "accepted_at": now.isoformat(),
        },
    )

    assert coordinator._tracker_change_requires_refresh((51.5136, 7.4653), now) is True
    assert coordinator._delayed_refresh_unsub is None
    await coordinator.async_shutdown()
