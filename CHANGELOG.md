## 1.3.54
- fix(flow): pełny wybór trybu i komplet wspólnych pól w kreatorze oraz w Opcjach (stałe z const, bez `options=`)
- chore(names): utrzymano dynamiczne friendly_name bez prefiksu "Open-Meteo"
- chore: brak api_provider, brak async_reload, parametry hourly/daily bez zmian

## 1.3.52
- fix(flow): poprawiono create_entry (bez options=), dodano re-eksport OptionsFlow w __init__, bezpieczne selektory
- feat(names): dynamiczne friendly_name dla wszystkich sensorów i encji pogodowej (aktualna miejscowość; entity_id bez zmian)
- feat(device): device name w Device Registry synchronizuje się z bieżącą lokalizacją (reverse geocode); brak prefiksu
- chore: brak api_provider, brak async_reload, parametry hourly/daily bez zmian

## 1.3.51
- fix(flow): poprawny import selektorów (moduł `homeassistant.helpers.selector as sel`); zamiana `selector.EntitySelector` na bezpieczny helper; brak crasha przy dodawaniu kolejnego wpisu
- fix(options): ekran Opcji otwiera się i zapisuje ustawienia (data → entry.options); `entity_id` ma fallback do `str`, jeśli selektory nie są dostępne
- chore: zachowano wcześniejsze poprawki (bez prefiksów, hourly/daily, brak api_provider, bez async_reload)

## 1.3.50
- fix: guard OptionsFlow and remove leftover references to removed fields; HA no longer crashes on startup
- fix(options): Options screen opens and saves correctly (data → entry.options)
- chore: keep no-prefix names; hourly/daily requests intact; no reloads during setup

## 1.3.49
- fix(options): w pełni działający OptionsFlow (edycja i zapis ustawień bez błędów)
- fix(names): usunięto prefiks „Open-Meteo — ” — urządzenie i encja pogodowa pokazują samą miejscowość (lub lat,lon)
- chore: zachowano stabilność (brak reloadów; update_entry tylko w migracji); hourly/daily pozostają w zapytaniach; sensory bez zmian

## 1.3.48
- fix(sensor): guard coordinator.show_place_name with getattr to prevent AttributeError in tests
- feat: dynamic friendly_name update based on current place_name (reverse geocode), entity_id remains unchanged
- chore: keep device name logic consistent with show_place_name option

## 1.3.47
- fix(options): correct OptionsFlow return (no `options=` arg); resolves "Unknown error occurred" when saving Options
- fix(data): include `hourly` and `daily` parameters in API request (UV, apparent temperature, visibility, wind gusts, POP, sunrise/sunset)
- feat(device): auto device name "Open-Meteo — {place}" (or "lat,lon") with live update after reverse geocoding
- chore: keep extra sensors removed; no reloads during setup

## 1.3.46
- fix: remove extra sensors (cloud_cover, solar_radiation, snow_depth) to prevent startup crashes
- chore: trim hourly request to only required variables
- keep: improved mappings for classic sensors (current.* + hourly-now)

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
