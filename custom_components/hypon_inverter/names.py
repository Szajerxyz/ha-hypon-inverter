"""Nazwy encji, ID i etykiety w wielu językach (pliki names/<język>.json).

* ID encji powstaje zawsze z names/en.json: <domena>.hypon_<id> (angielskie, niezależne od języka HA).
* Wyświetlane nazwy i etykiety opcji pochodzą z pliku języka systemowego Home Assistant
  (np. pl.json); gdy brakuje wpisu lub pliku, używany jest en.json.
* Aby dodać język: skopiuj en.json do <kod_języka>.json i przetłumacz wartości.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)
NAMES_DIR = Path(__file__).parent / "names"


def _read(code: str) -> dict:
    path = NAMES_DIR / f"{code}.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        _LOGGER.warning("Nie można wczytać %s: %s", path.name, err)
        return {}


class Names:
    def __init__(self, language: str) -> None:
        self.language = language
        self._en = _read("en")
        lang: dict = {}
        for code in (language, language.lower(), language.split("-")[0].lower()):
            if code != "en":
                lang = _read(code)
                if lang:
                    break
        self._lang = lang
        self.prefix: str = lang.get("prefix", self._en.get("prefix", ""))

    @classmethod
    async def async_load(cls, hass: HomeAssistant) -> "Names":
        return await hass.async_add_executor_job(cls, hass.config.language)

    @staticmethod
    def _text(value) -> str | None:
        if isinstance(value, dict):
            value = value.get("name")
        return value if isinstance(value, str) else None

    def object_id(self, key: str) -> str | None:
        """Angielski identyfikator (część entity_id) z en.json."""
        entry = self._en.get("entities", {}).get(key)
        return entry.get("id") if isinstance(entry, dict) else None

    def name(self, key: str, fallback: str) -> str:
        text = (
            self._text(self._lang.get("entities", {}).get(key))
            or self._text(self._en.get("entities", {}).get(key))
            or fallback
        )
        return f"{self.prefix} {text}".strip()

    def option(self, entity_key: str, option_key: str) -> str:
        return (
            self._lang.get("options", {}).get(entity_key, {}).get(option_key)
            or self._en.get("options", {}).get(entity_key, {}).get(option_key)
            or option_key
        )

    def group(self, group: str, fallback: str) -> str:
        return (
            self._lang.get("groups", {}).get(group)
            or self._en.get("groups", {}).get(group)
            or fallback
        )

    def fault(self, table: str, code: int) -> str:
        """Tytuł usterki/ostrzeżenia (sekcje "faults" / "warnings" w names/<język>.json)."""
        key = str(code)
        return (
            self._lang.get(table, {}).get(key, {}).get("title")
            or self._en.get(table, {}).get(key, {}).get("title")
            or f"{self.common('unknown')} ({code})"
        )

    def common(self, key: str) -> str:
        return (
            self._lang.get("common", {}).get(key)
            or self._en.get("common", {}).get(key)
            or key
        )
