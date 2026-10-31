"""Mapa rejestrów falownika Hypontech HPT-10000 (wg HYPONTECH Modbus Protocol V1.5).

Adresy dziesiętnie, tak jak w dokumentacji Hypontech (30100 = 0x7594). Wszystkie rejestry czytane
funkcją 03 (holding). Wartości 32-bitowe: starsze słowo pod niższym adresem (potwierdzone na liczniku
energii: 31104 kWh). Moduł nie zależy od Home Assistant - dekodowanie jest testowane osobno.
"""
from __future__ import annotations

import math
import struct
from dataclasses import dataclass

# ---------------------------------------------------------------- definicje


@dataclass(frozen=True)
class SensorDef:
    key: str
    name: str
    address: int
    scale: float = 1.0
    unit: str | None = None
    device_class: str | None = None
    state_class: str | None = "measurement"
    precision: int | None = None
    signed: bool = False
    words: int = 1  # 2 = wartość 32-bitowa (starsze słowo pod niższym adresem)
    options: dict[int, str] | None = None  # sensor wyliczeniowy (klucze etykiet z names/*.json)
    strict: bool = True  # False = nieznane wartości jako "Nieznany (N)"
    # "ascii" (2 znaki na rejestr), "version" (U8 x 4 -> V a.b.c.d), "energy_total" (Float32 / U32),
    # "fault_list" (kod usterki jako tekst), "fault_text" (opis + atrybut z listą),
    # "stat" (statystyka komunikacji z klienta, bez rejestru)
    kind: str | None = None
    table: str | None = None  # "faults" / "warnings" dla kind fault_*
    alt_address: int | None = None  # energy_total: adres Float32
    # sensor wyliczany: suma iloczynów par rejestrów razy scale (moc PV = U x I)
    products: tuple[tuple[int, int], ...] = ()
    # zachowanie, gdy falownik nie odpowiada (noc): "keep" ostatnia wartość, "zero", "none" (brak),
    # "today" (ostatnia wartość, po północy 0)
    offline: str = "keep"
    monotonic: bool = False  # licznik nie może maleć (ochrona panelu Energia przed błędnym odczytem)
    enabled_default: bool = True
    diagnostic: bool = False
    icon: str | None = None


@dataclass(frozen=True)
class BinarySensorDef:
    key: str
    name: str
    address: int
    device_class: str | None = "problem"


@dataclass(frozen=True)
class NumberDef:
    key: str
    name: str
    address: int
    minimum: float
    maximum: float
    step: float = 1
    scale: float = 1.0
    unit: str | None = None
    icon: str | None = None
    signed: bool = False
    words: int = 1


@dataclass(frozen=True)
class SwitchDef:
    key: str
    name: str
    address: int
    on: int = 1
    off: int = 0
    icon: str | None = None


@dataclass(frozen=True)
class SelectDef:
    key: str
    name: str
    address: int
    options: dict[int, str]
    icon: str | None = None


@dataclass(frozen=True)
class ButtonDef:
    key: str
    name: str
    icon: str | None = None


@dataclass(frozen=True)
class LockDef:
    key: str
    name: str


# ---------------------------------------------------------------- słowniki wartości
MACHINE_STATE = {0: "waiting", 1: "normal", 2: "fault"}
OFFLINE_STATE = "offline"  # stan dopisywany przez integrację, gdy falownik nie odpowiada
SUBSTATE = {0: "none", 1: "grid_tied", 2: "backup"}
REACTIVE_DIRECTION = {1: "lag", 2: "lead"}
GRID_STANDARD = {n: f"std_{n}" for n in range(1, 37)}
POWER_CONTROL_MODE = {0: "not_used", 1: "fixed_active_power", 2: "dred", 3: "meter", 4: "plant_control"}
METER_TYPE = {0: "sdm230", 1: "sdm630"}

# Adresy z rozpiski
REG_RUN = 40819  # Start/stop: 0 = start, 1 = stop
REG_STATE = 30115  # stan falownika - rejestr do sprawdzania, czy falownik odpowiada


# ---------------------------------------------------------------- sensory
def _v(key, name, addr, offline="none"):
    return SensorDef(key, name, addr, 0.1, "V", "voltage", precision=1, offline=offline)


def _a(key, name, addr):
    return SensorDef(key, name, addr, 0.1, "A", "current", precision=1, offline="zero")


def _pv_power(key, name, *pairs):
    return SensorDef(key, name, pairs[0][0], 0.01, "W", "power", precision=0, products=pairs,
                     offline="zero", icon="mdi:solar-power")


def _diag(key, name, addr, words=1, kind=None, icon="mdi:chip", enabled=True):
    return SensorDef(key, name, addr, words=words, kind=kind, state_class=None, diagnostic=True,
                     icon=icon, enabled_default=enabled)


SENSORS: tuple[SensorDef, ...] = (
    # --- 1. Informacje: dane urządzenia ---
    _diag("serial_number", "Numer seryjny", 30026, 8, "ascii", "mdi:identifier"),
    _diag("model_name", "Model", 30018, 8, "ascii", "mdi:information-outline"),
    _diag("manufacturer_name", "Producent", 30010, 8, "ascii", "mdi:factory"),
    _diag("firmware_pn", "Numer części oprogramowania", 30000, 7, "ascii", enabled=False),
    _diag("hardware_version", "Wersja sprzętowa", 30037, 2, "version"),
    _diag("software_version", "Wersja oprogramowania", 30039, 2, "version"),
    _diag("protocol_version", "Wersja protokołu Modbus", 30041, 2, "version"),
    _diag("parameter_version", "Wersja parametrów", 30043, 2, "version", enabled=False),
    _diag("device_type", "Typ urządzenia (kod)", 30034, icon="mdi:numeric", enabled=False),
    _diag("grid_type", "Typ sieci (kod)", 30035, icon="mdi:numeric", enabled=False),
    SensorDef("rated_power", "Moc znamionowa", 30036, 1, "W", "power", None, 0, diagnostic=True),
    SensorDef("max_apparent_power", "Maks. moc pozorna", 30047, 1, "VA", "apparent_power", None, 0,
              diagnostic=True),
    SensorDef("mppt_count", "Liczba MPPT", 30048, state_class=None, diagnostic=True,
              icon="mdi:solar-panel"),
    SensorDef("grid_standard", "Norma sieci", 30045, state_class=None, options=GRID_STANDARD,
              strict=False, diagnostic=True, icon="mdi:transmission-tower"),
    # --- 1. Informacje: stan pracy ---
    SensorDef("machine_state", "Stan falownika", REG_STATE, state_class=None, options=MACHINE_STATE,
              strict=False, kind="state", icon="mdi:state-machine"),
    SensorDef("operating_substate", "Tryb pracy (podstan)", 30160, state_class=None, options=SUBSTATE,
              strict=False, icon="mdi:sine-wave", enabled_default=False),
    SensorDef("waiting_time", "Czas oczekiwania na połączenie", 30116, 1, "s", "duration", precision=0,
              offline="zero", icon="mdi:timer-sand"),
    SensorDef("operating_hours_total", "Całkowity czas pracy", 30113, 1, "h", "duration",
              "total_increasing", 0, words=2, monotonic=True, icon="mdi:clock-outline"),
    SensorDef("fault_codes", "Kod usterki", 30117, state_class=None, kind="fault_list", table="faults",
              offline="zero", icon="mdi:alert-circle-outline"),
    SensorDef("fault_description", "Opis usterki", 30117, state_class=None, kind="fault_text",
              table="faults", offline="zero", icon="mdi:alert-circle"),
    SensorDef("warning_codes", "Kod ostrzeżenia", 30118, state_class=None, kind="fault_list",
              table="warnings", offline="zero", icon="mdi:alert-outline"),
    SensorDef("warning_description", "Opis ostrzeżenia", 30118, state_class=None, kind="fault_text",
              table="warnings", offline="zero", icon="mdi:alert"),
    # --- 2. Sieć i wyjście ---
    SensorDef("output_active_power", "Moc czynna wyjściowa", 30100, 1, "W", "power", precision=0,
              signed=True, words=2, offline="zero", icon="mdi:transmission-tower-export"),
    SensorDef("output_apparent_power", "Moc pozorna wyjściowa", 30102, 1, "VA", "apparent_power",
              precision=0, signed=True, words=2, offline="zero"),
    SensorDef("output_reactive_power", "Moc bierna wyjściowa", 30104, 1, "var", "reactive_power",
              precision=0, signed=True, words=2, offline="zero"),
    SensorDef("output_power_factor", "Współczynnik mocy", 30106, 0.01, None, "power_factor",
              precision=2, offline="none"),
    SensorDef("reactive_direction", "Charakter mocy biernej", 30107, state_class=None,
              options=REACTIVE_DIRECTION, strict=False, offline="none", icon="mdi:sine-wave"),
    _v("grid_l1_voltage", "Sieć L1 napięcie", 30131),
    _a("grid_l1_current", "Sieć L1 prąd", 30132),
    _v("grid_l2_voltage", "Sieć L2 napięcie", 30133),
    _a("grid_l2_current", "Sieć L2 prąd", 30134),
    _v("grid_l3_voltage", "Sieć L3 napięcie", 30135),
    _a("grid_l3_current", "Sieć L3 prąd", 30136),
    _v("grid_l1_l2_voltage", "Sieć napięcie L1-L2", 30137),
    _v("grid_l2_l3_voltage", "Sieć napięcie L2-L3", 30138),
    _v("grid_l3_l1_voltage", "Sieć napięcie L3-L1", 30139),
    SensorDef("grid_frequency", "Sieć częstotliwość", 30140, 0.01, "Hz", "frequency", precision=2,
              offline="none"),
    # --- 3. PV (moc = napięcie x prąd, rozpiska nie podaje mocy stringów) ---
    _v("pv1_voltage", "PV1 napięcie", 30119, "zero"),
    _a("pv1_current", "PV1 prąd", 30120),
    _pv_power("pv1_power", "PV1 moc", (30119, 30120)),
    _v("pv2_voltage", "PV2 napięcie", 30121, "zero"),
    _a("pv2_current", "PV2 prąd", 30122),
    _pv_power("pv2_power", "PV2 moc", (30121, 30122)),
    _pv_power("pv_power_total", "PV moc suma", (30119, 30120), (30121, 30122)),
    # --- 4. Energia ---
    SensorDef("energy_today", "Dzisiejsza produkcja", 30110, 0.1, "kWh", "energy", "total_increasing",
              1, offline="today", icon="mdi:solar-power-variant"),
    # Float32 (30154) ma rozdzielczość lepszą niż 1 kWh; gdy jest niedostępny lub niezgodny z U32 -> U32 (30111)
    SensorDef("energy_total", "Całkowita produkcja", 30111, 1, "kWh", "energy", "total_increasing", 1,
              words=2, kind="energy_total", alt_address=30154, monotonic=True,
              icon="mdi:solar-power-variant-outline"),
    # --- 5. Sterowanie mocą (tylko odczyt) ---
    SensorDef("power_increase_rate", "Szybkość wzrostu mocy", 40408, 0.1, "%Pn/min", None, None, 1,
              diagnostic=True, icon="mdi:trending-up"),
    SensorDef("power_decrease_rate", "Szybkość spadku mocy", 40409, 0.1, "%Pn/min", None, None, 1,
              diagnostic=True, icon="mdi:trending-down"),
    # --- Diagnostyka komunikacji (statystyki klienta od uruchomienia integracji, nie rejestry) ---
    SensorDef("response_time", "Czas odpowiedzi", 0, 1, "ms", "duration", "measurement", 0,
              kind="stat", enabled_default=False, diagnostic=True, icon="mdi:timer-outline"),
    SensorDef("read_errors", "Błędy odczytu", 0, state_class="total_increasing", precision=0,
              kind="stat", enabled_default=False, diagnostic=True, icon="mdi:alert-circle-outline"),
    SensorDef("reconnects", "Ponowne połączenia", 0, state_class="total_increasing", precision=0,
              kind="stat", enabled_default=False, diagnostic=True, icon="mdi:lan-connect"),
)

# sensor diagnostyczny -> atrybut klienta
STATS = {"response_time": "last_response_ms", "read_errors": "read_errors", "reconnects": "reconnects"}

BINARY_SENSORS: tuple[BinarySensorDef, ...] = (
    BinarySensorDef("fault_active", "Usterka falownika", 30117),
    BinarySensorDef("warning_active", "Ostrzeżenie falownika", 30118),
)

NUMBERS: tuple[NumberDef, ...] = (
    NumberDef("fixed_active_power", "Zadana moc czynna", 40410, 0, 100, 1, unit="%",
              icon="mdi:percent-circle"),
    NumberDef("meter_limit_power", "Limit mocy z licznikiem", 40401, 0, 10000, 10, unit="W",
              icon="mdi:transmission-tower-export", signed=True, words=2),
)

SELECTS: tuple[SelectDef, ...] = (
    SelectDef("power_control_mode", "Tryb sterowania mocą czynną", 40400, POWER_CONTROL_MODE,
              "mdi:tune-variant"),
    SelectDef("meter_type", "Typ licznika", 40403, METER_TYPE, "mdi:meter-electric"),
)

SWITCHES: tuple[SwitchDef, ...] = (
    SwitchDef("inverter_run", "Praca falownika (start/stop)", REG_RUN, on=0, off=1, icon="mdi:power"),
)

BUTTONS: tuple[ButtonDef, ...] = (ButtonDef("restart", "Restart falownika", "mdi:restart"),)

# Blokada ustawień (encja lock): zapisy od użytkowników wymagają odblokowania (bez kodu)
LOCKS: tuple[LockDef, ...] = (LockDef("settings_lock", "Blokada ustawień"),)

# ---------------------------------------------------------------- bloki odczytu
# Bloki ciągłe wg rozpiski (jedno zapytanie = jeden blok). Gdy falownik odrzuci blok,
# koordynator czyta potrzebne rejestry pojedynczo (jak w SRNE).
FAST_BLOCKS: tuple[tuple[int, int], ...] = ((30100, 41),)  # 30100-30140: moc, energia, stan, PV, sieć
SLOW_BLOCKS: tuple[tuple[int, int], ...] = ((30154, 2), (30160, 1), (40400, 11), (40819, 1))
INFO_BLOCKS: tuple[tuple[int, int], ...] = ((30000, 7), (30010, 36), (30047, 2))


def _span(addr: int, words: int = 1) -> set[int]:
    return set(range(addr, addr + words))


ALL_ADDRESSES: set[int] = set()
for _s in SENSORS:
    if _s.kind == "stat":
        continue
    ALL_ADDRESSES |= _span(_s.address, _s.words)
    if _s.alt_address:
        ALL_ADDRESSES |= _span(_s.alt_address, 2)
    for _a1, _a2 in _s.products:
        ALL_ADDRESSES |= {_a1, _a2}
for _b in BINARY_SENSORS:
    ALL_ADDRESSES.add(_b.address)
for _n in NUMBERS:
    ALL_ADDRESSES |= _span(_n.address, _n.words)
for _d in (*SELECTS, *SWITCHES):
    ALL_ADDRESSES.add(_d.address)


# ---------------------------------------------------------------- dekodowanie (czyste funkcje)
def to_signed(value: int, bits: int) -> int:
    return value - (1 << bits) if value >= 1 << (bits - 1) else value


def combine(data: dict[int, int], address: int, words: int) -> int | None:
    """Wartość z kolejnych rejestrów; starsze słowo pod niższym adresem."""
    value = 0
    for i in range(words):
        word = data.get(address + i)
        if word is None:
            return None
        value = (value << 16) | (word & 0xFFFF)
    return value


def split_words(value: int, words: int) -> list[int]:
    """Odwrotność combine(): lista rejestrów (starsze słowo pierwsze), wartości ujemne w U2."""
    value &= (1 << (16 * words)) - 1
    return [(value >> (16 * (words - 1 - i))) & 0xFFFF for i in range(words)]


def decode_ascii(data: dict[int, int], address: int, words: int) -> str | None:
    chars: list[str] = []
    for i in range(words):
        word = data.get(address + i)
        if word is None:
            return None
        for byte in (word >> 8, word & 0xFF):
            if byte == 0:
                return "".join(chars).strip() or None
            chars.append(chr(byte) if 32 <= byte < 127 else "?")
    return "".join(chars).strip() or None


def decode_version(raw: int) -> str:
    """U8 x 4 (dwa rejestry) -> "V a.b.c.d"."""
    return "V" + ".".join(str((raw >> s) & 0xFF) for s in (24, 16, 8, 0))


def decode_float32(data: dict[int, int], address: int) -> float | None:
    raw = combine(data, address, 2)
    if raw is None:
        return None
    value = struct.unpack(">f", raw.to_bytes(4, "big"))[0]
    return value if math.isfinite(value) else None


def energy_total(data: dict[int, int], d: SensorDef) -> tuple[float | None, str | None]:
    """Licznik całkowity: Float32 (dokładniejszy), o ile zgadza się z U32 (różnica <= 1,5 kWh)."""
    u32 = combine(data, d.address, 2)
    flt = decode_float32(data, d.alt_address) if d.alt_address else None
    if flt is not None and flt >= 0 and (u32 is None or abs(flt - u32) <= 1.5):
        return round(flt, 2), "float32"
    if u32 is None:
        return None, None
    return float(u32), "u32"


def active_code(data: dict[int, int], address: int) -> int | None:
    """Kod usterki/ostrzeżenia: pojedyncza wartość (0 = brak)."""
    return data.get(address)


def numeric_value(d: SensorDef, data: dict[int, int]) -> float | None:
    """Wartość liczbowa sensora (bez enum/tekstów)."""
    if d.products:
        total = 0
        for a1, a2 in d.products:
            if a1 not in data or a2 not in data:
                return None
            total += data[a1] * data[a2]
        return round(total * d.scale, 1)
    if d.kind == "energy_total":
        return energy_total(data, d)[0]
    raw = combine(data, d.address, d.words)
    if raw is None:
        return None
    if d.signed:
        raw = to_signed(raw, 16 * d.words)
    return round(raw * d.scale, 3)
