"""Translation entrypoints."""

from __future__ import annotations

from typing import Any

from weavbot.i18n.catalog_cli import CLI_TRANSLATIONS
from weavbot.i18n.locale import detect_locale, normalize_locale

_CURRENT_LOCALE = detect_locale()


def set_locale(value: str) -> None:
    """Set active locale for this process."""
    global _CURRENT_LOCALE
    _CURRENT_LOCALE = normalize_locale(value)


def get_locale() -> str:
    """Get active locale for this process."""
    return _CURRENT_LOCALE


def t(key: str, *args: Any) -> str:
    """Translate key with active locale, fallback to English and then key."""
    trans = CLI_TRANSLATIONS.get(_CURRENT_LOCALE) or CLI_TRANSLATIONS.get("en") or {}
    text = trans.get(key) or CLI_TRANSLATIONS.get("en", {}).get(key) or key
    if args:
        try:
            return text.format(*args)
        except (IndexError, KeyError):
            return text
    return text
