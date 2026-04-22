"""
This file prevents duplicate external actions like repeated Slack lead alerts.
It stores a lightweight send-history key so retries and restarts do not create
double notifications, which protects seller trust and reporting accuracy.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from uuid import UUID

from shared.versioning import PIPELINE_SCHEMA_VERSION

DEFAULT_DB = Path(__file__).resolve().parent.parent / "output" / ".intent_outbound_dedupe.sqlite"


def _db_path() -> Path:
    raw = os.getenv("IDEMPOTENCY_DB_PATH", "")
    if raw.strip():
        return Path(raw)
    return DEFAULT_DB


def _ensure_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _connect() -> sqlite3.Connection:
    p = _db_path()
    _ensure_dir(p)
    conn = sqlite3.connect(str(p), timeout=30.0)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS idempotency_keys (
            idempotency_key TEXT PRIMARY KEY,
            created_at REAL NOT NULL,
            payload_hash TEXT
        )
        """
    )
    conn.commit()
    return conn


def slack_delivery_key(run_id: UUID, lead_id: UUID) -> str:
    base = f"{run_id!s}|{lead_id!s}|slack|{PIPELINE_SCHEMA_VERSION}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def was_already_sent(key: str) -> bool:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT 1 FROM idempotency_keys WHERE idempotency_key = ?",
            (key,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def record_successful_send(key: str, payload: dict | None = None) -> None:
    ph = None
    if payload is not None:
        ph = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
    conn = _connect()
    now = time.time()
    try:
        conn.execute(
            "INSERT INTO idempotency_keys (idempotency_key, created_at, payload_hash) VALUES (?, ?, ?)",
            (key, now, ph),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
    finally:
        conn.close()
