"""Przełączniki (praca falownika: start/stop)."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HyponConfigEntry
from .entity import HyponWritableEntity
from .registers import SWITCHES, SwitchDef


async def async_setup_entry(
    hass: HomeAssistant, entry: HyponConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(HyponSwitch(entry.runtime_data, d) for d in SWITCHES)


class HyponSwitch(HyponWritableEntity, SwitchEntity):
    def __init__(self, coordinator, d: SwitchDef) -> None:
        super().__init__(coordinator, d.key, d.name, d.address)
        self._d = d
        if d.icon:
            self._attr_icon = d.icon

    @property
    def is_on(self) -> bool | None:
        raw = self._raw
        return None if raw is None else raw == self._d.on

    async def async_turn_on(self, **kwargs) -> None:
        self._guard()
        await self.coordinator.async_write(self._address, [self._d.on])

    async def async_turn_off(self, **kwargs) -> None:
        self._guard()
        await self.coordinator.async_write(self._address, [self._d.off])
