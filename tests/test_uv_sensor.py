import pytest


class DummyCoordinator:
    def __init__(self, data=None):
        self.hass = None
        self.data = data or {}
        self.last_update_success = True
        self.provider = "Open-Meteo"
        self._listeners = []

    def async_add_listener(self, update_callback, context=None):
        self._listeners.append(update_callback)

        def _remove():
            try:
                self._listeners.remove(update_callback)
            except ValueError:
                pass

        return _remove


@pytest.fixture
def expected_lingering_timers():
    # The integration is not fully loaded in these tests, so allow lingering timers.
    return True


def test_uv_sensor_uses_uv_index_unit():
    from homeassistant.const import UV_INDEX
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.openmeteo.const import (
        CONF_LATITUDE,
        CONF_LONGITUDE,
        CONF_MODE,
        DOMAIN,
        MODE_STATIC,
    )
    from custom_components.openmeteo.sensor import OpenMeteoUvIndexSensor

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_MODE: MODE_STATIC, CONF_LATITUDE: 0.0, CONF_LONGITUDE: 0.0},
        options={},
        title="Test",  # Device name
    )

    coordinator = DummyCoordinator({"current": {"uv_index": 3.4}})

    sensor = OpenMeteoUvIndexSensor(coordinator, entry)

    assert sensor.native_unit_of_measurement == UV_INDEX
