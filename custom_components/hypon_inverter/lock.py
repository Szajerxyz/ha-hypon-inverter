"""Blokada ustawień (encja lock): odblokowanie bez kodu, auto-blokada po czasie."""
from __future__ import annotations

from homeassistant.components.lock import LockEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HyponConfigEntry
from .entity import HyponEntity
from .registers import LOCKS, LockDef


async def async_setup_entry(
    hass: HomeAssistant, entry: HyponConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(HyponLock(entry.runtime_data, d) for d in LOCKS)


class HyponLock(HyponEntity, LockEntity):
    """locked = zapisy od użytkowników zablokowane; unlocked = dozwolone (do końca czasu)."""

    def __init__(self, coordinator, d: LockDef) -> None:
        super().__init__(coordinator, d.key, d.name, 0)

    @property
    def available(self) -> bool:
        # nie zależy od odczytu rejestrów
        return self.coordinator.last_update_success

    @property
    def is_locked(self) -> bool:
        return not self.coordinator.write_lock.unlocked

    @property
    def extra_state_attributes(self) -> dict:
        return {"remaining_seconds": self.coordinator.write_lock.remaining}

    async def async_unlock(self, **kwargs) -> None:
        self.coordinator.async_unlock()

    async def async_lock(self, **kwargs) -> None:
        self.coordinator.async_lock()
