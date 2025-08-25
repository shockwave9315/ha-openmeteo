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
