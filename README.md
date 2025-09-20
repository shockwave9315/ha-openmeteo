# 🌤 Open‑Meteo – Integracja dla Home Assistant (v1.4.71)

[Open‑Meteo](https://open-meteo.com/) — darmowe, szybkie API pogody **bez klucza API**.
Integracja dostarcza encję `weather` z bieżącą pogodą i prognozą oraz zestaw sensorów gotowych do automatyzacji.

---

## ✨ Co nowego w 1.4.x

- **Stabilne nazwy encji**: `weather.open_meteo` oraz czytelne, polskie ID sensorów (`sensor.open_meteo_cisnienie`, `sensor.open_meteo_temperatura`, ...).
- **Przyjazna nazwa z miejscowości** bez psucia `entity_id` — aktualizowana po dodaniu encji.
- **Tryb śledzenia (TRACK)** z bezpiecznym fallbackiem, gdy tracker chwilowo nie ma GPS.
- **Reverse‑geocode cooldown** (min) — ogranicza częstotliwość odświeżania nazwy miejscowości, oszczędzając baterię i dane.
- **Options save cooldown** (s) — ogranicza częste zapisy do rejestru ustawień HA.
- **Lepsze logowanie i odporność**: retry, time‑outy, zachowanie ostatnich poprawnych danych przy błędach sieci.
- **Tłumaczenia PL/EN** i czytelne opisy pól w UI.

---

## 🧩 Funkcje

- **Encja `weather`** z warunkami bieżącymi i prognozą **godzinową** oraz **dzienną**.
- **Sensory**: temperatura, wilgotność, ciśnienie, widzialność, wiatr (prędkość/porywy/kierunek), opady, prawdopodobieństwo opadów, punkt rosy (z API), UV.
- **Tryby lokalizacji**:
  - **Static** — stałe współrzędne;
  - **Tracker** — na podstawie `device_tracker` / `person` (GPS), z automatycznym fallbackiem.

---

## 📥 Instalacja (HACS – Custom Repository)

1. Zainstaluj [HACS](https://hacs.xyz/).
2. HACS → **Integrations** → menu ⋮ → **Custom repositories**.
3. Dodaj repozytorium:
   ```
   https://github.com/shockwave9315/ha-openmeteo
   ```
4. Kategoria: **Integration** → **Add**.
5. Zainstaluj „Open‑Meteo” i **zrestartuj Home Assistant**.

---

## ⚙️ Konfiguracja

### 🔹 Pierwsze uruchomienie (UI)

1. **Ustawienia → Urządzenia i usługi → + Dodaj integrację** → „Open‑Meteo”.
2. Wybierz **tryb lokalizacji**:
   - **Static** — podaj `latitude` i `longitude` (domyślnie pobierane z HA),
   - **Tracker** — wskaż encję `device_tracker` lub `person` **z GPS**.
3. Ustaw opcje (interwał aktualizacji, jednostki, nazwa obszaru). W trybie **Tracker** zobaczysz dodatkowo:
   - „Odstęp odświeżania nazwy miejsca (min)” — reverse‑geocode cooldown,
   - „Odstęp zapisu ustawień (min)” — options save cooldown,
   - „Użyj nazwy miejsca jako nazwy urządzenia”.

> **Options flow jest dwukrokowy** — najpierw wybór trybu (**Static / Tracker**), potem pola właściwe dla danego trybu.

### 🔹 Tryb śledzenia (TRACK)

- Rekomendowane encje: `person.<twoja_osoba>` (agreguje trackery i zwykle ma GPS) lub `device_tracker.<telefon>` z aplikacji mobilnej HA (**source_type: gps**).
- Jeśli tracker **nie ma GPS**, integracja:
  - loguje **1× WARNING** i używa **fallbacku** (Twoje konfigur. współrzędne / ostatnie znane),
  - po powrocie GPS loguje **1× INFO** i wraca do trackera.
- Dla oszczędzania baterii:
  - ustaw **min. odstęp śledzenia** (np. 15 min),
  - ustaw **reverse‑geocode cooldown** (np. 15–30 min).

### 🔹 Tryb statyczny (STATIC)

- Użyj stałych współrzędnych — np. dom, działka, domek letniskowy.
- Pola z cooldownami nie są tu potrzebne i nie będą widoczne.

---

## 🔍 Debug i testy

- **Stany**: Narzędzia deweloperskie → **Stany** → `weather.open_meteo*` i `sensor.open_meteo_*`.
- **Prognoza**: Usługa `weather.get_forecasts` (`type: hourly` / `daily`).
- **Logi**: `custom_components.openmeteo.coordinator` (retry, ostrzeżenia o GPS, itp.).

> Tip (Android/MIUI): w aplikacji HA włącz **Autostart**, **Bez ograniczeń** (bateria), **Lokalizacja: Zawsze**, a aplikację „zablokuj” w ostatnich.

---

## 🎨 Przykładowe karty Lovelace

> Wymaga: [Mushroom Cards](https://github.com/piitaya/lovelace-mushroom), [ApexCharts Card](https://github.com/RomRider/apexcharts-card), [Bar Card](https://github.com/custom-cards/bar-card)

```yaml
type: custom:stack-in-card
mode: vertical
cards:
  - type: custom:mushroom-title-card
    title: Open‑Meteo – Dom
    subtitle: "{{ states('weather.open_meteo') | title }} • {{ state_attr('weather.open_meteo','temperature') }}°C"

  - type: custom:mushroom-chips-card
    chips:
      - type: weather
        entity: weather.open_meteo
      - type: entity
        entity: sensor.open_meteo_indeks_uv
        name: UV
      - type: entity
        entity: sensor.open_meteo_prawdopodobienstwo_opadow
        name: Opady %
      - type: entity
        entity: sensor.open_meteo_wiatr
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
      - entity: sensor.open_meteo_wiatr
        name: Wiatr [km/h]
        min: 0
        max: 80
```

---

## 🗒️ Changelog skrót (1.4.x)

- Stabilne `entity_id` dla encji pogody i sensorów, migracje rejestru encji.
- Uporządkowane nazewnictwo i tłumaczenia PL/EN w UI.
- Reverse‑geocode cooldown i options save cooldown (w minutach) w trybie **TRACK**.
- Zabezpieczenia na błędy API i sieci, cache ostatnich danych.

---

## 📄 Licencja

Apache License 2.0

Projekt licencjonowany na warunkach **Apache‑2.0**. Pełny tekst w `LICENSE`.  
Jeżeli rozpowszechniasz binaria lub modyfikacje, dołącz plik `NOTICE`.

