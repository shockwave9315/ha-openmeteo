# 🌤 Open-Meteo – Integracja dla Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://hacs.xyz/)  
📡 **Źródło danych:** [Open-Meteo](https://open-meteo.com/) – darmowa, szybka i bez klucza API.

---

## ✨ Główne funkcje

- **Encja `weather`** z bieżącymi warunkami i prognozą *godzinową + dzienną*.
- **Śledzenie wielu lokalizacji** – automatyczne tworzenie encji pogodowych dla trackerów (np. telefonów).
- **Przyjazne nazwy obszarów** – nadpisywanie nazw lokalizacji w interfejsie.
- **Dodatkowe sensory** gotowe do automatyzacji:
  - 🌡 Temperatura + odczuwalna
  - 💧 Wilgotność
  - 📉 Ciśnienie
  - 🌬 Prędkość i porywy wiatru + kierunek
  - 👁 Widzialność
  - ☀️ Indeks UV
  - 🌧 Prawdopodobieństwo opadów
  - 🌦 Suma opadów (deszcz + śnieg)

---

## 📥 Instalacja (HACS)

1. Upewnij się, że masz [HACS](https://hacs.xyz/).
2. W HACS → **Integrations** → menu ⋮ → **Custom repositories**.
3. URL repozytorium:  
   ```
   https://github.com/shockwave9315/ha-openmeteoo00sdsdeh
   ```
4. Kategoria: **Integration** → **Add**.
5. Zainstaluj „Open-Meteo” i zrestartuj Home Assistant.

---

## ⚙️ Konfiguracja

### 🔹 Podstawowa
1. **Ustawienia → Urządzenia i usługi → + Dodaj integrację**.
2. Wyszukaj „Open-Meteo” → wybierz.
3. Lokalizacja uzupełni się automatycznie (na podstawie HA) – możesz zmienić.
4. Nadaj własną nazwę i zapisz.

### 🔹 Śledzenie urządzeń
1. **Ustawienia → Urządzenia i usługi → Open-Meteo → Opcje**.
2. Włącz „Śledź urządzenia” i wybierz trackery.
3. Opcjonalnie: nadpisz nazwę obszaru, używaj nazw urządzeń.

*Options flow jest dwukrokowy: najpierw wybór trybu (Static/Tracker), potem odpowiednie pola.*

### 🔹 Opcje zaawansowane
- **Interwał aktualizacji** – domyślnie 30 min.
- **Zmienne godzinowe/dzienne** – wybierz, które dane pobierać.
- **Nadpisywanie nazw obszarów**.

---

## 📝 Przykład konfiguracji YAML

```yaml
openmeteo:
  name: "Pogoda dom"
  latitude: "{{ state_attr('zone.home','latitude') }}"
  longitude: "{{ state_attr('zone.home','longitude') }}"
  elevation: 120
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

## 🎨 Przykładowe karty Lovelace (ładne i kolorowe)

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
        color_threshold:
          - value: -10
            color: "#7aa2f7"
          - value: 0
            color: "#89b4fa"
          - value: 10
            color: "#a6e3a1"
          - value: 20
            color: "#f9e2af"
          - value: 26
            color: "#fab387"
          - value: 30
            color: "#f38ba8"

  - type: custom:bar-card
    entities:
      - entity: sensor.open_meteo_wiatr_predkosc
        name: Wiatr [km/h]
        min: 0
        max: 80
        severity:
          - from: 0
            to: 20
            color: "#a6e3a1"
          - from: 20
            to: 40
            color: "#f9e2af"
          - from: 40
            to: 80
            color: "#f38ba8"
```

---

## 📌 Uwagi
- Dane dostarcza **Open-Meteo.com** – brak limitu zapytań.
- Wszystkie kolory, progi i układ możesz dowolnie modyfikować.
- Możesz tworzyć osobne karty dla różnych lokalizacji (np. dom, praca, wakacje).
