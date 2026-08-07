from homeassistant.const import UnitOfRatio

from custom_components.openmeteo.sensor import AQ_SENSORS


def test_carbon_monoxide_uses_current_ppm_unit():
    """Keep the CO sensor on the non-deprecated HA ppm unit API."""
    assert AQ_SENSORS["co"].native_unit_of_measurement == UnitOfRatio.PARTS_PER_MILLION
