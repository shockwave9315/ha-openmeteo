# tests/test_per_entry_coords.py
@pytest.mark.asyncio
async def test_per_entry_coords_and_title():
    with patch("homeassistant.util.dt.get_time_zone", return_value=dt_util.UTC):
        async with async_test_home_assistant() as hass:
            # Twój kod konfiguracyjny...
            entry_a = MockConfigEntry(
                domain=DOMAIN,
                data={CONF_MODE: MODE_STATIC, CONF_LATITUDE: A_LAT, CONF_LONGITUDE: A_LON},
                title="A",
                options={},
            )
            entry_a.add_to_hass(hass)

            # ...i reszta testu.
            with patch(
                "custom_components.openmeteo.coordinator.async_reverse_geocode",
                side_effect=fake_geocode,
            ):
                # Pamiętaj, aby zmienić tę linię na tę poprawioną:
                lat_a, lon_a = await resolve_coords(hass, entry_a)

            # Po zakończeniu testu, upewnij się, że koordynator jest zatrzymany.
            # Ta linia musi zostać dodana.
            # Zapewni to, że timer koordynatora zostanie wyłączony, co rozwiąże błąd "Lingering timer".
            # hass.data[DOMAIN][entry_a.entry_id] to prawdopodobnie twój koordynator.
            if DOMAIN in hass.data and entry_a.entry_id in hass.data[DOMAIN]:
                await hass.data[DOMAIN][entry_a.entry_id].async_shutdown()

# Możliwe, że będziesz musiał także obsłużyć drugi wpis (entry_b)
# i też go wyłączyć, jeśli to konieczne.