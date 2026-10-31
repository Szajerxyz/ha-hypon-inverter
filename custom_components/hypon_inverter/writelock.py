"""Blokada zapisu ustawień - czysta logika (bez zależności od Home Assistant).

Falownik Hypontech nie ma hasła ustawień, więc odblokowanie nie wymaga kodu: chroni przed
przypadkową zmianą z dashboardu. Po upływie czasu ustawienia blokują się same.
"""
from __future__ import annotations

import time
from collections.abc import Callable


class WriteLock:
    """Stan blokady: zapisy od użytkowników są dozwolone tylko po odblokowaniu (na N minut).

    Zapisy bez użytkownika (automatyzacje, system) nie są blokowane przez tę klasę.
    """

    def __init__(self, minutes: int = 10, clock: Callable[[], float] = time.monotonic) -> None:
        self._minutes = max(1, int(minutes))
        self._clock = clock
        self._until = 0.0

    @property
    def unlocked(self) -> bool:
        return self._clock() < self._until

    @property
    def remaining(self) -> int:
        """Sekundy do ponownego zablokowania (0, gdy zablokowane)."""
        return max(0, int(self._until - self._clock() + 0.999))

    def grant(self) -> None:
        """Odblokuj na ustawiony czas."""
        self._until = self._clock() + self._minutes * 60

    def lock(self) -> None:
        self._until = 0.0

    def allows(self, user_id: str | None) -> bool:
        """Zapis dozwolony, gdy odblokowano albo polecenie nie pochodzi od użytkownika."""
        return self.unlocked or user_id is None
