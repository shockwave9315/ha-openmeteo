import pytest
from unittest.mock import patch
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

pytest_plugins = "pytest_homeassistant_custom_component"

from custom_components.openmeteo import resolve_coords, build_title, DOMAIN
from custom_components.openmeteo.const import (
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_MODE,
    MODE_STATIC,
)

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_test_home_assistant,
)
from datetime import timedelta

from homeassistant.util import dt as dt_util

A_LAT, A_LON = 50.067, 20.000
B_LAT, B_LON = 51.110, 22.000


async def fake_geocode(hass, lat, lon, provider=None):
    if (lat, lon) == (A_LAT, A_LON):
        return "Radłów"
    if (lat, lon) == (B_LAT, B_LON):
        return "Delegacja"
    return None


@pytest.mark.asyncio
async def test_per_entry_coords_and_title():
    with patch("homeassistant.util.dt.get_time_zone", return_value=dt_util.UTC):
        async with async_test_home_assistant() as hass:
            entry_a = MockConfigEntry(
                domain=DOMAIN,
                data={CONF_MODE: MODE_STATIC, CONF_LATITUDE: A_LAT, CONF_LONGITUDE: A_LON},
                title="A",
                options={},
            )
            entry_a.add_to_hass(hass)

            entry_b = MockConfigEntry(
                domain=DOMAIN,
                data={CONF_MODE: MODE_STATIC, CONF_LATITUDE: B_LAT, CONF_LONGITUDE: B_LON},
                title="B",
                options={},
            )
            entry_b.add_to_hass(hass)

            with patch(
                "custom_components.openmeteo.coordinator.async_reverse_geocode",
                side_effect=fake_geocode,
            ), patch(
                "custom_components.openmeteo.async_reverse_geocode",
                side_effect=fake_geocode,
            ):
                lat_a, lon_a, _ = await resolve_coords(hass, entry_a)
                title_a = await build_title(hass, entry_a, lat_a, lon_a)
                lat_b, lon_b, _ = await resolve_coords(hass, entry_b)
                title_b = await build_title(hass, entry_b, lat_b, lon_b)

            assert (lat_a, lon_a) == (A_LAT, A_LON)
            assert (lat_b, lon_b) == (B_LAT, B_LON)
            assert title_a != title_b

            # Simulate options flow toggle for entry_b
            hass.config_entries.async_update_entry(
                entry_b, options={CONF_MODE: MODE_STATIC}
            )
            await hass.async_block_till_done()
            async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
            await hass.async_block_till_done()
            with patch(
                "custom_components.openmeteo.coordinator.async_reverse_geocode",
                side_effect=fake_geocode,
            ), patch(
                "custom_components.openmeteo.async_reverse_geocode",
                side_effect=fake_geocode,
            ):
                lat_b2, lon_b2, _ = await resolve_coords(hass, entry_b)
                title_b2 = await build_title(hass, entry_b, lat_b2, lon_b2)

            assert (lat_b2, lon_b2) == (B_LAT, B_LON)
            assert title_b2 == title_b
            assert title_b2 != title_a

            assert await hass.config_entries.async_unload(entry_a.entry_id)
            assert await hass.config_entries.async_unload(entry_b.entry_id)
            async_fire_time_changed(hass, dt_util.utcnow() + timedelta(days=1))
            await hass.async_block_till_done()
            await hass.async_stop()


@pytest.mark.asyncio
async def test_build_title_fallback():
    with patch("homeassistant.util.dt.get_time_zone", return_value=dt_util.UTC):
        async with async_test_home_assistant() as hass:
            entry = MockConfigEntry(
                domain=DOMAIN,
                data={CONF_MODE: MODE_STATIC, CONF_LATITUDE: A_LAT, CONF_LONGITUDE: A_LON},
                title="",
                options={},
            )
            entry.add_to_hass(hass)

            with patch(
                "custom_components.openmeteo.async_reverse_geocode",
                return_value=None,
            ):
                title = await build_title(hass, entry, A_LAT, A_LON)

            assert title == f"{A_LAT:.5f},{A_LON:.5f}"

            assert await hass.config_entries.async_unload(entry.entry_id)
            async_fire_time_changed(hass, dt_util.utcnow() + timedelta(days=1))
            await hass.async_block_till_done()
            await hass.async_stop()
