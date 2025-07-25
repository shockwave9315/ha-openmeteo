# Integracja Open-Meteo dla Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/hacs/integration)

Ta niestandardowa integracja dla Home Assistant pobiera dane pogodowe z darmowego i otwartego serwisu [Open-Meteo](https://open-meteo.com/).

## Główne funkcje

* **Encja pogody**: Kompletna encja `weather` z obecnymi warunkami oraz prognozą godzinową i dzienną.
* **Śledzenie wielu lokalizacji**: Automatyczne tworzenie osobnych encji pogodowych dla śledzonych urządzeń (np. telefonów).
* **Konfigurowalne nazwy obszarów**: Możliwość nadpisywania nazw obszarów dla lepszej identyfikacji lokalizacji.
* **Dodatkowe sensory**: Integracja tworzy szereg użytecznych sensorów, gotowych do użycia w automatyzacjach i na panelach, w tym:
    * Temperatura
    * Temperatura odczuwalna
    * Wilgotność
    * Ciśnienie
    * Prędkość i porywy wiatru
    * Kierunek wiatru
    * Widzialność
    * Indeks UV
    * Prawdopodobieństwo opadów
    * Suma opadów (deszcz + śnieg)

## Instalacja (Rekomendowana: HACS)

1.  Upewnij się, że masz zainstalowany [HACS](https://hacs.xyz/).
2.  Przejdź do **HACS > Integrations**.
3.  Kliknij menu z trzema kropkami w prawym górnym rogu i wybierz **"Custom repositories"**.
4.  Wklej ten adres URL repozytorium: `https://github.com/shockwave9315/ha-openmeteo`
5.  Wybierz kategorię **"Integration"**.
6.  Kliknij **"Add"**.
7.  Znajdź "Open-Meteo" na liście i kliknij **"Install"**.
8.  Zrestartuj Home Assistant.

## Konfiguracja

### Podstawowa konfiguracja

1. Przejdź do **Ustawienia > Urządzenia i usługi**.
2. Kliknij **"+ Dodaj integrację"**.
3. Wyszukaj **"Open-Meteo"** i kliknij wynik.
4. W formularzu, który się pojawi, lokalizacja (szerokość i długość geograficzna) zostanie uzupełniona automatycznie na podstawie ustawień Twojego Home Assistant. Możesz nadać integracji własną nazwę.
5. Po zapisaniu, encje zostaną automatycznie dodane.

### Konfiguracja śledzenia urządzeń

Integracja obsługuje automatyczne śledzenie wielu lokalizacji na podstawie urządzeń w Twoim systemie:

1. Przejdź do **Ustawienia > Urządzenia i usługi**.
2. Znajdź i kliknij integrację **Open-Meteo**.
3. Kliknij przycisk **Opcje**.
4. Włącz opcję **Śledź urządzenia**.
5. Wybierz urządzenia, które chcesz śledzić z listy dostępnych trackerów.
6. Dla każdego urządzenia możesz dostosować nazwę obszaru, który będzie używany w interfejsie.
7. Opcjonalnie możesz włączyć/wyłączyć używanie nazw urządzeń zamiast nazw trackerów.

### Zaawansowane opcje konfiguracji

W ustawieniach integracji dostępne są następujące zaawansowane opcje:

- **Interwał aktualizacji** - Jak często mają być pobierane nowe dane pogodowe (domyślnie 30 minut).
- **Używaj nazw urządzeń** - Jeśli włączone, integracja będzie używać przyjaznych nazw urządzeń zamiast identyfikatorów trackerów.
- **Nadpisywanie nazw obszarów** - Pozwala na ręczne ustawienie przyjaznych nazw dla każdej lokalizacji.
- **Zmienne dzienne/godzinowe** - Wybór, które dane pogodowe mają być pobierane.

## Przykłady konfiguracji

### Przykładowa konfiguracja YAML

```yaml
# configuration.yaml
openmeteo:
  name: "Pogoda dom"
  latitude: "{{ states('zone.home').attributes.latitude }}"
  longitude: "{{ states('zone.home').attributes.longitude }}"
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
    - relativehumidity_2m
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
    - windspeed_10m_max
```

### Przykładowa karta Lovelace

Możesz łatwo stworzyć rozbudowaną kartę pogodową, łącząc kilka standardowych kart za pomocą `vertical-stack-in-card` (dostępnej w HACS).

![Przykład karty](https://user-images.githubusercontent.com/12345/67890.png)  ```yaml
type: custom:vertical-stack-in-card
title: Open-Meteo
cards:
  - type: entities
    show_header_toggle: false
    entities:
      - entity: weather.open_meteo # Upewnij się, że nazwa encji jest poprawna
        name: Pogoda teraz
      - entity: sensor.open_meteo_temperatura_odczuwalna
      - entity: sensor.open_meteo_indeks_uv
      - entity: sensor.open_meteo_prawdopodobienstwo_opadow
      - entity: sensor.open_meteo_suma_opadow_deszcz_snieg
  - type: custom:weather-chart-card # Wymaga zainstalowania "weather-chart-card" z HACS
    entity: weather.open_meteo
    chart_type: temperature-bar
