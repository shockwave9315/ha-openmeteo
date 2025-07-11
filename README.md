# Integracja Open-Meteo dla Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/hacs/integration)

Ta niestandardowa integracja dla Home Assistant pobiera dane pogodowe z darmowego i otwartego serwisu [Open-Meteo](https://open-meteo.com/).

## Główne funkcje

* **Encja pogody**: Kompletna encja `weather` z obecnymi warunkami oraz prognozą godzinową i dzienną.
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

1.  Przejdź do **Ustawienia > Urządzenia i usługi**.
2.  Kliknij **"+ Dodaj integrację"**.
3.  Wyszukaj **"Open-Meteo"** i kliknij wynik.
4.  W formularzu, który się pojawi, lokalizacja (szerokość i długość geograficzna) zostanie uzupełniona automatycznie na podstawie ustawień Twojego Home Assistant. Możesz nadać integracji własną nazwę.
5.  Po zapisaniu, encje zostaną automatycznie dodane.

## Przykładowa karta Lovelace

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
