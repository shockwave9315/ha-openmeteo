# Audit jakościowy integracji `openmeteo` (etap rozpoznania)

Zakres: analiza kodu produkcyjnego i testów bez zmian funkcjonalnych/refaktoru.

## A. Must fix soon

### 1) Niespójny model `hass.data` i ryzyko ukrytych regresji
- **Plik/obszar:** `__init__.py` + `sensor.py`
- **Problem:** `__init__.py` zapisuje coordinator bezpośrednio pod `hass.data[DOMAIN][entry_id]`, ale `sensor.py` dalej obsługuje alternatywny kształt zagnieżdżony (`{"coordinator": ...}`) oraz utrzymuje oddzielną gałąź `hass.data[DOMAIN]["entries"]` z listą encji.
- **Ryzyko praktyczne:** Trudniejsze debugowanie i duże ryzyko subtelnych bugów przy zmianach lifecycle (reload/unload), bo część logiki działa na dwóch różnych kontraktach danych jednocześnie.
- **Rekomendacja:** Ustalić i udokumentować jeden kontrakt `hass.data` dla integracji (np. tylko `hass.data[DOMAIN][entry_id] = coordinator` + ewentualne typed helpery).
- **Mały osobny PR:** **TAK** (kontrakt + helper dostępu + testy regresji bez zmiany zachowania API).

### 2) Coordinator ma zbyt szeroką odpowiedzialność (fetch + tracking + geocoding + persistence + title management)
- **Plik/obszar:** `coordinator.py`, `OpenMeteoDataUpdateCoordinator._async_update_data`
- **Problem:** jedna metoda realizuje kilka krytycznych funkcji naraz (wyznaczanie coords, reverse geocode, decyzje o tytule, fetch weather/AQ, zapis `entry.data/options`).
- **Ryzyko praktyczne:** wysoki koszt zmian; łatwo o niezamierzone skutki uboczne przy pozornie małych poprawkach (np. tuning cooldownów wpływa na title sync i zapis opcji).
- **Rekomendacja:** etapowo wydzielić odpowiedzialności do mniejszych metod/serwisów domenowych (bez zmiany logiki), zaczynając od persistence i naming policy.
- **Mały osobny PR:** **TAK** (krokami, z zachowaniem obecnego zachowania).

### 3) Zbyt szerokie `except Exception` w ścieżkach krytycznych i migracyjnych
- **Plik/obszar:** `coordinator.py`, `weather.py`, `sensor.py`, `config_flow.py`
- **Problem:** wielokrotne przechwytywanie `Exception` i ciche `pass/continue`, także w migracjach rejestru encji i w update loop.
- **Ryzyko praktyczne:** realne błędy runtime mogą zostać zamaskowane; użytkownik dostaje „działa/nie działa losowo”, a logi nie pokazują precyzyjnej przyczyny.
- **Rekomendacja:** zawęzić wyjątki do oczekiwanych klas i zostawić kontekst (debug/warning z typem błędu) tam, gdzie failure jest dopuszczalny.
- **Mały osobny PR:** **TAK** (mechaniczne zawężanie + testy logowania).

### 4) Drift kompatybilności HA widoczny już w testach lokalnych
- **Plik/obszar:** `sensor.py`, `weather.py`, testy
- **Problem:** importy i API użyte w kodzie/testach nie pasują do lokalnego środowiska HA (np. `DeviceInfo` i `WeatherEntityFeature`), a fixture `async_test_home_assistant` jest użyta niezgodnie z wymaganiami lokalnej wersji.
- **Ryzyko praktyczne:** bardzo ograniczona wiarygodność testów CI/local; łatwo wypchnąć zmiany, które „przechodzą gdzieś”, ale nie są przenośne między wersjami HA.
- **Rekomendacja:** zdefiniować i przypiąć wspierane okno wersji HA + dopasować test harness do tych wersji.
- **Mały osobny PR:** **TAK** (wyłącznie stabilizacja kompatybilności testów i metadanych środowiska).

## B. Worth improving

### 1) Duplikacja logiki tytułu/nazewnictwa między config flow, weather i coordinator
- **Plik/obszar:** `config_flow.py` (`_async_guess_title`), `coordinator.py` (`_should_update_entry_title`), `weather.py` (`_maybe_update_entry_title`, `_maybe_update_device_registry_name`)
- **Problem:** decyzje o nazwie wpisu, nazwie urządzenia i friendly name są rozproszone.
- **Ryzyko praktyczne:** niespójne zachowanie po reloadach lub zmianach trybu; większa szansa regressions przy rozwijaniu UX.
- **Rekomendacja:** jeden moduł „naming policy” z jasno opisaną kolejnością priorytetów.
- **Mały osobny PR:** **TAK** (najpierw centralizacja helperów bez zmiany outputu).

### 2) Nierówny poziom jakości wyjątków i walidacji danych wejściowych
- **Plik/obszar:** szczególnie `config_flow.py` i pomocnicze reverse geocode/postcode
- **Problem:** część ścieżek ma defensywne `except Exception`, część ma precyzyjne wyjątki; style są mieszane.
- **Ryzyko praktyczne:** trudność utrzymania i przewidywalności zachowania przy błędach API/rate-limit.
- **Rekomendacja:** spójny standard: co jest expected failure (log debug), a co powinno być warning/error.
- **Mały osobny PR:** **TAK**.

### 3) Tłumaczenia i formularze mogą być niespójne z aktualnymi kluczami UI
- **Plik/obszar:** `config_flow.py` vs `en.json`/`pl.json`
- **Problem:** flow używa nowych kluczy (`update_interval_min`, dodatkowe pola onboardingu), a pliki tłumaczeń dalej eksponują m.in. legacy `update_interval`.
- **Ryzyko praktyczne:** słabszy UX i potencjalne „gołe” klucze w UI.
- **Rekomendacja:** synchronizacja i test snapshot dla formularzy/config steps.
- **Mały osobny PR:** **TAK**.

### 4) Testy dobrze pokrywają wycinki, ale słabo pokrywają scenariusze end-to-end lifecycle
- **Plik/obszar:** `tests/`
- **Problem:** dużo testów punktowych (migracja, UV, AQ), brak mocnych testów całego cyklu `setup -> update -> options change -> reload -> unload`.
- **Ryzyko praktyczne:** regresje integracyjne mogą przechodzić niezauważone.
- **Rekomendacja:** dodać 2-3 „wąskie” testy integracyjne krytycznych ścieżek HA.
- **Mały osobny PR:** **TAK**.

## C. Observations only

1. W kodzie widoczny jest świadomy nacisk na back-compat (legacy klucze i migracje), co jest dobre dla istniejących użytkowników, ale podnosi złożoność i koszt utrzymania.
2. Coordinator ma sensowne mechanizmy odporności (cache ostatnich danych, retry z jitter, fallback lokalizacji), co praktycznie redukuje skutki chwilowych awarii API.
3. Sporo komentarzy/komunikatów jest po polsku, część po angielsku — to nie jest bug, ale utrudnia onboarding zewnętrznym współtwórcom.
4. W `sensor.py` widoczne są drobne artefakty stylu (puste linie, importy używane historycznie), które same w sobie nie są krytyczne.

## D. Suggested refactor stages (bezpieczne, małe PR-y)

### Stage 1 — Stabilizacja kontraktu danych i test harness
- Ujednolicić odczyt/zapis `hass.data` przez helper dostępu (bez zmiany zachowania).
- Dodać testy regresji kontraktu `hass.data` dla sensor/weather setup.
- Uporządkować kompatybilność testów z docelową wersją HA i fixture.

### Stage 2 — Naming policy i ograniczenie efektów ubocznych
- Wydzielić jedną politykę nazewnictwa (entry title/device name/friendly name).
- Utrzymać obecne priorytety i cooldowny, ale przenieść decyzje do jednego modułu pomocniczego.
- Dodać testy scenariuszy: override użytkownika, fallback coords, track/static.

### Stage 3 — Redukcja ryzyka w wyjątkach i czytelność coordinatora
- Zawęzić `except Exception` do oczekiwanych wyjątków.
- Rozbić `_async_update_data` na mniejsze kroki prywatne (koordynacja bez zmiany wyników).
- Dodać testy dla logowania błędów i zachowania przy częściowej awarii AQ/geocode.
