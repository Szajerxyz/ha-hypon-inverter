"""Parametry liczbowe do zapisu (z walidacją zakresu)."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import HyponConfigEntry
from .entity import HyponWritableEntity
from .registers import NUMBERS, NumberDef, split_words, to_signed


async def async_setup_entry(
    hass: HomeAssistant, entry: HyponConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(HyponNumber(entry.runtime_data, d) for d in NUMBERS)


def encode_number(d: NumberDef, value: float) -> list[int]:
    """Wartość -> rejestry (walidacja zakresu i kroku)."""
    if not d.minimum <= value <= d.maximum:
        raise ServiceValidationError(
            f"Dozwolony zakres: {d.minimum:g}–{d.maximum:g}{(' ' + d.unit) if d.unit else ''}"
        )
    raw = int(round(value / d.scale))
    return split_words(raw, d.words)


class HyponNumber(HyponWritableEntity, NumberEntity):
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator, d: NumberDef) -> None:
        super().__init__(coordinator, d.key, d.name, d.address, d.words)
        self._d = d
        self._attr_native_min_value = d.minimum
        self._attr_native_max_value = d.maximum
        self._attr_native_step = d.step
        self._attr_native_unit_of_measurement = d.unit
        if d.icon:
            self._attr_icon = d.icon

    @property
    def native_value(self) -> float | None:
        raw = self._raw
        if raw is None:
            return None
        if self._d.signed:
            raw = to_signed(raw, 16 * self._d.words)
        return round(raw * self._d.scale, 3)

    async def async_set_native_value(self, value: float) -> None:
        self._guard()
        await self.coordinator.async_write(self._address, encode_number(self._d, value))
