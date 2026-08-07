from __future__ import annotations

from custom_components.openmeteo.config_flow import OpenMeteoConfigFlow


def test_v2_config_entry_schema_starts_at_1_1() -> None:
    """Keep the clean V2 baseline explicit for future schema evolution."""
    assert OpenMeteoConfigFlow.VERSION == 1
    assert OpenMeteoConfigFlow.MINOR_VERSION == 1
