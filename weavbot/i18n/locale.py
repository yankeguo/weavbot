"""Locale detection and normalization helpers."""

from __future__ import annotations

import locale
import os


def normalize_locale(value: str | None) -> str:
    """Normalize locale-like values to short language codes."""
    if not value:
        return "en"
    normalized = value.strip().lower()
    if not normalized:
        return "en"
    normalized = normalized.split(".")[0].split("_")[0].split(":")[0]
    if normalized in {"zh", "en"}:
        return normalized
    return "en"


def detect_locale() -> str:
    """Detect locale from env vars or system locale, with fallback to en."""
    override = os.environ.get("WB_LANG", "")
    if override.strip():
        return normalize_locale(override)

    for name in ("LC_ALL", "LANG", "LANGUAGE"):
        value = os.environ.get(name, "")
        if value and value != "C":
            return normalize_locale(value)

    try:
        loc = locale.getlocale()[0]
        if loc:
            return normalize_locale(loc)
    except Exception:
        pass

    return "en"
