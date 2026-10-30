"""Kody usterek i ostrzeżeń (HYPONTECH Modbus Protocol V1.5): kod -> nazwa z rozpiski.

Falownik podaje jeden kod naraz (30117 usterka, 30118 ostrzeżenie; 0 = brak).
Tytuły w różnych językach są w names/<język>.json (sekcje "faults" i "warnings").
"""
from __future__ import annotations

FAULTS: dict[int, str] = {
    1: "MCU Fault",
    2: "Current sensor fault",
    3: "GFCI device fault",
    4: "Relay fault",
    5: "PV voltage high fault",
    6: "ISO fault",
    7: "GFCI fault",
    8: "Temperature over fault",
    9: "No utility fault",
    10: "Grid voltage over fault",
    11: "Grid frequency over fault",
    12: "DCI over fault",
    13: "EEPROM fault",
    14: "Main and voice MCU communication fault",
    15: "BUS voltage high fault",
    16: "BUS voltage low fault",
    17: "DRM S9 fault",
    18: "DRM S0 fault",
    19: "PE Connection missing",
    20: "Bus voltage unbalance",
    21: "BMS communication fail",
    22: "CT is not connected",
    23: "CT reverse connection",
    24: "Battery is not connected",
    25: "Backup load over voltage",
}

WARNINGS: dict[int, str] = {
    1: "PV1 over current",
    2: "PV2 over current",
    3: "PV3 over current",
    4: "PV4 over current",
    5: "PV1 under voltage",
    6: "PV2 under voltage",
    7: "PV3 under voltage",
    8: "PV4 under voltage",
    9: "BUS over voltage",
    10: "BUS under voltage",
    11: "INV over current",
    12: "ISO",
    13: "Grid peak over voltage",
    14: "FW update",
    15: "PE connection missing",
    16: "Grid voltage consistency warning",
    17: "Fan abnormal",
    18: "Backup load overload warning",
    19: "SPD failure warning",
}

TABLES = {"faults": FAULTS, "warnings": WARNINGS}
