"""Sensory binarne (usterka, ostrzeżenie)."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HyponConfigEntry
from .entity import HyponEntity
from .registers import BINARY_SENSORS, BinarySensorDef


async def async_setup_entry(
    hass: HomeAssistant, entry: HyponConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(HyponBinarySensor(entry.runtime_data, d) for d in BINARY_SENSORS)


class HyponBinarySensor(HyponEntity, BinarySensorEntity):
    def __init__(self, coordinator, d: BinarySensorDef) -> None:
        super().__init__(coordinator, d.key, d.name, d.address)
        self._attr_device_class = (
            BinarySensorDeviceClass(d.device_class) if d.device_class else None
        )

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and (
            self.coordinator.offline or self._raw is not None
        )

    @property
    def is_on(self) -> bool | None:
        if self.coordinator.offline:
            return False  # falownik wyłączony (noc) - brak aktywnej usterki
        raw = self._raw
        return None if raw is None else raw != 0
