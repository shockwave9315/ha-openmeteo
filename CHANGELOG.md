## 1.3.45
- fix(stability): no entry updates/reloads during setup; cancel timers on unload
- feat(data): include hourly/daily in API call
- fix(sensors): current.* mapping; hourly-now values for apparent_temperature, cloud_cover, shortwave_radiation, dew_point fallback, visibility (km), precipitation, probability, wind_gust
- refactor: remove legacy current_weather usage

## 1.3.44
- fix: prevent post-setup reload loops; no entry updates outside migration; defer reverse-geocoding; cancel timers on unload.

## 1.3.41
- feat: remove global extra sensor option; extra sensors disabled by default
- fix: non-blocking options listener and network timeouts

## 1.3.39
- fix: pre-register entities to enforce object IDs; remove coordinate fallback in names

## 1.3.37
- feat: stałe entity_id bez miejscowości; domyślnie w nazwach dopisek lokalizacji; poprawione ikony i device_class; usunięto kod migracji

## 1.3.32
- fix: correct override handling, prevent coords as names, stabilize tests

## 1.3.31
- fix(naming): compute and store place for entities; weather name uses place only
- fix(naming): sensors use static labels and entity names; remove dynamic names
- fix: respect user device renames via registry; dispatch updates to entities

## 1.3.30
- fix(naming): sensor labels restored; respect user device renames; static mode always uses place (no toggle); stop writing device_info.name from entities; title remains place

## 1.3.28
- fix(naming): respect user device renames; keep place-driven names only when allowed; remove "Open-Meteo" remnants
- fix: expose and persist `use_place_as_device_name` option for existing entries
- fix: sensor labels with `has_entity_name=True`

## 1.3.27
- fix(sensor): reorder dataclass fields (Python 3.13) so required `value_fn` precedes optional fields; prevents import error
- chore: mark dataclass `kw_only=True` for forward compatibility

## 1.3.25
- feat: use reverse geocoded place name for entry titles; fallback to lat,lon only if geocode fails

## 1.3.20
- fix: per-entry coords/title; remove global coords cache; add diagnostics attributes

## 1.3.21
- feat(diagnostics): expose `om_source`, `om_coords_used`, `om_place_name` on weather (and sensors if present)
- fix(unload): remove per-entry store on `async_unload_entry` to avoid stale state

## 1.3.22
- fix: dynamically refresh entry title when coords change

## 1.3.23
- fix(tests): use async_update_entry for options in tests; unload entries
- fix(cleanup): track and unsubscribe timers/subscriptions on unload to avoid lingering timers
