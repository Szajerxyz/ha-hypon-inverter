"""Stałe integracji Hypontech Inverter."""

DOMAIN = "hypon_inverter"
ENTITY_PREFIX = "hypon"  # entity_id = <domena>.hypon_<id z names/en.json>

CONF_SLAVE = "slave"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_TIMEOUT = "timeout"
CONF_RETRIES = "retries"
CONF_LOCK_MINUTES = "lock_minutes"
CONF_TOLERANCE = "tolerance"

DEFAULT_NAME = "Falownik Hypontech"
DEFAULT_PORT = 502
DEFAULT_SLAVE = 3
DEFAULT_SCAN_INTERVAL = 10  # sekundy (magistrala wspólna z SRNE)
# Konwerter Waveshare przy kilku połączeniach TCP potrafi przetrzymać odpowiedź ok. 2-5 s,
# dlatego timeout ma zapas, a ponowienie jest jedno (z przerwą RETRY_DELAY).
DEFAULT_TIMEOUT = 5  # sekundy na jedno zapytanie
DEFAULT_RETRIES = 1  # ponowienia zapytania bez odpowiedzi
RETRY_DELAY = 0.5  # s przerwy przed ponowieniem
DEFAULT_LOCK_MINUTES = 10

# Rejestry "wolne" (ustawienia, energia Float32) co N cykli, dane urządzenia co M cykli
SLOW_EVERY = 6
INFO_EVERY = 360

# Przerwa po każdym zapytaniu (druga integracja korzysta z tego samego konwertera)
REQUEST_GAP = 0.1

# Falownik on-grid bez słońca nie ma zasilania i nie odpowiada (noc).
# Po DEFAULT_TOLERANCE kolejnych cyklach bez odpowiedzi (opcja "tolerancja") integracja przechodzi
# w tryb czuwania: jedno zapytanie (bez ponowień) co OFFLINE_INTERVAL sekund.
DEFAULT_TOLERANCE = 3
OFFLINE_INTERVAL = 60

# Restart: Stop (40819 = 1) -> przerwa -> Start (40819 = 0)
RESTART_DELAY = 10

MANUFACTURER = "Hypontech"
MODEL = "HPT-10000"
