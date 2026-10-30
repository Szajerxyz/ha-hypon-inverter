"""Przyciski (restart falownika: Stop -> 10 s -> Start)."""
from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HyponConfigEntry
from .entity import HyponEntity
from .registers import BUTTONS, ButtonDef, REG_RUN


async def async_setup_entry(
    hass: HomeAssistant, entry: HyponConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(HyponButton(entry.runtime_data, d) for d in BUTTONS)


class HyponButton(HyponEntity, ButtonEntity):
    _attr_device_class = ButtonDeviceClass.RESTART

    def __init__(self, coordinator, d: ButtonDef) -> None:
        super().__init__(coordinator, d.key, d.name, REG_RUN)
        if d.icon:
            self._attr_icon = d.icon

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and not self.coordinator.offline

    async def async_press(self) -> None:
        self._guard()
        await self.coordinator.async_restart()
