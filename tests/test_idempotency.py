"""Test idempotency storage used to dedupe outbound side effects.

These checks assert stable key generation and correct SQLite state transitions
for first-write and duplicate-write behavior. They are critical because
duplicate Slack deliveries are a core production risk this layer mitigates.
"""

import tempfile
import uuid
from pathlib import Path

import pytest

from shared.idempotency import (
    record_successful_send,
    slack_delivery_key,
    was_already_sent,
)


@pytest.fixture
def empty_db_path(monkeypatch: pytest.MonkeyPatch) -> Path:
    d = Path(tempfile.mkdtemp()) / "test.sqlite"
    monkeypatch.setenv("IDEMPOTENCY_DB_PATH", str(d))
    return d


def test_dedupe_key_stable(empty_db_path: Path) -> None:
    r = uuid.uuid4()
    l = uuid.uuid4()
    k1 = slack_delivery_key(r, l)
    k2 = slack_delivery_key(r, l)
    assert k1 == k2


def test_not_sent_then_recorded(empty_db_path: Path) -> None:
    r = uuid.uuid4()
    l = uuid.uuid4()
    k = slack_delivery_key(r, l)
    assert was_already_sent(k) is False
    record_successful_send(k, {"a": 1})
    assert was_already_sent(k) is True
    record_successful_send(k, {"a": 1})
    assert was_already_sent(k) is True
