## 1.6.0a19 ⚡ **ALPHA - PV Forecasting**

**⚠️ Alpha Release - Requires Testing**

This alpha release introduces **optional PV (photovoltaic) production forecasting** functionality. This feature is experimental and requires real-world testing.

### ✨ What's New
- **PV Production Forecasting:** Calculate solar power production forecasts based on solar radiation data from Open-Meteo API
- **Smart Appliance Automation:** Binary sensor that indicates when there's sufficient PV production to run appliances (washing machine, dishwasher, dryer)
- **7 New PV Sensors:**
  - `sensor.pv_produkcja_teraz` - Current PV production estimate (kW)
  - `sensor.pv_prognoza_1h` - 1-hour forecast (kWh)
  - `sensor.pv_prognoza_3h` - 3-hour forecast (kWh)
  - `sensor.pv_prognoza_6h` - 6-hour forecast (kWh)
  - `sensor.pv_prognoza_dzis` - Today's forecast until end of day (kWh)
  - `sensor.pv_min_3h` - Minimum production in next 3 hours (kW)
  - `sensor.pv_sr_3h` - Average production in next 3 hours (kW)
- **1 New Binary Sensor:**
  - `binary_sensor.pv_gotowe_agd` - "Appliances Ready" - ON when avg production ≥ 1000W and min ≥ 600W over next 3h
  - Includes detailed attributes: `avg_production_w`, `min_production_w`, `total_3h_kwh`, `confidence`, `reasoning`

### 🔧 Configuration Options
New optional PV configuration section in config flow:
- **pv_enabled** (bool) - Enable PV forecasting (default: False)
- **pv_power_kwp** (float) - Installation power in kWp (default: 5.0, range: 0.5-50)
- **pv_azimuth** (int) - Panel azimuth in degrees (default: 180=south, range: 0-360)
- **pv_tilt** (int) - Panel tilt angle (default: 35°, range: 0-90)
- **pv_efficiency** (float) - System efficiency (default: 0.85, range: 0.5-1.0)

### 🌤️ New API Parameters
Extended hourly forecast with solar radiation parameters:
- `direct_radiation` - Direct solar radiation (W/m²)
- `diffuse_radiation` - Diffuse solar radiation (W/m²)
- `direct_normal_irradiance` - DNI (W/m²)
- `shortwave_radiation` - GHI - Global Horizontal Irradiance (W/m²)
- `sunshine_duration` - Duration of sunshine (seconds)

### 📦 Technical Details
- **New file:** `binary_sensor.py` - Platform for PV appliances ready binary sensor
- **Modified:** `coordinator.py` - Added `_calculate_pv_production()` method (263 lines) with graceful degradation
- **Modified:** `sensor.py` - Added 7 PV sensor definitions
- **Modified:** `config_flow.py` - Added PV configuration section
- **Modified:** `const.py` - Extended `DEFAULT_HOURLY_VARIABLES`, added PV constants
- **Modified:** `pl.json`, `en.json` - Added PV translations and descriptions

### ⚠️ Important Notes
- **REQUIRES TESTING** - This feature needs validation with real PV installations
- **Backward Compatible** - When `pv_enabled = False` (default), no changes to existing behavior
- **Graceful Degradation** - If radiation data is unavailable, sensors return 0 with error indication
- **Night Detection** - Production is 0 when sun is down (hour < 6 or > 20, or sunshine_duration = 0)

### 🎯 Use Case
Example automation using the new binary sensor:
```yaml
automation:
  - alias: "Run washing machine when PV is ready"
    trigger:
      - platform: state
        entity_id: binary_sensor.pv_gotowe_agd
        to: "on"
    condition:
      - condition: time
        after: "10:00"
        before: "14:00"
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.washing_machine
```

### 📝 TODO for Stable Release
- [ ] Real-world testing with actual PV installations
- [ ] Validation of production calculation accuracy
- [ ] User feedback on appliances ready thresholds
- [ ] Documentation update with automation examples

---

## 1.6.0 🎉

**First stable release of 1.6.x series!**

This release brings significant code quality improvements, better type safety, and completely modernized documentation.

### ✨ What's New
- **Production-ready code:** Comprehensive refactoring with type hints and better error handling
- **Modern documentation:** Complete README rewrite with examples, FAQ, and troubleshooting
- **Better maintainability:** Split complex functions into focused, testable methods
- **Improved reliability:** Specific exception handling and detailed logging

### 🔧 Technical Improvements
- Added comprehensive type hints throughout coordinator module (ConfigEntry, return types, args)
- Refactored 200+ line `_async_update_data` into 4 focused helper methods:
  - `_update_coordinates_from_tracker()` - GPS tracking coordinate updates
  - `_update_coordinates_static()` - Static mode coordinate updates
  - `_update_location_name()` - Reverse geocoding with cooldown logic
- Replaced broad `except Exception` with specific exception types (aiohttp.ClientError, asyncio.TimeoutError, etc.)
- Added detailed docstrings explaining retry logic, backoff timing, and cooldowns
- Documented magic numbers and exponential backoff formula (1.5^n + jitter)

### 📚 Documentation Overhaul
- Complete README.md rewrite with modern structure and badges
- Added comprehensive sensor tables (17 weather + 8 air quality sensors)
- Included collapsible sections for better navigation
- Added FAQ/troubleshooting section with common issues
- Documented performance optimizations and battery saving tips
- Included Lovelace card examples (basic + advanced)

### 🐛 Bug Fixes
- Improved GPS tracking fallback behavior
- Better handling of missing air quality data
- More robust network error recovery

### 📦 Changed Files
- `coordinator.py` - Refactored and type-hinted
- `manifest.json` - Version 1.6.0
- `const.py` - Updated user agent
- `CHANGELOG.md` - Release notes
- `README.md` - Complete rewrite

---


## 1.6.0a18
- refactor(coordinator): Add comprehensive type hints to improve type safety
- refactor(coordinator): Split long `_async_update_data` method into smaller, focused helper methods:
  - `_update_coordinates_from_tracker()` - GPS tracking coordinate updates
  - `_update_coordinates_static()` - Static mode coordinate updates
  - `_update_location_name()` - Reverse geocoding with cooldown logic
- improve(error-handling): Replace broad `except Exception` with specific exception types
- improve(docs): Add detailed docstrings explaining retry logic, backoff timing, and cooldowns
- improve(docs): Document magic numbers and exponential backoff formula in retry logic

## 1.6.0a10
- Grouped sensor selection (Weather vs AQ).

## 1.6.0a8
- feat(config): Add selectable sensors (multi-select) in config/options.

## 1.4.72
- feat(options): unify cooldown jednostki – `options_save_cooldown` w minutach (UI), z pełnym fallbackiem do legacy `*_sec`.
- feat(i18n): tłumaczenia PL/EN zaktualizowane (etykiety + opisy) pod nowe pola.
- docs: README odświeżone do v1.4.71+ (TRACK cooldowns, stabilne entity_id, wskazówki baterii).

## 1.4.71
- docs: pełna aktualizacja README w stylu z ikonami, opis nowych opcji TRACK.
- chore(manifest): podbicie wersji.

## 1.4.70
- feat(ui): dodane opcje „Reverse geocode cooldown (min)” i „Options save cooldown (s)” w options flow (TRACK);
  w 1.4.72 zamienione na minuty.
- feat(i18n): etykiety i opisy po polsku i angielsku; lepsze zrozumienie w UI.
- feat(icons): wsparcie ikon – `hacs.json` i `manifest.json` wskazują `icon.png`.

## 1.4.39
- fix(weather): restore safe device-name initialization so setup works and devices use the resolved place name

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
