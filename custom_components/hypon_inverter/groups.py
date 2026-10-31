"""Podział encji na urządzenia (grupy) w Home Assistant.

Główne urządzenie ("Informacje") zawiera dane o falowniku. Pozostałe grupy to osobne
urządzenia podłączone do głównego (via_device). Kolejność i nazwy zmienisz tutaj.
"""
from __future__ import annotations

# Kolejność grup = kolejność numerów w nazwach urządzeń (HA sortuje urządzenia po nazwie)
GROUP_ORDER = ("info", "grid", "pv", "energy", "power_control")

# Nazwy urządzeń: "info" to główne urządzenie ("<nazwa> – 1. Informacje"), pozostałe są do niego podłączone
GROUP_LABELS = {
    "info": "Informacje",
    "grid": "Sieć i wyjście",
    "pv": "PV",
    "energy": "Energia",
    "power_control": "Sterowanie mocą",
}

GROUP_NUMBER = {group: i + 1 for i, group in enumerate(GROUP_ORDER)}

_SETS: dict[str, set[str]] = {
    "info": {
        "serial_number", "model_name", "manufacturer_name", "firmware_pn", "hardware_version",
        "software_version", "protocol_version", "parameter_version", "device_type", "grid_type",
        "rated_power", "max_apparent_power", "mppt_count", "grid_standard",
        "machine_state", "operating_substate", "waiting_time", "operating_hours_total",
        "fault_codes", "fault_description", "fault_active",
        "warning_codes", "warning_description", "warning_active",
        "restart", "settings_lock", "response_time", "read_errors", "reconnects",
    },
    "grid": {
        "output_active_power", "output_apparent_power", "output_reactive_power",
        "output_power_factor", "reactive_direction", "grid_frequency",
        "grid_l1_voltage", "grid_l2_voltage", "grid_l3_voltage",
        "grid_l1_current", "grid_l2_current", "grid_l3_current",
        "grid_l1_l2_voltage", "grid_l2_l3_voltage", "grid_l3_l1_voltage",
    },
    "pv": {
        "pv1_voltage", "pv1_current", "pv1_power", "pv2_voltage", "pv2_current", "pv2_power",
        "pv_power_total",
    },
    "energy": {"energy_today", "energy_total"},
    "power_control": {
        "power_control_mode", "fixed_active_power", "meter_limit_power", "meter_type",
        "power_increase_rate", "power_decrease_rate", "inverter_run",
    },
}

GROUP_OF: dict[str, str] = {key: group for group, keys in _SETS.items() for key in keys}


def group_of(key: str) -> str:
    """Grupa dla klucza encji (nieznane trafiają do głównego urządzenia)."""
    return GROUP_OF.get(key, "info")
