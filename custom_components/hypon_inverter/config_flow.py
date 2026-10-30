"""Konfiguracja przez UI."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .client import HyponClient, HyponConnectionError, HyponDeviceError, HyponNoResponse
from .const import (
    CONF_LOCK_MINUTES,
    CONF_RETRIES,
    CONF_SCAN_INTERVAL,
    CONF_SLAVE,
    CONF_TIMEOUT,
    DEFAULT_LOCK_MINUTES,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_RETRIES,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLAVE,
    DEFAULT_TIMEOUT,
    DOMAIN,
)
from .registers import REG_STATE


def _box(minimum: int, maximum: int, unit: str | None = None) -> vol.All:
    """Pole liczbowe (pole tekstowe zamiast suwaka) zwracające int."""
    config = NumberSelectorConfig(min=minimum, max=maximum, step=1, mode=NumberSelectorMode.BOX)
    if unit:  # klucz bez wartości (None) jest odrzucany przez walidację selektora
        config["unit_of_measurement"] = unit
    return vol.All(NumberSelector(config), vol.Coerce(int))


class HyponConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._pending: dict | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return HyponOptionsFlow()

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(
                f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}:{user_input[CONF_SLAVE]}"
            )
            self._abort_if_unique_id_configured()
            client = HyponClient(
                user_input[CONF_HOST], user_input[CONF_PORT], user_input[CONF_SLAVE], retries=1
            )
            try:
                await client.connect()
                await client.read(REG_STATE, 1)  # stan falownika
            except HyponConnectionError:
                errors["base"] = "cannot_connect"
            except HyponNoResponse:
                # konwerter działa, falownik milczy (np. noc) - zapytaj, czy dodać mimo to
                self._pending = user_input
                return await self.async_step_no_response()
            except HyponDeviceError:
                return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)
            else:
                return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)
            finally:
                await client.close()

        d = user_input or {}
        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=d.get(CONF_NAME, DEFAULT_NAME)): str,
                vol.Required(CONF_HOST, default=d.get(CONF_HOST, "")): str,
                vol.Required(CONF_PORT, default=d.get(CONF_PORT, DEFAULT_PORT)): _box(1, 65535),
                vol.Required(CONF_SLAVE, default=d.get(CONF_SLAVE, DEFAULT_SLAVE)): _box(1, 247),
                vol.Required(
                    CONF_SCAN_INTERVAL, default=d.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                ): _box(2, 300, "s"),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_no_response(self, user_input=None):
        if user_input is not None and self._pending is not None:
            return self.async_create_entry(title=self._pending[CONF_NAME], data=self._pending)
        return self.async_show_form(step_id="no_response", data_schema=vol.Schema({}))


class HyponOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input=None):
        entry = self.config_entry
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        def get(key, default):
            return entry.options.get(key, entry.data.get(key, default))

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL, default=get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                    ): _box(2, 300, "s"),
                    vol.Required(CONF_TIMEOUT, default=get(CONF_TIMEOUT, DEFAULT_TIMEOUT)): _box(
                        1, 10, "s"
                    ),
                    vol.Required(CONF_RETRIES, default=get(CONF_RETRIES, DEFAULT_RETRIES)): _box(
                        0, 5
                    ),
                    vol.Required(
                        CONF_LOCK_MINUTES, default=get(CONF_LOCK_MINUTES, DEFAULT_LOCK_MINUTES)
                    ): _box(1, 1440, "min"),
                }
            ),
        )
