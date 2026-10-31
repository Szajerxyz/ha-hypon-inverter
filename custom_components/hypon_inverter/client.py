"""Cienka warstwa nad pymodbus: jedno połączenie, jedna blokada, przerwy i ponowienia.

Rozróżnia trzy sytuacje, bo falownik on-grid w nocy nie ma zasilania:
* HyponConnectionError - nie można połączyć się z konwerterem (Waveshare),
* HyponNoResponse      - konwerter działa, ale falownik nie odpowiada (np. noc),
* HyponDeviceError     - falownik odpowiedział wyjątkiem Modbus (np. nieobsługiwany rejestr).

Zasady pracy na magistrali współdzielonej z innymi integracjami (inne połączenia TCP do tego
samego konwertera):
* brak odpowiedzi NIE zrywa połączenia - konwerter przy kilku połączeniach potrafi przetrzymać
  odpowiedź kilka sekund, a spóźniona ramka musi trafić do tego samego gniazda (pymodbus odrzuci
  ją po numerze transakcji); połączenie zamykamy tylko przy błędzie łącza,
* odpowiedź o innej liczbie rejestrów niż zapytanie (cudza lub spóźniona ramka) jest odrzucana,
* statystyki (czas odpowiedzi, błędy, rozłączenia) są dostępne jako sensory diagnostyczne.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import time

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ConnectionException, ModbusException

from .const import REQUEST_GAP, RETRY_DELAY

_LOGGER = logging.getLogger(__name__)

# Wyjątki bramki Modbus TCP: 10 = ścieżka niedostępna, 11 = urządzenie docelowe nie odpowiada
GATEWAY_CODES = {10, 11}
ILLEGAL_FUNCTION = 1


class HyponError(Exception):
    """Bazowy błąd."""


class HyponConnectionError(HyponError):
    """Brak połączenia z konwerterem."""


class HyponNoResponse(HyponError):
    """Konwerter działa, falownik nie odpowiada."""


class HyponDeviceError(HyponError):
    """Falownik odpowiedział wyjątkiem Modbus."""

    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


class HyponClient:
    """Klient Modbus TCP (konwerter Waveshare w trybie Modbus TCP <-> RTU)."""

    def __init__(
        self, host: str, port: int, slave: int, timeout: float = 5, retries: int = 1
    ) -> None:
        self._slave = slave
        self._retries = max(0, int(retries))
        self._lock = asyncio.Lock()
        # ponowienia realizujemy sami (z przerwą i możliwością wyłączenia w trybie czuwania)
        self._client = AsyncModbusTcpClient(host, port=port, timeout=timeout, retries=0)
        params = inspect.signature(self._client.read_holding_registers).parameters
        # pymodbus >= 3.10 używa device_id, starsze slave
        self._id_kw = "device_id" if "device_id" in params else "slave"
        # statystyki (od uruchomienia integracji)
        self.last_response_ms: int | None = None
        self.read_errors = 0
        self.reconnects = 0
        self._connected_once = False

    async def _ensure_connected(self) -> None:
        if self._client.connected:
            return
        try:
            await self._client.connect()
        except (OSError, ModbusException, asyncio.TimeoutError) as err:
            raise HyponConnectionError(str(err)) from err
        if not self._client.connected:
            raise HyponConnectionError("Nie można połączyć się z konwerterem")
        if self._connected_once:
            self.reconnects += 1
        self._connected_once = True

    async def _close(self) -> None:
        try:
            res = self._client.close()
            if inspect.isawaitable(res):
                await res
        except Exception:  # noqa: BLE001 - zamykanie nie może przerwać obsługi błędu
            pass

    async def close(self) -> None:
        async with self._lock:
            await self._close()

    async def connect(self) -> None:
        async with self._lock:
            await self._ensure_connected()

    async def _call(self, func, label: str, retries: int | None, expect: int | None, *args, **kwargs):
        """Wywołanie z ponowieniami. Zwraca odpowiedź pymodbus (bez błędu)."""
        attempts = (self._retries if retries is None else max(0, retries)) + 1
        last = "brak odpowiedzi"
        for attempt in range(attempts):
            if attempt:
                await asyncio.sleep(RETRY_DELAY)
            await self._ensure_connected()
            start = time.monotonic()
            try:
                rr = await func(*args, **kwargs, **{self._id_kw: self._slave})
            except (ConnectionException, OSError) as err:
                # błąd łącza - zamknij, przy następnej próbie połączymy się od nowa
                last = str(err) or type(err).__name__
                await self._close()
            except (ModbusException, asyncio.TimeoutError) as err:
                # brak odpowiedzi - połączenie zostaje (spóźniona ramka trafi do tego gniazda)
                last = str(err) or type(err).__name__
            else:
                if not rr.isError():
                    regs = getattr(rr, "registers", None)
                    if expect is not None and (regs is None or len(regs) != expect):
                        last = f"odpowiedź o złej długości ({0 if regs is None else len(regs)} zamiast {expect})"
                    else:
                        self.last_response_ms = int((time.monotonic() - start) * 1000)
                        await asyncio.sleep(REQUEST_GAP)
                        return rr
                else:
                    code = getattr(rr, "exception_code", None)
                    if code is not None and code not in GATEWAY_CODES:
                        self.last_response_ms = int((time.monotonic() - start) * 1000)
                        await asyncio.sleep(REQUEST_GAP)
                        raise HyponDeviceError(f"{label}: wyjątek Modbus {code}", code)
                    last = f"bramka: falownik nie odpowiada (kod {code})" if code else str(rr)
            self.read_errors += 1
            _LOGGER.debug("%s: próba %s/%s nieudana (%s)", label, attempt + 1, attempts, last)
            await asyncio.sleep(REQUEST_GAP)
        raise HyponNoResponse(f"{label}: {last}")

    async def read(self, start: int, count: int, retries: int | None = None) -> list[int]:
        async with self._lock:
            rr = await self._call(
                self._client.read_holding_registers, f"Odczyt {start}+{count}", retries, count,
                start, count=count,
            )
            return list(rr.registers)

    async def write(self, address: int, values: list[int]) -> None:
        """Zapis: jeden rejestr funkcją 06, kilka - funkcją 16 (06 -> 16, gdy falownik nie obsługuje 06)."""
        async with self._lock:
            label = f"Zapis {address}={values}"
            if len(values) == 1:
                try:
                    await self._call(self._client.write_register, label, None, None, address, values[0])
                    return
                except HyponDeviceError as err:
                    if err.code != ILLEGAL_FUNCTION:
                        raise
                    _LOGGER.debug("Funkcja 06 nieobsługiwana - zapis funkcją 16")
            await self._call(self._client.write_registers, label, None, None, address, list(values))
