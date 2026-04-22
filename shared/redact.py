"""Redact common PII patterns before structured logs are emitted.

This module recursively sanitizes strings, dicts, and lists to remove obvious
emails and phone numbers from log payloads. It matters for compliance because
debug visibility is preserved while reducing accidental exposure of PII.
"""

from __future__ import annotations

import os
import re
from typing import Any

EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)
# Simple US phone pattern
PHONE_RE = re.compile(
    r"\b(?:\+?1[-.\s]?)?(?:\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4})\b"
)


def _redact_str(text: str) -> str:
    t = EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    t = PHONE_RE.sub("[REDACTED_PHONE]", t)
    return t


def redact_value(value: Any) -> Any:
    if os.getenv("LOG_REDACT", "true").lower() in ("0", "false", "no"):
        return value
    if isinstance(value, str):
        return _redact_str(value)
    if isinstance(value, dict):
        return {k: redact_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_value(v) for v in value]
    return value
