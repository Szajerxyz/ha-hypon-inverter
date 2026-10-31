"""Sensory (odczyty)."""
from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import HyponConfigEntry
from .entity import HyponEntity
from .faults import TABLES
from .registers import (
    OFFLINE_STATE,
    SENSORS,
    STATS,
    SensorDef,
    active_code,
    combine,
    decode_ascii,
    decode_version,
    energy_total,
    numeric_value,
)

_LOGGER = logging.getLogger(__name__)
TEXT_KINDS = {"state", "fault_list", "fault_text", "ascii", "version"}


async def async_setup_entry(
    hass: HomeAssistant, entry: HyponConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(HyponSensor(entry.runtime_data, d) for d in SENSORS)


class HyponSensor(HyponEntity, RestoreSensor):
    def __init__(self, coordinator, d: SensorDef) -> None:
        super().__init__(coordinator, d.key, d.name, d.address, d.words)
        self._d = d
        self._names = coordinator.names
        self._attr_native_unit_of_measurement = d.unit
        if d.options and d.strict:
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = [self._names.option(d.key, o) for o in d.options.values()]
        else:
            self._attr_device_class = SensorDeviceClass(d.device_class) if d.device_class else None
        self._attr_state_class = SensorStateClass(d.state_class) if d.state_class else None
        self._attr_suggested_display_precision = d.precision
        if d.icon:
            self._attr_icon = d.icon
        self._attr_entity_registry_enabled_default = d.enabled_default
        if d.diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._numeric = not d.options and d.kind not in TEXT_KINDS
        self._restored: float | None = None
        self._restored_at: datetime | None = None
        self._last: float | None = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # ostatnia wartość liczników sprzed restartu HA (pokazywana, gdy falownik śpi)
        if self._numeric and self._d.offline in ("keep", "today"):
            last = await self.async_get_last_sensor_data()
            state = await self.async_get_last_state()
            if last is not None and isinstance(last.native_value, (int, float)):
                self._restored = float(last.native_value)
                self._restored_at = state.last_updated if state else None
                if self._d.monotonic:
                    self._last = self._restored

    @property
    def available(self) -> bool:
        if self._d.kind == "stat":
            return True
        if not self.coordinator.last_update_success:
            return False
        return self.coordinator.offline or self._raw is not None

    # ------------------------------------------------------------------ wartość
    def _option(self, raw: int | None) -> str | None:
        if raw is None:
            return None
        option = self._d.options.get(raw)
        if option is not None:
            return self._names.option(self._d.key, option)
        return None if self._d.strict else f"{self._names.common('unknown')} ({raw})"

    def _code(self) -> int | None:
        return 0 if self.coordinator.offline else active_code(self._data, self._d.address)

    def _today_valid(self) -> bool:
        """Czy zapamiętana wartość "dzisiejsza" pochodzi z dzisiaj (po północy -> 0)."""
        ref = self.coordinator.last_online or self._restored_at
        return ref is not None and dt_util.as_local(ref).date() == dt_util.now().date()

    def _value(self):
        d, data, off = self._d, self._data, self.coordinator.offline
        if d.kind == "stat":
            return getattr(self.coordinator.client, STATS[d.key], None)
        if d.kind == "state":
            return self._names.option(d.key, OFFLINE_STATE) if off else self._option(data.get(d.address))
        if d.kind in ("fault_list", "fault_text"):
            code = self._code()
            if code is None:
                return None
            if not code:
                return self._names.common("none")
            if d.kind == "fault_list":
                return str(code)
            return f"[{code:02d}] {self._names.fault(d.table, code)}"[:255]
        if off and d.offline == "zero":
            return 0
        if off and d.offline == "none":
            return None
        if d.kind == "ascii":
            return decode_ascii(data, d.address, d.words)
        if d.kind == "version":
            raw = combine(data, d.address, d.words)
            return None if raw is None else decode_version(raw)
        if d.options:
            return self._option(data.get(d.address))
        value = numeric_value(d, data)
        if value is None and off:
            value = self._restored
        if off and d.offline == "today" and not self._today_valid():
            return 0.0
        return value

    @property
    def native_value(self):
        value = self._value()
        if self._d.monotonic and isinstance(value, (int, float)):
            if self._last is not None and value < self._last - 0.05:
                _LOGGER.debug("%s: odczyt %s mniejszy niż %s - pomijam", self._d.key, value, self._last)
                return self._last
            self._last = value
        return value

    @property
    def extra_state_attributes(self) -> dict | None:
        d = self._d
        if d.kind == "fault_text":
            code = self._code()
            if not code:
                return {"faults": []}
            return {
                "faults": [
                    {
                        "code": code,
                        "name": TABLES[d.table].get(code),
                        "title": self._names.fault(d.table, code),
                    }
                ]
            }
        if d.kind == "energy_total" and not self.coordinator.offline:
            return {"source": energy_total(self._data, d)[1]}
        if d.kind == "state":
            off = self.coordinator.offline
            return {"raw_value": None if off else self._data.get(d.address), "offline": off}
        if d.options:
            return {"raw_value": self._data.get(d.address)}
        return None
