# Hypontech Inverter – integracja Home Assistant (Modbus TCP)

Falownik on-grid Hypontech **HPT-10000** (oraz HPK/HPS/HPT wg protokołu Hypontech Modbus V1.5) jako urządzenie
w Home Assistant, bez wpisów w `configuration.yaml`.
Komunikacja: falownik → RS485 → Waveshare (tryb **Modbus TCP ↔ RTU**) → Home Assistant.

## Instalacja przez HACS
1. HACS → ⋮ → *Custom repositories* → adres `https://github.com/Szajerxyz/ha-hypon-inverter`, kategoria **Integration**.
2. Pobierz „Hypontech Inverter”, zrestartuj Home Assistant.
3. *Ustawienia → Urządzenia i usługi → Dodaj integrację → Hypontech Inverter*.

## Instalacja ręczna
Skopiuj `custom_components/hypon_inverter` do `/config/custom_components/`, zrestartuj HA, dodaj integrację.

## Konfiguracja
Przy dodawaniu: nazwa (domyślnie „Falownik Hypontech”), adres IP konwertera, port (502), ID urządzenia Modbus (slave, domyślnie 3)
i interwał odczytu (domyślnie **10 s**). W *Konfiguruj* zmienisz: interwał, czas oczekiwania na odpowiedź (**5 s**),
liczbę ponowień (**1**), tolerancję – po ilu kolejnych cyklach bez odpowiedzi falownik zostaje uznany za wyłączony (**3**) –
oraz czas odblokowania ustawień (10 min).

Falownik on-grid bez słońca **nie ma zasilania i nie odpowiada**. Jeśli dodajesz integrację w nocy, kreator zapyta, czy dodać ją mimo to.

## Noc (tryb czuwania)
Po 3 kolejnych cyklach bez odpowiedzi (opcja *tolerancja*) integracja przechodzi w tryb czuwania: wysyła **jedno** zapytanie na minutę, bez ponowień,
żeby nie blokować magistrali współdzielonej z innymi urządzeniami. W tym czasie:
- stan falownika = „Wyłączony (brak PV)”, moce i prądy = 0, napięcia i częstotliwość sieci = brak wartości,
- liczniki (produkcja całkowita, czas pracy) zachowują ostatnią wartość, także po restarcie HA,
- „Dzisiejsza produkcja” zachowuje wartość do północy, potem pokazuje 0,
- ustawienia, start/stop i restart są niedostępne.

Rano, gdy falownik odpowie, odczyty wracają do zwykłego interwału.

## Grupy encji (urządzenia)
Encje są podzielone na urządzenia z numerami (nazwa wynika z nazwy wpisanej przy dodawaniu integracji):

| Urządzenie | Zawartość |
|---|---|
| Falownik Hypontech – 1. Informacje | model, SN, wersje, norma sieci, stan, czas pracy, usterki i ostrzeżenia, blokada, restart |
| Falownik Hypontech – 2. Sieć i wyjście | moc czynna/pozorna/bierna, PF, napięcia i prądy faz, napięcia międzyfazowe, częstotliwość |
| Falownik Hypontech – 3. PV | napięcie, prąd i moc PV1/PV2 (moc = napięcie × prąd), moc PV suma |
| Falownik Hypontech – 4. Energia | produkcja dziś i całkowita (do panelu Energia) |
| Falownik Hypontech – 5. Sterowanie mocą | tryb sterowania mocą czynną, zadana moc, limit mocy z licznikiem, typ licznika, start/stop |

Nazwa integracji i domyślna nazwa urządzenia to „Hypontech”, natomiast **ID i nazwy encji** zachowują krótki prefiks `hypon_` / „Hypon” (np. „Hypon PV moc suma”), a domena integracji to `hypon_inverter`.

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
Falownik Hypontech nie ma hasła ustawień. Zapisy wykonywane przez **użytkowników** (dashboard, aplikacja, ręcznie uruchamiane skrypty)
są odrzucane, dopóki ustawienia nie zostaną odblokowane w encji `lock.hypon_settings_lock` („Blokada ustawień”) – dotknij jej
i wybierz *Odblokuj*. Po upływie czasu odblokowania (domyślnie 10 min) ustawienia blokują się same; po restarcie HA są zawsze
zablokowane. Zapisy z **automatyzacji** (bez użytkownika) nie są blokowane.

## Wspólna magistrala (inny falownik / inna integracja na tym samym konwerterze)
Integracja może pracować na jednej magistrali RS485 z innymi urządzeniami (np. falownik SRNE z własną integracją),
które łączą się z tym samym konwerterem osobnym połączeniem TCP. Każde urządzenie musi mieć inny adres slave.
- W konwerterze Waveshare włącz *Multi-host* (w trybie *Modbus TCP to RTU* jest zawsze włączony).
- Konwerter przy kilku połączeniach TCP **rozsyła odpowiedzi do wszystkich klientów** i potrafi przetrzymać odpowiedź
  o 2–5 s (zaobserwowane na RS485 TO ETH (B), firmware V1.452). Dlatego:
  - domyślny czas oczekiwania to 5 s, a brak odpowiedzi **nie zrywa połączenia** (spóźniona odpowiedź trafia do właściwego
    gniazda; połączenie jest odnawiane tylko przy błędzie łącza),
  - cudze ramki są odrzucane (inny adres slave, inny numer transakcji lub inna liczba rejestrów),
  - w logach drugiej integracji mogą pojawiać się komunikaty pymodbus `request ask for id=1 but got id=3, Skipping` –
    to nieszkodliwe odrzucenie cudzej odpowiedzi.
- Integracja czyta blokami (pomiary: 1 zapytanie na cykl, ustawienia i liczniki co 6 cykli, dane urządzenia co godzinę)
  z przerwą 0,1 s po każdym zapytaniu i jednym zapytaniem naraz.
- Nie ustawiaj zbyt krótkich interwałów: dla dwóch falowników sprawdzone jest 10 s w każdej z integracji.
  Przy 5 s w drugiej integracji opóźnienia konwertera rosły powyżej 3 s.
- Komunikaty pymodbus o odrzuconych ramkach wyciszysz w `configuration.yaml`:
  `logger:` → `logs:` → `pymodbus: critical` (integracje i tak logują własne problemy).

## Diagnostyka
Sensory diagnostyczne (domyślnie wyłączone, urządzenie „1. Informacje”): **Czas odpowiedzi** [ms] ostatniego zapytania,
**Błędy odczytu** i **Ponowne połączenia** (liczone od uruchomienia integracji). Zapytania testowe w trybie nocnym
(falownik wyłączony) nie są liczone jako błędy. Włącz je, gdy chcesz ocenić pracę magistrali.

Akcja `hypon_inverter.read_registers` (Narzędzia deweloperskie → Akcje) odczytuje dowolny zakres rejestrów, np. start `30100`, count `41`.
Logi szczegółowe: w `configuration.yaml` → `logger: logs: custom_components.hypon_inverter: debug`.

## Ikona integracji
Ikona znajduje się w `custom_components/hypon_inverter/brand/` (`icon.png`, `icon@2x.png`) i jest wyświetlana przez Home Assistant 2026.3
lub nowszy. Lista HACS nie pokazuje ikon integracji niestandardowych (ograniczenie HACS).
