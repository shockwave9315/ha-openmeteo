# Changelog

## 2.0.0-dev.0 — V2 architecture rewrite

Development branch: `rewrite/v2-architecture`. Not released yet.

### Architecture
- Rebuilt config-entry lifecycle around `ConfigEntry.runtime_data` and per-entry Home Assistant storage.
- Separated stable source identity from mutable current location and UI presentation names.
- Moved active runtime GPS/place persistence out of config-entry `data` and `options` into per-entry storage; frozen V1 `last_*` values are temporarily retained only as a rollback snapshot.
- Split the monolithic implementation into dedicated API, location, identity, runtime, coordinator and entity layers.

### Tracking
- Added event-driven tracker updates through Home Assistant state-change events.
- Ignore GPS jitter below roughly 50 m.
- Throttle small location changes with one delayed follow-up refresh.
- Accept large jumps (>=10 km) immediately even inside the configured tracking interval.
- Added a regression test for a tracker moving from Lotte to Dortmund without changing entity identity.
- A tracking entry with no live GPS and no stored last position stays not-ready instead of falling back to Home Assistant's home coordinates.

### Entity identity and migration
- Added a persisted stable `source_key` for every entry.
- Preserve V1 registry `unique_id` values to avoid duplicate entities and broken dashboards during migration.
- Do not auto-rename existing entity IDs.
- New entries receive source-scoped stable object IDs independent of the current city.
- V2 remains on config-entry major version 3 and migrates to minor version 3.2 so first live testing remains rollback-safe with the V1.7.x line.
- Legacy V1/V3 config is canonicalized while frozen `last_lat`, `last_lon` and `last_location_name` values are retained as an inert rollback snapshot; V2 never updates them.

### Home Assistant 2026.8
- Weather forecasts now use the current native forecast field contract.
- Weather entity exposes apparent temperature, wind gusts, cloud coverage and UV index in addition to existing values.
- CI targets Home Assistant 2026.8.0 and Python 3.14.
- User config-flow tests run through Home Assistant's real custom-integration loader.
- Entity IDs are supplied through the HA 2026.8 entity-platform path that keeps the integration-suggested object ID independent of the mutable device name.

### Open-Meteo API
- Replaced legacy `weathercode` / `dewpoint_2m` usage with `weather_code` / `dew_point_2m`.
- Removed the invalid Open-Meteo reverse-geocoding endpoint call; reverse geocoding is isolated to Nominatim.
- Weather failures remain fatal to the coordinator update; Air Quality failures are best effort.
- Entries with no enabled AQ sensors no longer call the Air Quality endpoint.

### Sensors
- Rebuilt sensors around one generic coordinator-backed entity implementation.
- Current location is exposed as place state with coordinates as attributes.
- Corrected Open-Meteo snowfall unit from the V1 `mm` label to the API's actual `cm` unit.
- Updated sensor device classes and the HA 2026.8 ppm unit API.

### Configuration UI
- Simplified setup to Static or Tracking mode.
- Static mode uses Home Assistant's native location selector.
- Tracking mode uses a `person`/`device_tracker` entity selector.
- Tracker coordinate validation is shared by setup and options flows.
- Removed obsolete/fake unit/provider configuration and old postcode/place-search flow.

### Tests and CI
- Replaced V1 architecture tests with V2 behavior/contract tests, including full setup → movement → registry → unload lifecycle coverage.
- Added an upgrade test proving existing V1 registry IDs survive migration and movement without duplicate entities.
- CI checks dependencies, compiles component/test Python sources, validates HACS/manifest/translation JSON and runs the full pytest suite.

### Cleanup
- Removed old naming/registry self-renaming machinery.
- Removed stale duplicate translation files and rewrote PL/EN V2 translations.
- Removed obsolete V1 tests that encoded retired architecture and replaced them with V2 behavior/contract tests.
- Removed the ineffective `icon` key from the manifest; V2 brand assets will use Home Assistant's local `brand/` mechanism before release.

## 1.7.1
- Home Assistant 2026.8 compatibility fixes on the stable V1 line.
- Replaced deprecated ppm constant usage.
- Modernized test stack for HA 2026.8 / Python 3.14.
- Replaced `async_timeout` with native `asyncio.timeout()`.

## 1.6.5
- Added separate rain and snowfall current-hour sensors.
- Historical note: V1 exposed Open-Meteo `snowfall` as mm; V2 corrects this to cm.
