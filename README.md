# Hypon Inverter – integracja Home Assistant (Modbus TCP)

Falownik on-grid Hypontech **HPT-10000** (oraz HPK/HPS/HPT wg protokołu Hypontech Modbus V1.5) jako urządzenie
w Home Assistant, bez wpisów w `configuration.yaml`.
Komunikacja: falownik → RS485 → Waveshare (tryb **Modbus TCP ↔ RTU**) → Home Assistant.

## Instalacja przez HACS
1. HACS → ⋮ → *Custom repositories* → adres `https://github.com/Szajerxyz/ha-hypon-inverter`, kategoria **Integration**.
2. Pobierz „Hypon Inverter”, zrestartuj Home Assistant.
3. *Ustawienia → Urządzenia i usługi → Dodaj integrację → Hypon Inverter*.

## Instalacja ręczna
Skopiuj `custom_components/hypon_inverter` do `/config/custom_components/`, zrestartuj HA, dodaj integrację.

## Konfiguracja
Przy dodawaniu: nazwa (domyślnie „Falownik Hypon”), adres IP konwertera, port (502), ID urządzenia Modbus (slave, domyślnie 3)
i interwał odczytu (domyślnie **10 s**). W *Konfiguruj* zmienisz interwał, czas oczekiwania na odpowiedź (3 s), liczbę ponowień (2)
i czas odblokowania ustawień (10 min).

Falownik on-grid bez słońca **nie ma zasilania i nie odpowiada**. Jeśli dodajesz integrację w nocy, kreator zapyta, czy dodać ją mimo to.

## Noc (tryb czuwania)
Po 3 kolejnych cyklach bez odpowiedzi integracja przechodzi w tryb czuwania: wysyła **jedno** zapytanie na minutę, bez ponowień,
żeby nie blokować magistrali współdzielonej z SRNE. W tym czasie:
- stan falownika = „Wyłączony (brak PV)”, moce i prądy = 0, napięcia i częstotliwość sieci = brak wartości,
- liczniki (produkcja całkowita, czas pracy) zachowują ostatnią wartość, także po restarcie HA,
- „Dzisiejsza produkcja” zachowuje wartość do północy, potem pokazuje 0,
- ustawienia, start/stop i restart są niedostępne.

Rano, gdy falownik odpowie, odczyty wracają do zwykłego interwału.

## Grupy encji (urządzenia)
Encje są podzielone na urządzenia z numerami (nazwa wynika z nazwy wpisanej przy dodawaniu integracji):

| Urządzenie | Zawartość |
|---|---|
| Falownik Hypon – 1. Informacje | model, SN, wersje, norma sieci, stan, czas pracy, usterki i ostrzeżenia, blokada, restart |
| Falownik Hypon – 2. Sieć i wyjście | moc czynna/pozorna/bierna, PF, napięcia i prądy faz, napięcia międzyfazowe, częstotliwość |
| Falownik Hypon – 3. PV | napięcie, prąd i moc PV1/PV2 (moc = napięcie × prąd), moc PV suma |
| Falownik Hypon – 4. Energia | produkcja dziś i całkowita (do panelu Energia) |
| Falownik Hypon – 5. Sterowanie mocą | tryb sterowania mocą czynną, zadana moc, limit mocy z licznikiem, typ licznika, start/stop |

ID encji mają format `<domena>.hypon_<nazwa_angielska>`, np. `sensor.hypon_pv_total_power`,
`sensor.hypon_pv_generation_total` – niezależnie od języka Home Assistant.

## Panel Energia
Jako *produkcję energii słonecznej* wybierz `sensor.hypon_pv_generation_total` (kWh, `total_increasing`).
Integracja używa licznika Float32 (rejestr 30154, dokładność ułamków kWh), a gdy falownik go nie podaje lub wartość nie zgadza się
z licznikiem U32 (30111) – licznika U32 (rozdzielczość 1 kWh). Źródło widać w atrybucie `source`. Licznik nie może się cofnąć
(pojedynczy błędny odczyt jest pomijany).

## Usterki i ostrzeżenia
Falownik podaje **jeden** kod usterki (30117) i jeden kod ostrzeżenia (30118) naraz.
- `sensor.hypon_fault_description` – „[09] Brak sieci” albo „Brak”; atrybut `faults` (lista: `code`, `name`, `title`),
- `sensor.hypon_fault_codes` – sam kod, `binary_sensor.hypon_fault_active` – czy jest usterka,
- analogicznie `warning_description`, `warning_codes`, `warning_active`.

## Tłumaczenia
Nazwy encji, opcji, grup i usterek są w `custom_components/hypon_inverter/names/` (`en.json`, `pl.json`).
Wyświetlany język = język systemowy Home Assistant, brakujące wpisy z `en.json`.
Aby dodać język: skopiuj `en.json` do `<kod_języka>.json` (np. `de.json`), zostaw klucze, przetłumacz tylko wartości
(pole `id` jest potrzebne tylko w `en.json` – z niego powstają ID encji). Zrestartuj HA.

## Zapis parametrów
Zapisywane są tylko rejestry zatwierdzone z rozpiski: tryb sterowania mocą czynną (40400), limit mocy z licznikiem (40401, 0–10000 W),
typ licznika (40403), zadana moc czynna (40410, 0–100 %) i start/stop (40819). Wartości spoza zakresu są odrzucane.
Restart = Stop → 10 s → Start (rozpiska nie ma osobnego polecenia restartu).
Zapis: funkcja 06 (jeden rejestr), a gdy falownik jej nie obsługuje – funkcja 16.

## Blokada ustawień (bez kodu)
Falownik Hypon nie ma hasła ustawień. Zapisy wykonywane przez **użytkowników** (dashboard, aplikacja, ręcznie uruchamiane skrypty)
są odrzucane, dopóki ustawienia nie zostaną odblokowane w encji `lock.hypon_settings_lock` („Blokada ustawień”) – dotknij jej
i wybierz *Odblokuj*. Po upływie czasu odblokowania (domyślnie 10 min) ustawienia blokują się same; po restarcie HA są zawsze
zablokowane. Zapisy z **automatyzacji** (bez użytkownika) nie są blokowane.

## Wspólna magistrala z SRNE
Falownik pracuje na tej samej magistrali RS485 co SRNE (ten sam konwerter Waveshare, inny adres slave).
- W konwerterze musi być włączona obsługa wielu połączeń/zapytań (bez niej encje znikały).
- Integracja czyta blokami (pomiary: 1 zapytanie na cykl, ustawienia i liczniki co 6 cykli, dane urządzenia co godzinę),
  robi przerwę 0,1 s po każdym zapytaniu i trzyma jedno zapytanie naraz (blokada asyncio).
- Gdy pojawiają się braki odczytów u SRNE lub Hypona: wydłuż interwał (np. 15 s) albo zmniejsz liczbę ponowień.

## Diagnostyka
Akcja `hypon_inverter.read_registers` (Narzędzia deweloperskie → Akcje) odczytuje dowolny zakres rejestrów, np. start `30100`, count `41`.
Logi szczegółowe: w `configuration.yaml` → `logger: logs: custom_components.hypon_inverter: debug`.

## Ikona integracji
Ikona znajduje się w `custom_components/hypon_inverter/brand/` (`icon.png`, `icon@2x.png`) i jest wyświetlana przez Home Assistant 2026.3
lub nowszy. Lista HACS nie pokazuje ikon integracji niestandardowych (ograniczenie HACS).
