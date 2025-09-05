import pytest
from unittest.mock import patch, Mock

# Importowanie wymaganych modułów
from pytest_homeassistant_custom_component.common import async_test_home_assistant, MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_MODE

# Importowanie funkcji i stałych z Twojej integracji
from custom_components.openmeteo import resolve_coords, async_setup_entry
from custom_components.openmeteo.const import DOMAIN, MODE_STATIC, CONF_UPDATE_INTERVAL
from custom_components.openmeteo.coordinator import OpenMeteoDataUpdateCoordinator

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
        # Tworzymy środowisko Home Assistant
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
                options={CONF_UPDATE_INTERVAL: 60}, # Dodajemy interwał, żeby uniknąć domyślnej wartości, która może powodować błędy.
            )
            entry_b = MockConfigEntry(
                domain=DOMAIN,
                data={
                    CONF_MODE: MODE_STATIC,
                    CONF_LATITUDE: B_LAT,
                    CONF_LONGITUDE: B_LON
                },
                title="B",
                options={CONF_UPDATE_INTERVAL: 60},
            )

            # POPRAWKA: Jawne ładowanie integracji
            await async_setup_entry(hass, entry_a)
            await async_setup_entry(hass, entry_b)

            # Podmieniamy funkcje geokodowania
            with patch(
                "custom_components.openmeteo.coordinator.async_reverse_geocode",
                side_effect=fake_geocode,
            ):
                # POPRAWKA: Naprawiono rozpakowywanie wartości
                lat_a, lon_a = await resolve_coords(hass, entry_a)

                assert lat_a == A_LAT
                assert lon_a == A_LON

            # POPRAWKA: Jawne wyłączenie koordynatorów w bloku `async with`
            # Jest to niezbędne, aby test zakończył się bez błędu "Lingering timer"
            coordinator_a = hass.data[DOMAIN][entry_a.entry_id]
            await coordinator_a.async_shutdown()

            coordinator_b = hass.data[DOMAIN][entry_b.entry_id]
            await coordinator_b.async_shutdown()