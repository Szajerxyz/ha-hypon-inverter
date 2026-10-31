"""Integracja Hypontech Inverter (Modbus TCP przez konwerter RS485)."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .client import HyponClient, HyponError
from .const import (
    CONF_RETRIES,
    CONF_SLAVE,
    CONF_TIMEOUT,
    DEFAULT_RETRIES,
    DEFAULT_TIMEOUT,
    DOMAIN,
    ENTITY_PREFIX,
    MANUFACTURER,
    MODEL,
)
from .coordinator import HyponCoordinator
from .entity import device_name
from .names import Names
from .registers import BINARY_SENSORS, BUTTONS, LOCKS, NUMBERS, SELECTS, SENSORS, SWITCHES

PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.LOCK,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SWITCH,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SERVICE_READ_REGISTERS = "read_registers"
READ_SCHEMA = vol.Schema(
    {
        vol.Required("start"): vol.Any(int, str),
        vol.Optional("count", default=16): vol.All(vol.Coerce(int), vol.Range(min=1, max=125)),
        vol.Optional("config_entry_id"): str,
    }
)

type HyponConfigEntry = ConfigEntry[HyponCoordinator]


def _all_entities():
    """(domena, klucz, domyślnie wyłączona) dla wszystkich encji integracji."""
    for d in SENSORS:
        yield "sensor", d.key, not d.enabled_default
    for d in BINARY_SENSORS:
        yield "binary_sensor", d.key, False
    for d in NUMBERS:
        yield "number", d.key, False
    for d in SWITCHES:
        yield "switch", d.key, False
    for d in SELECTS:
        yield "select", d.key, False
    for d in BUTTONS:
        yield "button", d.key, False
    for d in LOCKS:
        yield "lock", d.key, False


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    async def _read_registers(call: ServiceCall) -> dict:
        entries = [
            e
            for e in hass.config_entries.async_entries(DOMAIN)
            if e.state is ConfigEntryState.LOADED
            and call.data.get("config_entry_id") in (None, e.entry_id)
        ]
        if len(entries) != 1:
            raise ServiceValidationError(
                "Podaj config_entry_id (znaleziono "
                f"{len(entries)} aktywnych falowników)"
            )
        try:
            start = int(str(call.data["start"]), 0)  # np. 30100 lub 0x7594
        except ValueError as err:
            raise ServiceValidationError("Nieprawidłowy adres startowy") from err
        try:
            regs = await entries[0].runtime_data.async_read_range(start, call.data["count"])
        except HyponError as err:
            raise HomeAssistantError(f"Błąd odczytu: {err}") from err
        return {"registers": {f"{a} (0x{a:04X})": v for a, v in regs.items()}}

    hass.services.async_register(
        DOMAIN,
        SERVICE_READ_REGISTERS,
        _read_registers,
        schema=READ_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: HyponConfigEntry) -> bool:
    client = HyponClient(
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data[CONF_SLAVE],
        timeout=entry.options.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
        retries=entry.options.get(CONF_RETRIES, DEFAULT_RETRIES),
    )
    coordinator = HyponCoordinator(hass, entry, client)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await client.close()
        raise
    coordinator.names = await Names.async_load(hass)
    entry.runtime_data = coordinator
    # angielskie ID encji: rejestracja z góry, niezależnie od języka i nazw urządzeń
    registry = er.async_get(hass)
    for domain, key, disabled in _all_entities():
        object_id = coordinator.names.object_id(key)
        if object_id:
            registry.async_get_or_create(
                domain,
                DOMAIN,
                f"{entry.entry_id}_{key}",
                suggested_object_id=f"{ENTITY_PREFIX}_{object_id}",
                config_entry=entry,
                disabled_by=er.RegistryEntryDisabler.INTEGRATION if disabled else None,
            )
    # główne urządzenie musi istnieć przed podurządzeniami (via_device)
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=device_name(entry, "info", coordinator.names),
        manufacturer=MANUFACTURER,
        model=MODEL,
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_reload_on_update))
    return True


async def _reload_on_update(hass: HomeAssistant, entry: HyponConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: HyponConfigEntry) -> bool:
    if ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.client.close()
    return ok
