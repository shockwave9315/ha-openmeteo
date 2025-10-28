# 🌤️ Open-Meteo for Home Assistant

![Version](https://img.shields.io/badge/version-1.6.0a19-orange)
![License](https://img.shields.io/badge/license-Apache%202.0-green)
![HACS](https://img.shields.io/badge/HACS-Custom-orange)
![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024+-blue)

Darmowa, szybka integracja pogodowa dla Home Assistant wykorzystująca [Open-Meteo API](https://open-meteo.com/) — **bez klucza API, bez limitów!**

---

## ✨ Funkcje

- 🌡️ **Pogoda** - temperatura, wilgotność, ciśnienie, wiatr, opady
- 🔮 **Prognozy** - godzinowe (72h) i dzienne (7 dni)
- 💨 **Jakość powietrza** - PM2.5, PM10, CO, NO₂, SO₂, O₃, AQI (US/EU)
- 📍 **GPS Tracking** - śledź pogodę w lokalizacji osoby/urządzenia
- 🌍 **Geocoding** - automatyczne nazwy miejscowości z współrzędnych
- ⚡ **Wydajność** - cooldowny, retry, cache dla oszczędności baterii
- 🌐 **Dwujęzyczne** - pełne wsparcie PL/EN

---

## 🚀 Szybki start

### 1. **Instalacja przez HACS**

<details>
<summary><b>📥 Kliknij, aby rozwinąć instrukcję</b></summary>

1. Otwórz **HACS** w Home Assistant
2. Kliknij **Integrations**
3. Menu `⋮` (prawy górny róg) → **Custom repositories**
4. Wklej URL:
   ```
   https://github.com/shockwave9315/ha-openmeteo
   ```
5. Wybierz kategorię: **Integration**
6. Kliknij **Add**
7. Znajdź "**Open-Meteo**" na liście i kliknij **Download**
8. **Restartuj Home Assistant**

</details>

### 2. **Konfiguracja**

1. Przejdź do **Ustawienia** → **Urządzenia i usługi**
2. Kliknij **+ Dodaj integrację**
3. Wyszukaj "**Open-Meteo**"
4. Wybierz tryb:
   - **Static** - stałe współrzędne (dom, działka)
   - **Track** - śledź lokalizację osoby/urządzenia
5. Gotowe! 🎉

---

## 📋 Tryby lokalizacji

### 🏠 Tryb statyczny (Static)

Idealne dla stałej lokalizacji - domu, biura, działki.

**Konfiguracja:**
- Wpisz nazwę miejsca (np. "Warszawa") lub kod pocztowy
- System znajdzie lokalizację automatycznie
- Lub podaj dokładne współrzędne GPS

### 📱 Tryb śledzenia (Track)

Pogoda śledzi Twoją lokalizację w czasie rzeczywistym!

**Wymogi:**
- Encja `person.*` lub `device_tracker.*` z GPS
- Aplikacja Home Assistant Mobile z włączoną lokalizacją

**Ustawienia:**
- **Min. odstęp śledzenia** (15 min) - jak często aktualizować lokalizację
- **Reverse geocode cooldown** (15 min) - jak często pobierać nazwę miejsca
- **Options save cooldown** (1 min) - jak często zapisywać zmiany

**💡 Tip dla Android/MIUI:**
- Włącz **Autostart** dla aplikacji HA
- Ustaw baterię: **Bez ograniczeń**
- Lokalizacja: **Zawsze**
- "Zablokuj" aplikację w Recent Apps

---

## 🎯 Dostępne sensory

### ☁️ Sensory pogodowe

| Sensor | Opis | Jednostka |
|--------|------|-----------|
| 🌡️ Temperatura | Temperatura powietrza | °C |
| 🌡️ Temp. odczuwalna | Temperatura odczuwalna | °C |
| 💧 Wilgotność | Wilgotność względna | % |
| 📊 Ciśnienie | Ciśnienie atmosferyczne | hPa |
| 💎 Punkt rosy | Temperatura punktu rosy | °C |
| 💨 Wiatr | Prędkość wiatru | km/h |
| 💨 Porywy wiatru | Maksymalne porywy | km/h |
| 🧭 Kierunek wiatru | Kierunek wiatru | ° |
| 🌧️ Opady (1h) | Opady w bieżącej godzinie | mm |
| 🌧️ Opady (dzienna suma) | Suma opadów dziennych | mm |
| 🌧️ Opady (3h) | Suma opadów z 3h | mm |
| ☔ Prawdopodobieństwo opadów | Szansa na opady | % |
| 👁️ Widzialność | Widzialność | km |
| 🌅 Wschód słońca | Czas wschodu | timestamp |
| 🌇 Zachód słońca | Czas zachodu | timestamp |
| ☀️ Indeks UV | Promieniowanie UV | - |
| 📍 Lokalizacja | Współrzędne GPS | lat,lon |

### 🏭 Sensory jakości powietrza

| Sensor | Opis | Jednostka |
|--------|------|-----------|
| PM2.5 | Pyły zawieszone 2.5µm | µg/m³ |
| PM10 | Pyły zawieszone 10µm | µg/m³ |
| CO | Tlenek węgla | ppm |
| NO₂ | Dwutlenek azotu | µg/m³ |
| SO₂ | Dwutlenek siarki | µg/m³ |
| O₃ | Ozon | µg/m³ |
| US AQI | Indeks jakości powietrza (USA) | - |
| EU AQI | Indeks jakości powietrza (EU) | - |

### ⚡ Sensory fotowoltaiki (PV) - **OPCJONALNE**

**⚠️ Alpha - Wymaga testów w rzeczywistych warunkach**

<details>
<summary><b>📊 Kliknij, aby zobaczyć sensory PV</b></summary>

Funkcjonalność prognozowania produkcji PV pozwala automatycznie uruchamiać urządzenia AGD (pralka, zmywarka, suszarka) gdy jest wystarczająca produkcja energii słonecznej.

**Konfiguracja:**
1. W opcjach integracji włącz "Włącz przewidywanie produkcji PV"
2. Podaj parametry instalacji:
   - Moc instalacji (kWp)
   - Azymut paneli (180° = południe)
   - Nachylenie paneli (35° optymalne dla Polski)
   - Współczynnik sprawności (0.85 typowo)

**7 Sensorów prognozy:**

| Sensor | Opis | Jednostka |
|--------|------|-----------|
| ☀️ Produkcja PV (teraz) | Aktualne szacowanie produkcji | kW |
| 📈 Prognoza PV 1h | Prognoza na następną godzinę | kWh |
| 📈 Prognoza PV 3h | Suma produkcji w ciągu 3h | kWh |
| 📈 Prognoza PV 6h | Suma produkcji w ciągu 6h | kWh |
| 📈 Prognoza PV dziś | Suma do końca dnia | kWh |
| ⬇️ Min. produkcja PV 3h | Minimum w ciągu 3h | kW |
| 📊 Śr. produkcja PV 3h | Średnia w ciągu 3h | kW |

**1 Binary Sensor (automatyzacje):**

| Sensor | Opis | Wartość |
|--------|------|---------|
| 🔌 Gotowe do uruchomienia AGD | Czy uruchomić urządzenia? | ON/OFF |

**Atrybuty binary sensor:**
- `avg_production_w` - Średnia produkcja w następnych 3h (W)
- `min_production_w` - Minimalna produkcja w następnych 3h (W)
- `total_3h_kwh` - Całkowita energia w 3h (kWh)
- `confidence` - Poziom pewności (high/medium/low)
- `reasoning` - Wyjaśnienie decyzji

**Warunki włączenia:**
- Średnia produkcja w ciągu 3h ≥ 1000W
- Minimalna produkcja w ciągu 3h ≥ 600W (60% średniej)

**Przykładowa automatyzacja:**

```yaml
automation:
  - alias: "Uruchom pralkę gdy PV gotowe"
    description: "Automatyczne uruchomienie pralki przy wystarczającej produkcji PV"
    trigger:
      - platform: state
        entity_id: binary_sensor.pv_gotowe_agd
        to: "on"
        for: "00:05:00"  # Potwierdź przez 5 min
    condition:
      - condition: time
        after: "10:00"
        before: "14:00"
      - condition: state
        entity_id: input_boolean.pralka_czeka
        state: "on"
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.pralka_smartthings
      - service: notify.mobile_app
        data:
          message: "Pralka uruchomiona - produkcja PV: {{ state_attr('binary_sensor.pv_gotowe_agd', 'avg_production_w') }}W"
```

**Sekwencyjne uruchamianie urządzeń:**

```yaml
automation:
  - alias: "Sekwencja AGD z PV"
    trigger:
      - platform: state
        entity_id: binary_sensor.pv_gotowe_agd
        to: "on"
    action:
      # 1. Pralka (1.5h)
      - service: switch.turn_on
        target:
          entity_id: switch.pralka
      - delay: "01:30:00"
      # 2. Zmywarka (2h)
      - service: switch.turn_on
        target:
          entity_id: switch.zmywarka
      - delay: "02:00:00"
      # 3. Suszarka (1.5h)
      - service: switch.turn_on
        target:
          entity_id: switch.suszarka
```

**Uwagi:**
- Wymaga testowania z rzeczywistą instalacją PV
- Wartości progowe (1000W/600W) można dostosować do swoich potrzeb
- Nocą (< 6:00, > 20:00) produkcja = 0
- Gdy brak danych promieniowania, sensory zwracają 0 z błędem w atrybutach

</details>

---

## 🎨 Przykładowa karta Lovelace

### Podstawowa karta pogody

```yaml
type: weather-forecast
entity: weather.open_meteo
show_forecast: true
forecast_type: daily
```

### Zaawansowana karta (wymaga HACS)

<details>
<summary><b>🎭 Kliknij, aby zobaczyć kod</b></summary>

**Wymagane karty:**
- [Mushroom Cards](https://github.com/piitaya/lovelace-mushroom)
- [ApexCharts Card](https://github.com/RomRider/apexcharts-card)

```yaml
type: vertical-stack
cards:
  # Header z aktualną pogodą
  - type: custom:mushroom-title-card
    title: 🌤️ Pogoda
    subtitle: "{{ states('weather.open_meteo') | title }} • {{ state_attr('weather.open_meteo','temperature') }}°C"

  # Szybki podgląd najważniejszych danych
  - type: custom:mushroom-chips-card
    chips:
      - type: weather
        entity: weather.open_meteo
        show_conditions: true
        show_temperature: true
      - type: entity
        entity: sensor.promieniowanie_uv
        icon: mdi:weather-sunny-alert
        icon_color: orange
      - type: entity
        entity: sensor.prawdopodobienstwo_opadow
        icon: mdi:umbrella
        icon_color: blue
      - type: entity
        entity: sensor.wiatr
        icon: mdi:weather-windy
      - type: entity
        entity: sensor.cisnienie
        icon: mdi:gauge

  # Wykres temperatury
  - type: custom:apexcharts-card
    header:
      show: true
      title: 📈 Temperatura (24h)
    graph_span: 24h
    span:
      start: day
    series:
      - entity: sensor.temperatura
        name: Temperatura
        stroke_width: 2
        color: '#ff6b6b'
      - entity: sensor.temperatura_odczuwalna
        name: Odczuwalna
        stroke_width: 2
        color: '#4ecdc4'
        curve: smooth

  # Karta jakości powietrza
  - type: entities
    title: 🏭 Jakość powietrza
    entities:
      - entity: sensor.pm2_5_aq
        name: PM2.5
        icon: mdi:blur
      - entity: sensor.pm10_aq
        name: PM10
        icon: mdi:blur
      - entity: sensor.aqi_eu_aq
        name: European AQI
        icon: mdi:gauge
```

</details>

---

## ⚙️ Konfiguracja zaawansowana

### Opcje integracji

| Opcja | Opis | Domyślnie | Tryb |
|-------|------|-----------|------|
| **Interwał aktualizacji** | Jak często pobierać dane pogodowe | 10 min | Oba |
| **Jednostki** | Metryczne lub imperialne | Metryczne | Oba |
| **Nazwa miejsca** | Własna nazwa (opcjonalne) | Auto | Oba |
| **Min. odstęp śledzenia** | Min. czas między aktualizacjami GPS | 15 min | Track |
| **Reverse geocode cooldown** | Cooldown na pobieranie nazwy miejsca | 15 min | Track |
| **Options save cooldown** | Cooldown na zapis ustawień | 1 min | Track |

### Wybór sensorów

Możesz włączyć/wyłączyć dowolne sensory w opcjach integracji:
1. Przejdź do **Urządzenia i usługi** → **Open-Meteo**
2. Kliknij **Konfiguruj**
3. Wybierz sensory pogodowe i/lub jakości powietrza
4. Zapisz

---

## 🔧 Rozwiązywanie problemów

<details>
<summary><b>❓ Brak danych GPS w trybie Track</b></summary>

**Problem:** Sensory pokazują "unavailable" lub używają starych współrzędnych

**Rozwiązanie:**
1. Sprawdź czy encja trackera ma atrybuty `latitude` i `longitude`
2. W aplikacji HA Mobile: Ustawienia → Companion App → Włącz lokalizację
3. Android: Uprawnienia → Lokalizacja → Zawsze
4. Sprawdź logi: `custom_components.openmeteo.coordinator`

</details>

<details>
<summary><b>❓ Sensory jakości powietrza są niedostępne</b></summary>

**Problem:** Sensory AQ pokazują "unavailable"

**Przyczyna:** Open-Meteo Air Quality API może nie mieć danych dla wszystkich lokalizacji

**Rozwiązanie:**
- To normalne - nie wszystkie regiony mają dostępne dane AQ
- Sensory będą "unavailable" w miejscach bez pokrycia
- Sprawdź [Open-Meteo Air Quality](https://open-meteo.com/en/docs/air-quality-api)

</details>

<details>
<summary><b>❓ Nazwy encji się zmieniają</b></summary>

**Problem:** Entity ID zmienia się po zmianie lokalizacji

**Rozwiązanie:**
Od wersji 1.4+ używamy stabilnych ID:
- Weather: `weather.open_meteo`
- Sensory: `sensor.temperatura`, `sensor.cisnienie`, itp.

Jeśli masz starą wersję - zaktualizuj i uruchom ponownie konfigurację.

</details>

---

## 📊 Wydajność i bateria

Integracja jest zoptymalizowana pod kątem oszczędzania baterii:

| Feature | Opis |
|---------|------|
| ⏱️ **Cooldowny** | Ograniczają częstotliwość API calls |
| 🔄 **Retry z backoff** | Eksponencjalny backoff przy błędach (1s → 1.5s → 2.25s) |
| 💾 **Cache** | Zachowuje ostatnie dane przy błędach sieci |
| 📍 **GPS throttling** | Min. odstęp między aktualizacjami lokalizacji |
| 🌐 **Geocode cooldown** | Ogranicza reverse geocoding (oszczędność danych) |

---

## 🆕 Co nowego w 1.6.x

### ✨ Nowe funkcje
- ✅ Grupowane sensory (pogoda vs jakość powietrza) w UI
- ✅ Ulepszone type hints dla lepszej type safety
- ✅ Refaktoryzacja kodu - lepsze utrzymanie
- ✅ Szczegółowe docstringi i komentarze

### 🔧 Poprawki
- ✅ Bardziej precyzyjne exception handling
- ✅ Udokumentowane magic numbers i timing
- ✅ Split długich funkcji na mniejsze metody
- ✅ Lepsze logowanie z kontekstem

Pełen changelog: [CHANGELOG.md](CHANGELOG.md)

---

## 🤝 Wsparcie i rozwój

### Znalazłeś bug?
Zgłoś issue: [GitHub Issues](https://github.com/shockwave9315/ha-openmeteo/issues)

### Masz pomysł na feature?
Otwórz Feature Request: [GitHub Issues](https://github.com/shockwave9315/ha-openmeteo/issues/new)

### Chcesz pomóc?
Pull requesty są mile widziane! 🎉

---

## 📜 Licencja

**Apache License 2.0**

Projekt jest open-source na warunkach Apache 2.0.
Pełny tekst licencji: [LICENSE](LICENSE)

---

## 🙏 Podziękowania

- [Open-Meteo](https://open-meteo.com/) - za darmowe API
- Społeczność Home Assistant - za wsparcie i testy
- Wszyscy kontrybutorzy - za pull requesty i raporty bugów

---

<div align="center">

**Jeśli podoba Ci się ta integracja, zostaw ⭐ na GitHubie!**

Made with ❤️ for Home Assistant

</div>
