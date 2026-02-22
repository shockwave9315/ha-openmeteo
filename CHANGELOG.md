## 1.6.5

### Changed
- Removed legacy production forecasting functionality from the integration.
- Removed related options from config and options flow.
- Removed related entities and binary sensor platform.

### Added
- New weather sensor: `rain_current_hour` (`sensor.deszcz_biezaca_godzina`) – rain in current hour (mm).
- New weather sensor: `snow_current_hour` (`sensor.snieg_biezaca_godzina`) – snow in current hour (mm, based on Open-Meteo `snowfall`).

### Compatibility
- Existing precipitation sensor `precipitation_sum` remains unchanged and keeps existing entity IDs.
- Integration requests Open-Meteo hourly `rain` in addition to existing precipitation/snowfall fields.
