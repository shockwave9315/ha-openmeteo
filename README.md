# Open-Meteo for Home Assistant

Custom Home Assistant integration using the free Open-Meteo Weather and Air Quality APIs. No API key is required.

## V2

V2 is the current integration line. It was rebuilt around a simple rule: **source identity, current location and UI presentation are separate things**.

That fixes the main V1 tracking problem where an entry created in one city could later use weather from another city while parts of Home Assistant still kept the original city as entity/device identity.

V2 targets Home Assistant 2026.8+ and Python 3.14.

## V1 -> V2 transition

V2 intentionally does **not** migrate V1 config entries. The first V2 installation is a one-time clean start:

1. remove the old Open-Meteo config entry from Home Assistant,
2. replace/update the custom integration,
3. restart Home Assistant,
4. create the weather source again through the V2 config flow.

From V2 onward, normal updates are expected to preserve config entries, entity identity and history. The V2 config-entry schema starts at **1.1**; compatible schema changes should stay on major version 1 and bump only the minor version.

## Identity model

For a tracking source, the selected tracker creates a stable source key once, for example:

```text
device_tracker.phone -> source_key: phone
```

The source key and config-entry ID define identity. The current city never does.

A trip can therefore look like:

```text
Lotte -> Dortmund -> Osnabrück -> Radłów
```

while the same Home Assistant entities continue to exist throughout the trip.

Example initial object IDs:

```text
weather.open_meteo_phone
sensor.open_meteo_phone_temperatura
sensor.open_meteo_phone_cisnienie
sensor.open_meteo_phone_lokalizacja
```

Registry `unique_id` values are based on the config-entry ID rather than location or presentation name.

## Location modes

### Tracking location

Select a `person.*` or `device_tracker.*` entity exposing `latitude` and `longitude`.

Tracking is event driven:

- GPS jitter below roughly **50 m** is ignored,
- small movements are grouped according to the configured minimum position-update interval,
- a jump of at least **10 km** bypasses that throttle and refreshes immediately,
- a delayed refresh is scheduled for a throttled small movement so the latest position is not silently lost.

Open-Meteo does not force the phone to acquire GPS more often. It only reacts to state changes already produced by Home Assistant / Companion App and filters them before making weather/geocoding requests.

The accepted coordinates and place name are runtime data stored in Home Assistant storage. They are not repeatedly written into config-entry `data` or `options`.

If a tracked entity temporarily has no coordinates, V2 uses the last accepted stored position. A fresh tracking entry with neither live GPS nor a stored last position stays not-ready instead of falling back to Home Assistant's home coordinates.

### Static location

Static mode stores ordinary fixed `latitude` / `longitude`. Version 2.0.2 adds four convenient ways to obtain them during setup or from Options:

1. **Use Home Assistant location** — copy the coordinates configured for the HA instance.
2. **Use current person/device position** — select a `person` or `device_tracker`; its current GPS coordinates are copied **once** and then treated as static. The entity is not tracked afterwards.
3. **Search for a place or address** — enter a city, village or address; Nominatim forward geocoding returns matching locations to choose from.
4. **Pick on the map** — use Home Assistant's native location selector and adjust the point manually.

All four paths end with exactly the same runtime configuration:

```text
mode = static
latitude = ...
longitude = ...
```

The acquisition method itself is not stored as another runtime mode.

## Current location entity

The integration exposes the current place as mutable state, for example:

```text
sensor.open_meteo_<source>_lokalizacja = Dortmund, DE
```

with attributes containing the accepted `latitude`, `longitude`, mode and last accepted location update.

The visible state can therefore remain `Dortmund, DE` while coordinates move within Dortmund. Entity identity does not change.

## Weather entity

The weather entity uses the Home Assistant 2026.8 native weather API and exposes current weather plus hourly/daily forecasts, including:

- temperature and apparent temperature,
- humidity and dew point,
- pressure,
- wind speed, direction and gusts,
- visibility,
- cloud coverage,
- UV index,
- precipitation and weather condition.

Forecast dictionaries use current Home Assistant `native_*` forecast fields.

## Sensors

Weather sensors include temperature, apparent temperature, humidity, pressure, dew point, wind, precipitation, rain, snowfall, precipitation probability, visibility, sunrise/sunset, UV and current location.

Air-quality sensors include PM2.5, PM10, CO, NO₂, SO₂, O₃, US AQI and European AQI.

Open-Meteo reports hourly `snowfall` in **centimeters**; V2 exposes that value as `cm`.

## API behavior

Weather data comes from Open-Meteo. Air Quality is optional: an AQ failure does not take the weather entity down, and entries with no AQ sensors enabled do not call the Air Quality endpoint.

Reverse and forward geocoding use OpenStreetMap Nominatim through Home Assistant's shared HTTP session.

For tracking entries, reverse geocoding is rate-limited separately from weather refreshes. Large location jumps can bypass the cooldown so the UI does not remain labeled with the previous city. If reverse geocoding fails after a large jump, presentation falls back to coordinates rather than keeping a false old city name.

## Development and tests

CI currently targets:

```text
Home Assistant 2026.8.0
Python 3.14
pytest-homeassistant-custom-component 0.13.354
```

The workflow checks dependency consistency, compiles component/test Python sources, validates HACS/manifest/translation JSON and runs the full pytest suite through Home Assistant's custom-integration test harness.

Coverage includes identity invariants, event-driven tracking, Lotte -> Dortmund -> Osnabrück movement, tracker-unavailable behavior, API contracts, AQ request policy, sensor units, native forecasts, config/options flows, static-location acquisition paths, translation resources and full setup -> movement -> registry -> unload lifecycle.

Run locally with:

```bash
python -m pip install -r requirements.txt
pytest -q
```

## License

Apache License 2.0.

Weather and air-quality data are provided by Open-Meteo. Forward/reverse geocoding uses OpenStreetMap Nominatim.
