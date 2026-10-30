"""Cienka warstwa nad pymodbus: jedno połączenie, jedna blokada, przerwy i ponowienia.

Rozróżnia trzy sytuacje, bo falownik on-grid w nocy nie ma zasilania:
* HyponConnectionError - nie można połączyć się z konwerterem (Waveshare),
* HyponNoResponse      - konwerter działa, ale falownik nie odpowiada (np. noc),
* HyponDeviceError     - falownik odpowiedział wyjątkiem Modbus (np. nieobsługiwany rejestr).
"""
from __future__ import annotations

import asyncio
import inspect
import logging

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from .const import REQUEST_GAP

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
        self, host: str, port: int, slave: int, timeout: float = 3, retries: int = 2
    ) -> None:
        self._slave = slave
        self._retries = max(0, int(retries))
        self._lock = asyncio.Lock()
        # ponowienia realizujemy sami (z przerwą i możliwością wyłączenia w trybie czuwania)
        self._client = AsyncModbusTcpClient(host, port=port, timeout=timeout, retries=0)
        params = inspect.signature(self._client.read_holding_registers).parameters
        # pymodbus >= 3.10 używa device_id, starsze slave
        self._id_kw = "device_id" if "device_id" in params else "slave"

    async def _ensure_connected(self) -> None:
        if self._client.connected:
            return
        try:
            await self._client.connect()
        except (OSError, ModbusException, asyncio.TimeoutError) as err:
            raise HyponConnectionError(str(err)) from err
        if not self._client.connected:
            raise HyponConnectionError("Nie można połączyć się z konwerterem")

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

    async def _call(self, func, label: str, retries: int | None, *args, **kwargs):
        """Wywołanie z ponowieniami. Zwraca odpowiedź pymodbus (bez błędu)."""
        attempts = (self._retries if retries is None else max(0, retries)) + 1
        last = "brak odpowiedzi"
        for attempt in range(attempts):
            await self._ensure_connected()
            try:
                rr = await func(*args, **kwargs, **{self._id_kw: self._slave})
            except (OSError, ModbusException, asyncio.TimeoutError) as err:
                last = str(err) or type(err).__name__
                await self._close()  # po timeoucie numeracja transakcji może się rozjechać
            else:
                if not rr.isError():
                    await asyncio.sleep(REQUEST_GAP)
                    return rr
                code = getattr(rr, "exception_code", None)
                if code is not None and code not in GATEWAY_CODES:
                    await asyncio.sleep(REQUEST_GAP)
                    raise HyponDeviceError(f"{label}: wyjątek Modbus {code}", code)
                last = f"bramka: falownik nie odpowiada (kod {code})" if code else str(rr)
            _LOGGER.debug("%s: próba %s/%s nieudana (%s)", label, attempt + 1, attempts, last)
            await asyncio.sleep(REQUEST_GAP)
        raise HyponNoResponse(f"{label}: {last}")

    async def read(self, start: int, count: int, retries: int | None = None) -> list[int]:
        async with self._lock:
            rr = await self._call(
                self._client.read_holding_registers, f"Odczyt {start}+{count}", retries,
                start, count=count,
            )
            return list(rr.registers)

    async def write(self, address: int, values: list[int]) -> None:
        """Zapis: jeden rejestr funkcją 06, kilka - funkcją 16 (06 -> 16, gdy falownik nie obsługuje 06)."""
        async with self._lock:
            label = f"Zapis {address}={values}"
            if len(values) == 1:
                try:
                    await self._call(self._client.write_register, label, None, address, values[0])
                    return
                except HyponDeviceError as err:
                    if err.code != ILLEGAL_FUNCTION:
                        raise
                    _LOGGER.debug("Funkcja 06 nieobsługiwana - zapis funkcją 16")
            await self._call(self._client.write_registers, label, None, address, list(values))
