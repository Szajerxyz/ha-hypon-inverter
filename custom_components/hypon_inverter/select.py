"""Listy wyboru (tryb sterowania mocą, typ licznika); etykiety z names/<język>.json."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HyponConfigEntry
from .entity import HyponWritableEntity
from .registers import SELECTS, SelectDef


async def async_setup_entry(
    hass: HomeAssistant, entry: HyponConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(HyponSelect(entry.runtime_data, d) for d in SELECTS)


class HyponSelect(HyponWritableEntity, SelectEntity):
    def __init__(self, coordinator, d: SelectDef) -> None:
        super().__init__(coordinator, d.key, d.name, d.address)
        self._d = d
        self._labels = {
            raw: coordinator.names.option(d.key, option) for raw, option in d.options.items()
        }
        self._attr_options = list(self._labels.values())
        if d.icon:
            self._attr_icon = d.icon

    @property
    def current_option(self) -> str | None:
        raw = self._raw
        return None if raw is None else self._labels.get(raw)

    @property
    def extra_state_attributes(self) -> dict[str, int | None]:
        # Surowa wartość rejestru - przydatna, gdy falownik zwróci wartość spoza rozpiski
        return {"raw_value": self._raw}

    async def async_select_option(self, option: str) -> None:
        self._guard()
        value = next(raw for raw, label in self._labels.items() if label == option)
        await self.coordinator.async_write(self._address, [value])
