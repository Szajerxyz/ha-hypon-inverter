"""Wspólna klasa encji i urządzenia (grupy)."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import HyponCoordinator
from .groups import GROUP_LABELS, GROUP_NUMBER, group_of
from .registers import combine


def device_name(entry, group: str, names) -> str:
    """Nazwa urządzenia: "<nazwa> – <numer>. <opis grupy>", np. "Falownik Hypontech – 1. Informacje"."""
    label = names.group(group, GROUP_LABELS[group])
    return f"{entry.title} – {GROUP_NUMBER[group]}. {label}"


def device_info_for(entry, key: str, names) -> DeviceInfo:
    """Urządzenie (grupa) dla danej encji; "info" = główne urządzenie."""
    group = group_of(key)
    if group == "info":
        return DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=device_name(entry, group, names),
            manufacturer=MANUFACTURER,
            model=MODEL,
        )
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_{group}")},
        name=device_name(entry, group, names),
        manufacturer=MANUFACTURER,
        model=MODEL,
        via_device=(DOMAIN, entry.entry_id),
    )


class HyponEntity(CoordinatorEntity[HyponCoordinator]):
    # Pełne nazwy z prefiksem "Hypon" (jak w SRNE), bez nazwy urządzenia
    _attr_has_entity_name = False

    def __init__(
        self, coordinator: HyponCoordinator, key: str, name: str, address: int, words: int = 1
    ) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._key = key
        self._address = address
        self._words = words
        self._attr_name = coordinator.names.name(key, name)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = device_info_for(entry, key, coordinator.names)

    def _guard(self) -> None:
        """Blokada ustawień: zgłasza błąd, jeśli zapis od użytkownika jest zablokowany."""
        self.coordinator.ensure_writable(getattr(self, "_context", None))

    @property
    def _data(self) -> dict[int, int]:
        return self.coordinator.data or {}

    @property
    def _raw(self) -> int | None:
        """Surowa wartość (dla words=2: starsze słowo pod niższym adresem)."""
        return combine(self._data, self._address, self._words)

    @property
    def available(self) -> bool:
        return super().available and self._raw is not None


class HyponWritableEntity(HyponEntity):
    """Ustawienia: niedostępne, gdy falownik nie odpowiada (nie da się ich zapisać)."""

    @property
    def available(self) -> bool:
        return super().available and not self.coordinator.offline
