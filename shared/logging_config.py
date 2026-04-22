"""Standardize operational logs so GTM teams can answer what happened and why.

It emits structured events with run and lead IDs, stage names, and payload
context so failures, drop-offs, and throughput can be analyzed quickly.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import UUID

from shared.redact import redact_value

LOG_VERSION = 1


class JsonLineFormatter(logging.Formatter):
    """Render each log record as a single JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        run_id = getattr(record, "run_id", None)
        lead_id = getattr(record, "lead_id", None)
        stage = getattr(record, "stage", None)
        event = getattr(record, "event", None)
        duration_ms = getattr(record, "duration_ms", None)
        body: dict[str, Any] = {
            "v": LOG_VERSION,
            "timestamp": ts,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if run_id is not None:
            body["run_id"] = str(run_id)
        if lead_id is not None:
            body["lead_id"] = str(lead_id)
        if stage is not None:
            body["stage"] = stage
        if event is not None:
            body["event"] = event
        if duration_ms is not None:
            body["duration_ms"] = duration_ms
        extra = getattr(record, "log_payload", None)
        if isinstance(extra, dict) and extra:
            body["extra"] = redact_value(dict(extra))
        if record.exc_info and record.exc_text:
            body["exception"] = record.exc_text[:8000]
        return json.dumps(body, default=str, ensure_ascii=False)


def _env_level() -> int:
    name = os.getenv("LOG_LEVEL", "INFO").upper()
    return getattr(logging, name, logging.INFO)


def setup_logging() -> None:
    """Idempotent: attach JSON handler to root once."""
    root = logging.getLogger()
    for h in root.handlers:
        if isinstance(h, logging.StreamHandler) and isinstance(
            h.formatter, JsonLineFormatter
        ):
            return
    root.setLevel(_env_level())
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(JsonLineFormatter())
    root.addHandler(h)


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    run_id: UUID | None = None,
    lead_id: UUID | None = None,
    stage: str | None = None,
    message: str = "",
    duration_ms: float | None = None,
    extra: Mapping[str, Any] | None = None,
) -> None:
    ex: dict[str, Any] = {
        "event": event,
    }
    if run_id is not None:
        ex["run_id"] = str(run_id)
    if lead_id is not None:
        ex["lead_id"] = str(lead_id)
    if stage is not None:
        ex["stage"] = stage
    if duration_ms is not None:
        ex["duration_ms"] = duration_ms
    if extra:
        ex["log_payload"] = dict(extra)
    logger.info(message or event, extra=ex)


class StageTimer:
    __slots__ = ("_t0",)

    def __init__(self) -> None:
        self._t0 = time.perf_counter()

    def ms(self) -> float:
        return (time.perf_counter() - self._t0) * 1000.0
