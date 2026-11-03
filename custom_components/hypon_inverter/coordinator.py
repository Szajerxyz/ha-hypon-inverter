"""Koordynator odpytywania falownika."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .client import HyponClient, HyponConnectionError, HyponDeviceError, HyponError, HyponNoResponse
from .const import (
    CONF_LOCK_MINUTES,
    CONF_SCAN_INTERVAL,
    CONF_TOLERANCE,
    DEFAULT_LOCK_MINUTES,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TOLERANCE,
    DOMAIN,
    INFO_EVERY,
    OFFLINE_INTERVAL,
    RESTART_DELAY,
    SLOW_EVERY,
)
from .registers import ALL_ADDRESSES, FAST_BLOCKS, INFO_BLOCKS, REG_RUN, REG_STATE, SLOW_BLOCKS
from .writelock import WriteLock

_LOGGER = logging.getLogger(__name__)

ERROR_TEXT = {
    1: "funkcja nieobsługiwana",
    2: "nieprawidłowy adres rejestru",
    3: "wartość poza zakresem akceptowanym przez falownik",
    4: "błąd urządzenia (parametr nie może być teraz zapisany)",
    6: "falownik zajęty, spróbuj ponownie",
}


class HyponCoordinator(DataUpdateCoordinator[dict[int, int]]):
    """Czyta rejestry blokami; słownik: adres -> surowa wartość 16-bit.

    Gdy falownik przestaje odpowiadać (w nocy nie ma zasilania), koordynator przechodzi w tryb
    czuwania (offline): zachowuje ostatnie dane, a co OFFLINE_INTERVAL s wysyła jedno krótkie
    zapytanie bez ponowień, żeby nie blokować wspólnej magistrali.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: HyponClient) -> None:
        self._interval = timedelta(
            seconds=entry.options.get(
                CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            )
        )
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=self._interval,
        )
        self.client = client
        self.names = None  # ustawiane w async_setup_entry (obiekt Names)
        self.write_lock = WriteLock(entry.options.get(CONF_LOCK_MINUTES, DEFAULT_LOCK_MINUTES))
        # ile kolejnych cykli bez odpowiedzi, zanim uznamy, że falownik śpi (noc)
        self.tolerance = max(1, int(entry.options.get(CONF_TOLERANCE, DEFAULT_TOLERANCE)))
        self._relock_unsub = None
        self.offline = False
        self.last_online: datetime | None = None
        self._fails = 0
        self._cycle = 0
        self._force_slow = False
        self._split: set[tuple[int, int]] = set()
        self._bad: set[int] = set()

    # ------------------------------------------------------------------ odczyt
    async def _read_block(self, block: tuple[int, int], data: dict[int, int]) -> None:
        start, count = block
        if block not in self._split:
            try:
                regs = await self.client.read(start, count)
            except HyponDeviceError:
                if count == 1:
                    self._bad.add(start)
                    return
                _LOGGER.debug("Blok %s+%s odrzucony - czytam rejestry pojedynczo", start, count)
                self._split.add(block)
            else:
                data.update(zip(range(start, start + count), regs))
                return
        for addr in range(start, start + count):
            if addr not in ALL_ADDRESSES or addr in self._bad:
                continue
            try:
                regs = await self.client.read(addr, 1)
            except HyponDeviceError:
                _LOGGER.debug("Rejestr %s niedostępny - pomijam", addr)
                self._bad.add(addr)
                continue
            data[addr] = regs[0]

    async def _set_offline(self) -> None:
        if not self.offline:
            _LOGGER.info("Falownik nie odpowiada (brak zasilania z PV?) - tryb czuwania")
            # jednorazowo świeże połączenie na czas czuwania (gdyby gniazdo było martwe)
            await self.client.close()
        self.offline = True
        self.update_interval = timedelta(seconds=OFFLINE_INTERVAL)

    def _set_online(self) -> None:
        if self.offline:
            _LOGGER.info("Falownik odpowiada - wznowienie odczytów")
        self.offline = False
        self._fails = 0
        self._cycle = 0  # pierwszy cykl po wybudzeniu czyta wszystko
        self.update_interval = self._interval

    async def _async_update_data(self) -> dict[int, int]:
        data = dict(self.data or {})
        try:
            if self.offline:
                try:
                    await self.client.read(REG_STATE, 1, retries=0, count_errors=False)
                except HyponNoResponse:
                    return data
                except HyponDeviceError:
                    pass  # falownik odpowiedział (wyjątkiem) - działa
                self._set_online()
            self._cycle += 1
            first = self._cycle == 1
            blocks = list(FAST_BLOCKS)
            if first or self._force_slow or self._cycle % SLOW_EVERY == 0:
                blocks += SLOW_BLOCKS
            if first or self._cycle % INFO_EVERY == 0:
                blocks += INFO_BLOCKS
            self._force_slow = False
            for block in blocks:
                await self._read_block(block, data)
        except HyponConnectionError as err:
            raise UpdateFailed(f"Brak połączenia z konwerterem: {err}") from err
        except HyponNoResponse as err:
            self._fails += 1
            if self._fails >= self.tolerance or not data:
                await self._set_offline()
            else:
                _LOGGER.debug("Falownik nie odpowiedział (%s/%s): %s", self._fails, self.tolerance, err)
                self._cycle -= 1  # powtórz ten sam zestaw bloków w następnym cyklu
            return data
        self._fails = 0
        self.last_online = dt_util.now()
        return data

    # ------------------------------------------------------------------ zapis
    async def async_write(self, address: int, values: list[int]) -> None:
        """Zapis rejestru (lub kilku kolejnych) + natychmiastowe odświeżenie."""
        if self.offline:
            raise HomeAssistantError("Falownik nie odpowiada (brak zasilania z PV) - zapis niemożliwy.")
        try:
            await self.client.write(address, values)
        except HyponError as err:
            code = getattr(err, "code", None)
            text = ERROR_TEXT.get(code, f"kod błędu {code}") if code is not None else str(err)
            raise HomeAssistantError(f"Zapis do falownika nie powiódł się: {text}") from err
        self._force_slow = True
        self.async_set_updated_data(
            {**(self.data or {}), **{address + i: v for i, v in enumerate(values)}}
        )
        await self.async_request_refresh()

    async def async_restart(self) -> None:
        """Restart: Stop -> przerwa -> Start (rozpiska nie ma osobnego polecenia restartu)."""
        await self.async_write(REG_RUN, [1])
        await asyncio.sleep(RESTART_DELAY)
        try:
            await self.async_write(REG_RUN, [0])
        except HomeAssistantError:
            await asyncio.sleep(2)
            try:
                await self.async_write(REG_RUN, [0])
            except HomeAssistantError as err:
                raise HomeAssistantError(
                    "Falownik zatrzymany, ale polecenie Start nie dotarło. "
                    "Włącz go encją „Praca falownika (start/stop)”."
                ) from err

    async def async_read_range(self, start: int, count: int) -> dict[int, int | None]:
        """Odczyt zakresu rejestrów (do diagnostyki); niedostępne -> None."""
        result: dict[int, int | None] = {}
        pos, end = start, start + count
        while pos < end:
            n = min(32, end - pos)
            try:
                regs = await self.client.read(pos, n)
                result.update(zip(range(pos, pos + n), regs))
            except HyponDeviceError:
                for addr in range(pos, pos + n):
                    try:
                        result[addr] = (await self.client.read(addr, 1))[0]
                    except HyponDeviceError:
                        result[addr] = None
            pos += n
        return result

    # ------------------------------------------------------------------ blokada ustawień
    def ensure_writable(self, context=None) -> None:
        """Zapisy od użytkownika (UI, aplikacja) wymagają odblokowania; automatyzacje przechodzą."""
        if not self.write_lock.allows(getattr(context, "user_id", None)):
            raise ServiceValidationError(
                "Ustawienia falownika są zablokowane. Odblokuj je encją „Blokada ustawień”."
            )

    @callback
    def async_unlock(self) -> None:
        self.write_lock.grant()
        self._cancel_relock()
        self._relock_unsub = async_call_later(
            self.hass, self.write_lock.remaining + 1, self._relock_expired
        )
        self.async_update_listeners()

    @callback
    def async_lock(self) -> None:
        self.write_lock.lock()
        self._cancel_relock()
        self.async_update_listeners()

    @callback
    def _relock_expired(self, _now) -> None:
        self._relock_unsub = None
        self.async_update_listeners()

    def _cancel_relock(self) -> None:
        if self._relock_unsub is not None:
            self._relock_unsub()
            self._relock_unsub = None

    async def async_shutdown(self) -> None:
        self._cancel_relock()
        await super().async_shutdown()
