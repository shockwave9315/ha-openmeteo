# Open-Meteo for Home Assistant — V2 development

> **Status:** active V2 rewrite on `rewrite/v2-architecture`. This branch is not a release yet.

Custom Home Assistant integration using the free Open-Meteo Weather and Air Quality APIs. No API key is required.

## Why V2 exists

The original integration grew through many incremental AI-assisted changes. It worked, but mixed three concepts that must remain separate in Home Assistant:

1. **source identity** — the configured weather source,
2. **current location** — mutable runtime state,
3. **presentation name** — what the UI currently displays.

That caused tracking entries to keep stale city identity. For example, an entry created while the tracker was in **Lotte** could later show weather for **Dortmund**, while parts of the registry/UI still remained tied to Lotte.

V2 rebuilds this model instead of adding another compatibility patch.

## V2 identity model

For tracking entries, the tracker defines a stable source key once:

```text
device_tracker.phone -> source_key: phone
```

The source key and config-entry ID define identity. The current city never does.

A trip can therefore look like this:

```text
Lotte -> Dortmund -> Osnabrück -> Radłów
```

while the same Home Assistant entities continue to exist throughout the trip.

For existing V1 installations, V2 deliberately preserves the old registry `unique_id` values so dashboards, history and automations are not replaced by duplicate entities during migration. Existing user-customized entity IDs are not renamed automatically.

For newly created entries, initial object IDs are source-scoped, for example:

```text
weather.open_meteo_phone
sensor.open_meteo_phone_temperatura
sensor.open_meteo_phone_cisnienie
sensor.open_meteo_phone_lokalizacja
```

## Location modes

### Tracking

Select a `person.*` or `device_tracker.*` entity exposing `latitude` and `longitude`.

Tracking is event driven:

- GPS jitter below roughly 50 m is ignored,
- small movements are grouped according to the configured tracking interval,
- a jump of at least 10 km bypasses that throttle and refreshes immediately,
- a delayed refresh is scheduled for a throttled small movement, so movement is not silently lost.

The current coordinates and place name are runtime data stored in Home Assistant storage. They are **not** written repeatedly into config-entry `data` or `options`.

### Static

Choose a point with Home Assistant's native location selector. Static entries use the configured coordinates and otherwise share the same weather/sensor implementation as tracking entries.

## Current location in Home Assistant

The integration exposes the current place as normal mutable state:

```text
sensor.open_meteo_<source>_lokalizacja = Dortmund, DE
```

with attributes including latitude, longitude, tracking mode and last accepted location update.

The visible integration/device/weather names may follow the current place, but those changes do not alter registry identity and do not trigger a configuration reload by themselves.

## Weather entity

The V2 weather entity targets the Home Assistant 2026.8 native weather API and exposes:

- temperature and apparent temperature,
- humidity and dew point,
- pressure,
- wind speed, direction and gusts,
- visibility,
- cloud coverage,
- UV index,
- weather condition,
- native hourly forecast,
- native daily forecast.

Forecast dictionaries use Home Assistant's current `native_*` forecast fields rather than the old compatibility field names.

## Sensors

Weather sensors include temperature, apparent temperature, humidity, pressure, dew point, wind, precipitation, rain, snowfall, precipitation probability, visibility, sunrise/sunset, UV and current location.

Air-quality sensors include PM2.5, PM10, CO, NO₂, SO₂, O₃, US AQI and European AQI.

Important unit correction in V2: Open-Meteo reports hourly `snowfall` in **centimeters**. V1 incorrectly exposed that value as millimeters; V2 exposes it as `cm`.

## API behavior

V2 requests current Open-Meteo field names such as:

```text
weather_code
dew_point_2m
```

Weather data is required for a successful coordinator update. Air-quality data is best effort: an AQ outage does not take the weather entity down.

Reverse geocoding is isolated from the weather API and currently uses Nominatim with a configurable cooldown. Large location jumps may bypass the cooldown so a trip does not remain labeled with the previous city.

## Configuration migration

Config-entry version 4 migrates V1–V3 entries by:

- normalizing static/tracking mode,
- migrating legacy tracker keys,
- converting the old update interval to minutes,
- splitting the legacy single sensor list into weather and AQ lists,
- creating one stable `source_key`,
- removing obsolete options such as fake `units`, provider selection and old runtime persistence/cooldown fields.

Runtime GPS state is moved out of configuration and into per-entry Home Assistant storage.

## Development and tests

The V2 branch CI targets the same stack as current Home Assistant:

```text
Home Assistant 2026.8.0
Python 3.14
pytest-homeassistant-custom-component 0.13.354
```

The suite covers identity invariants, V1–V3 migration, event-driven tracking, the Lotte→Dortmund regression, API field contracts, sensor units, native HA weather forecasts, title-only update behavior, and full user config-flow paths for TRACK and STATIC modes.

Run locally with:

```bash
python -m pip install -r requirements.txt
pytest -q
```

## Installation

The stable release remains the version published from `main`. V2 should currently be treated as development code and tested on a non-critical/staged Home Assistant installation before release.

## License

Apache License 2.0.

Weather and air-quality data are provided by Open-Meteo. Reverse geocoding uses OpenStreetMap Nominatim.
