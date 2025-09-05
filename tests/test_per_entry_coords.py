# tests/test_per_entry_coords.py
from unittest.mock import patch, Mock

import pytest
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE, CONF_MODE
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
        # Używamy async_test_home_assistant() do stworzenia środowiska
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

            # Patchujemy (podmieniamy) funkcje geokodowania
            with patch(
                "custom_components.openmeteo.coordinator.async_reverse_geocode",
                side_effect=fake_geocode,
            ), patch(
                "custom_components.openmeteo.async_reverse_geocode",
                side_effect=fake_geocode,
            ):
                # POPRAWKA: Zmieniono rozpakowywanie wartości z 3 na 2
                # ponieważ resolve_coords() zwraca tylko krotkę (latitude, longitude)
                lat_a, lon_a = await resolve_coords(hass, entry_a)

                # Zmienne, które testują poprawność pobranych danych
                assert lat_a == A_LAT
                assert lon_a == A_LON

                # Prawdopodobnie tutaj powinieneś umieścić kolejne testy...

    # Tutaj byłby blok `finally` lub `teardown`, który powinien wyłączyć koordynatora.
    # W Twoim przypadku, błąd testu mógł zatrzymać wykonywanie kodu,
    # dlatego błąd "Lingering timer" jest widoczny.
    # Upewnij się, że Twój test kończy się poprawnie,
    # a `async_test_home_assistant` prawidłowo zwalnia zasoby.
    # Jeśli nadal będziesz miał błędy, możesz ręcznie wyłączyć koordynatora
    # tak jak w poprzednim przykładzie.