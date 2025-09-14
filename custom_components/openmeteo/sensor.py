
# SPDX-License-Identifier: Apache-2.0
"""Sensor platform for Open-Meteo."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Mapping

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfLength,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
)
from .helpers import hourly_value_at_now
from .coordinator import OpenMeteoDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class OpenMeteoSensorDescription(SensorEntityDescription):
    key: str
    value_fn: Callable[[dict[str, Any]], Any] | None = None


def _parse_iso_to_local_dt(s: str | None, tzname: str | None) -> datetime | None:
    if not s:
        return None
    try:
        dt = dt_util.parse_datetime(s)
        if dt and dt.tzinfo is None:
            tz = dt_util.get_time_zone(tzname) or dt_util.UTC
            dt = dt.replace(tzinfo=tz)
        return dt
    except Exception:
        return None


def _hourly_times_converted(data: dict[str, Any]) -> list[datetime]:
    hourly = (data or {}).get("hourly") or {}
    times = hourly.get("time") or []
    tzname = (data or {}).get("timezone")
    out: list[datetime] = []
    for s in times:
        dt = _parse_iso_to_local_dt(s, tzname)
        if dt:
            out.append(dt.replace(minute=0, second=0, microsecond=0))
    return out


def _precip_last_n_hours(data: dict[str, Any], n: int, keys: list[str] | None = None) -> float | None:
    hourly = (data or {}).get("hourly") or {}
    times = _hourly_times_converted(data)
    if not times:
        return None
    if not keys:
        keys = ["precipitation"]
    # index of "now"
    now_idx_val = hourly_value_at_now(times, list(range(len(times))))
    if now_idx_val is None:
        return None
    idx_now = int(now_idx_val)
    total = 0.0
    for k in keys:
        vals = hourly.get(k) or []
        for off in range(n):
            i = idx_now - off
            if 0 <= i < len(vals):
                v = vals[i]
                if isinstance(v, (int, float)):
                    total += float(v)
    return round(total, 2)


SENSORS: dict[str, OpenMeteoSensorDescription] = {
    "temperature": OpenMeteoSensorDescription(
        key="temperature",
        name="Temperatura",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.get("current_weather") or {}).get("temperature"),
    ),
    "humidity": OpenMeteoSensorDescription(
        key="humidity",
        name="Wilgotność",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.get("hourly") or {}).get("relative_humidity_2m") and hourly_value_at_now(
            _hourly_times_converted(d),
            (d.get("hourly") or {}).get("relative_humidity_2m"),
        ),
    ),
    "pressure": OpenMeteoSensorDescription(
        key="pressure",
        name="Ciśnienie",
        native_unit_of_measurement=UnitOfPressure.HPA,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.get("hourly") or {}).get("pressure_msl") and hourly_value_at_now(
            _hourly_times_converted(d),
            (d.get("hourly") or {}).get("pressure_msl"),
        ),
    ),
    "wind_speed": OpenMeteoSensorDescription(
        key="wind_speed",
        name="Wiatr",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.get("hourly") or {}).get("wind_speed_10m") and hourly_value_at_now(
            _hourly_times_converted(d),
            (d.get("hourly") or {}).get("wind_speed_10m"),
        ),
    ),
    "wind_gust": OpenMeteoSensorDescription(
        key="wind_gust",
        name="Porywy wiatru",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.get("hourly") or {}).get("wind_gusts_10m") and hourly_value_at_now(
            _hourly_times_converted(d),
            (d.get("hourly") or {}).get("wind_gusts_10m"),
        ),
    ),
    "precipitation": OpenMeteoSensorDescription(
        key="precipitation",
        name="Opad (teraz)",
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.get("hourly") or {}).get("precipitation") and hourly_value_at_now(
            _hourly_times_converted(d),
            (d.get("hourly") or {}).get("precipitation"),
        ),
    ),
    "precipitation_probability": OpenMeteoSensorDescription(
        key="precipitation_probability",
        name="Szansa opadu",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.get("hourly") or {}).get("precipitation_probability") and hourly_value_at_now(
            _hourly_times_converted(d),
            (d.get("hourly") or {}).get("precipitation_probability"),
        ),
    ),
    "visibility": OpenMeteoSensorDescription(
        key="visibility",
        name="Widoczność",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.get("hourly") or {}).get("visibility") and hourly_value_at_now(
            _hourly_times_converted(d),
            (d.get("hourly") or {}).get("visibility"),
        ),
    ),
    "dew_point": OpenMeteoSensorDescription(
        key="dew_point",
        name="Punkt rosy",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.get("hourly") or {}).get("dewpoint_2m") and hourly_value_at_now(
            _hourly_times_converted(d),
            (d.get("hourly") or {}).get("dewpoint_2m"),
        ),
    ),
    "precipitation_sum": OpenMeteoSensorDescription(
        key="precipitation_sum",
        name="Suma opadów (doba)",
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.get("daily") or {}).get("precipitation_sum") and ((d.get("daily") or {}).get("precipitation_sum")[0] if (d.get("daily") or {}).get("precipitation_sum") else None),
    ),
    "uv_index": OpenMeteoSensorDescription(
        key="uv_index",
        name="Indeks UV",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: (d.get("hourly") or {}).get("uv_index") and hourly_value_at_now(
            _hourly_times_converted(d),
            (d.get("hourly") or {}).get("uv_index"),
        )
        or ((d.get("hourly") or {}).get("uv_index_clear_sky") and hourly_value_at_now(
            _hourly_times_converted(d),
            (d.get("hourly") or {}).get("uv_index_clear_sky"),
        )),
    ),
    "precipitation_last_3h": OpenMeteoSensorDescription(
        key="precipitation_last_3h",
        name="Opad (ostatnie 3h)",
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _precip_last_n_hours(d, 3, ["precipitation", "snowfall"]),
    ),
}

# Entities


class OpenMeteoSensor(CoordinatorEntity[OpenMeteoDataUpdateCoordinator], SensorEntity):
    entity_description: OpenMeteoSensorDescription

    def __init__(
        self,
        coordinator: OpenMeteoDataUpdateCoordinator,
        description: OpenMeteoSensorDescription,
        config_entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._config_entry = config_entry
        self._attr_has_entity_name = True
        self._attr_name = description.name

    @property
    def native_value(self) -> Any:
        data = self.coordinator.data or {}
        fn = self.entity_description.value_fn
        if fn is None:
            return None
        try:
            return fn(data)
        except Exception:  # pragma: no cover (defensive)
            return None

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        try:
            attrs: dict[str, Any] = {}
            provider = getattr(self.coordinator, "provider", None)
            if provider:
                attrs["provider"] = provider
            loc = (self.coordinator.data or {}).get("location_name")
            if loc:
                attrs["location_name"] = loc
            return attrs
        except Exception:  # pragma: no cover
            return None


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: OpenMeteoDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[OpenMeteoSensor] = []
    for desc in SENSORS.values():
        entities.append(OpenMeteoSensor(coordinator, desc, entry))

    async_add_entities(entities)
