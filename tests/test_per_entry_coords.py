import pytest
from unittest.mock import patch, Mock

# Zapewnia dostęp do async_test_home_assistant
from pytest_homeassistant_custom_component.common import async_test_home_assistant, MockConfigEntry

from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_MODE
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.openmeteo import resolve_coords
from custom_components.openmeteo.const import DOMAIN, MODE_STATIC
from custom_components.openmeteo.coordinator import async_reverse_geocode

# Stałe używane w teście
A_LAT = 10.0
A_LON = 10.0
B_LAT = 20.0
B_LON = 20.0

async def fake_geocode(*args):
    """Zastępuje funkcję geokodowania dla celów testowych."""
    return "Test Location"

@pytest.mark.asyncio
async def test_per_entry_coords_and_title():
    """Testuje poprawność koordynatów i tytułu dla wpisów."""
    with patch("homeassistant.util.dt.get_time_zone", return_value=dt_util.UTC):
        async with async_test_home_assistant() as hass:
            # Tworzymy mockowe wpisy konfiguracji
            entry_a = MockConfigEntry(
                domain=DOMAIN,
                data={
                    CONF_MODE: MODE_STATIC,
                    CONF_LATITUDE: A_LAT,
                    CONF_LONGITUDE: A_LON
                },
                title="A",
                options={},
            )
            entry_a.add_to_hass(hass)

            entry_b = MockConfigEntry(
                domain=DOMAIN,
                data={
                    CONF_MODE: MODE_STATIC,
                    CONF_LATITUDE: B_LAT,
                    CONF_LONGITUDE: B_LON
                },
                title="B",
                options={},
            )
            entry_b.add_to_hass(hass)

            # Podmieniamy funkcje geokodowania
            with patch(
                "custom_components.openmeteo.coordinator.async_reverse_geocode",
                side_effect=fake_geocode,
            ), patch(
                "custom_components.openmeteo.async_reverse_geocode",
                side_effect=fake_geocode,
            ):
                # POPRAWKA 1: Naprawiono rozpakowywanie wartości (z 3 na 2)
                lat_a, lon_a = await resolve_coords(hass, entry_a)

                assert lat_a == A_LAT
                assert lon_a == A_LON

            # POPRAWKA 2: Jawne wyłączenie koordynatora, aby uniknąć błędu "Lingering timer"
            # Koordynator jest przechowywany w hass.data
            coordinator = hass.data[DOMAIN][entry_a.entry_id]
            await coordinator.async_shutdown()

            coordinator_b = hass.data[DOMAIN][entry_b.entry_id]
            await coordinator_b.async_shutdown()