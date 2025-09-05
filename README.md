# 🌤 Open-Meteo – Integracja dla Home Assistant (v1.3.19)

[Open-Meteo](https://open-meteo.com/) — darmowe, szybkie API pogody **bez klucza API**.  
Integracja dostarcza encję `weather` z bieżącą pogodą i prognozą oraz zestaw sensorów do automatyzacji.

---

## ✨ Funkcje

- **Encja `weather`** z bieżącymi warunkami i prognozą **godzinową** oraz **dzienną**.
- **Tryb lokalizacji**:
  - **Static** — stałe współrzędne,
  - **Tracker** — z encji `device_tracker` / `person` (GPS) z **automatycznym fallbackiem**.
- **Punkt rosy** z API: `dewpoint_2m` (bez lokalnych obliczeń).
- **Sensory pomocnicze** (łatwe do automatyzacji): temperatura, wilgotność, ciśnienie, wiatr (prędkość / porywy / kierunek), widzialność, Indeks UV (godzinowy), opady i ich prawdopodobieństwo.

---

## 📥 Instalacja (HACS – Custom Repository)

1. Zainstaluj [HACS](https://hacs.xyz/).
2. HACS → **Integrations** → menu ⋮ → **Custom repositories**.
3. URL repozytorium:
   ```
   https://github.com/shockwave9315/ha-openmeteo
   ```
4. Kategoria: **Integration** → **Add**.
5. Zainstaluj „Open-Meteo” i **zrestartuj Home Assistant**.

---

## ⚙️ Konfiguracja

### 🔹 Pierwsze uruchomienie (UI)

1. **Ustawienia → Urządzenia i usługi → + Dodaj integrację** → „Open-Meteo”.
2. Wybierz **tryb lokalizacji**:
   - **Static** — podaj `latitude` i `longitude` (domyślnie pobierane z Home Assistant).
   - **Tracker** — wskaż encję `device_tracker` lub `person` **z GPS**.
3. Ustaw opcje (interwał odświeżania, zmienne hourly/daily, nazwa obszaru) i zapisz.

> **Options flow jest dwukrokowy:** najpierw wybór trybu (**Static / Tracker**), potem tylko pola dla wybranego trybu.  
> W trybie **Tracker** encja musi mieć atrybuty `latitude` i `longitude`. Trackery „routerowe” (np. UniFi/DHCP) **nie** mają GPS → wybierz `person.*` albo tracker z aplikacji mobilnej HA (*source_type: gps*).

### 🔹 Śledzenie urządzeń (Tracker)

- Rekomendowane encje:
  - `person.<twoja_osoba>` (agreguje trackery i zwykle ma GPS), lub
  - `device_tracker.<telefon>` z aplikacji mobilnej HA (**source_type: gps**).
- Gdy wybrany tracker **nie ma GPS**, integracja loguje **1× WARNING** i używa **fallbacku** (Twoje współrzędne z opcji lub `Home`). Gdy GPS wróci — **1× INFO** i powrót do trackera.

### 🔹 Tryb statyczny

- Wpisz stałe współrzędne. Dobre do stacji domowej, domku letniskowego itp.

---

## 🧪 Testy i debug

### Run tests

```bash
python -m pip install -U pip
python -m pip install -r requirements_test.txt
pytest -q
```

- **Bieżące atrybuty**: Narzędzia deweloperskie → **Stany** → `weather.open_meteo_*`
  Sprawdź `temperature`, `humidity`, **`dew_point`**, itd.
- **Prognoza godzinowa / dzienna**: Narzędzia deweloperskie → **Usługi** → `weather.get_forecasts`  
  Parametry:
  ```yaml
  entity_id: weather.open_meteo_home
  type: hourly   # lub: daily
  ```
- **Logi**: `custom_components.openmeteo.coordinator`  
  - `WARNING` — wybrany tracker bez GPS → użyto fallbacku,  
  - `INFO` — powrót z fallbacku do GPS.

> **MIUI/Android tipy**: dla aplikacji HA włącz **Autostart**, **Bez ograniczeń** (bateria), **Lokalizacja: Zawsze** i „zablokuj” apkę kłódką w Ostatnich.

---

## 📝 Przykład konfiguracji YAML (opcjonalnie)

> Integracja jest konfigurowana przez UI. Poniższy YAML to tylko przykład użycia list zmiennych **hourly/daily**.

```yaml
openmeteo:
  name: "Pogoda dom"
  latitude: "{{ state_attr('zone.home', 'latitude') }}"
  longitude: "{{ state_attr('zone.home', 'longitude') }}"
  time_zone: "Europe/Warsaw"
  scan_interval: 1800
  track_devices: true
  use_device_names: true
  device_trackers:
    - device_tracker.phone_1
    - device_tracker.phone_2
  area_overrides:
    device_tracker.phone_1: "Praca"
    device_tracker.phone_2: "Wakacje"

  hourly_variables:
    - temperature_2m
    - relative_humidity_2m
    - dewpoint_2m
    - precipitation
    - precipitation_probability
    - pressure_msl
    - cloud_cover
    - wind_speed_10m
    - wind_gusts_10m
    - wind_direction_10m
    - visibility
    - weathercode

  daily_variables:
    - weathercode
    - temperature_2m_max
    - temperature_2m_min
    - sunrise
    - sunset
    - precipitation_sum
    - precipitation_hours
    - precipitation_probability_max
    - wind_speed_10m_max
```

---

## 🎨 Przykładowe karty Lovelace

> Wymaga: [Mushroom Cards](https://github.com/piitaya/lovelace-mushroom), [ApexCharts Card](https://github.com/RomRider/apexcharts-card), [Bar Card](https://github.com/custom-cards/bar-card)

```yaml
type: custom:stack-in-card
mode: vertical
cards:
  - type: custom:mushroom-title-card
    title: Open-Meteo – Dom
    subtitle: "{{ states('weather.open_meteo_home') | title }}  •  {{ state_attr('weather.open_meteo_home','temperature') }}°C"

  - type: custom:mushroom-chips-card
    chips:
      - type: weather
        entity: weather.open_meteo_home
      - type: entity
        entity: sensor.open_meteo_indeks_uv
        name: UV
      - type: entity
        entity: sensor.open_meteo_prawdopodobienstwo_opadow
        name: Opady %
      - type: entity
        entity: sensor.open_meteo_wiatr_predkosc
        name: Wiatr
      - type: entity
        entity: sensor.open_meteo_cisnienie
        name: Ciśnienie

  - type: custom:apexcharts-card
    header:
      show: true
      title: Temperatura (24h)
    graph_span: 24h
    series:
      - entity: sensor.open_meteo_temperatura
        type: line
        stroke_width: 3

  - type: custom:bar-card
    entities:
      - entity: sensor.open_meteo_wiatr_predkosc
        name: Wiatr [km/h]
        min: 0
        max: 80
```

---

## 📚 Słowniczek (PL → EN) – debug GPS

- **dryf** (*drift*) — powolne, systematyczne odjeżdżanie pozycji.  
  _Tip:_ próg dystansu (`distance_threshold_m`).

- **szum** (*jitter*) — szybkie, losowe skoki pozycji.  
  _Tip:_ zaokrąglanie (`round_decimals`) + próg dystansu.

- **fallback** — zapasowe współrzędne, gdy tracker nie ma GPS.  
  _Tip:_ loguj 1× WARNING przy wejściu, 1× INFO przy powrocie.

- **histereza** (*hysteresis*) — „zatrzask” progowy zmian.  
- **debounce** — ignorowanie krótkich zmian przez X s/min.  
- **throttle / rate-limit** — minimalny odstęp między aktualizacjami (np. `min_track_interval`).  
- **stale** — dane przeterminowane; użyj ostatniego dobrego fixa lub fallback.  
- **snap to zone** — „przyklej” pozycję do środka strefy (Home/Work) w promieniu R.  
- **Haversine** — odległość po kuli ziemskiej między punktami (lat/lon).  
- **gps accuracy** — dokładność fixa (m); odrzucaj zbyt słabe fixy.

---

## 🗒️ Changelog

### 1.3.19
- Uproszczono obsługę UV – pozostaje tylko jeden sensor godzinowy.

### 1.3.9
- **Punkt rosy** z API (`dewpoint_2m`) — usunięto lokalne liczenie.
- **Prognoza godzinowa** — poprawna implementacja `async_forecast_hourly` + mapowanie `weathercode`.
- **Options flow 2-krokowy** — najpierw tryb (*Static/Tracker*), potem odpowiednie pola.
- **Fallback GPS** — jedno ostrzeżenie przy braku GPS, jedno INFO przy powrocie.

---

## 📄 Licencja

Apache License 2.0

Ten projekt jest licencjonowany na warunkach **Apache-2.0**. Pełny tekst licencji znajdziesz w pliku `LICENSE`. 
Jeżeli rozpowszechniasz binaria lub modyfikacje, dołącz plik `NOTICE`.

