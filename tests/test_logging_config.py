"""Verify structured logging emits parseable, correlated JSON lines.

This suite exercises the logger setup and formatter to ensure required fields
are present and machine-readable. It is important because observability
depends on stable log schemas for alerts, dashboards, and debugging.
"""

import json
import logging

from shared.logging_config import JsonLineFormatter, setup_logging, log_event
from uuid import uuid4


def test_json_log_line() -> None:
    setup_logging()
    logger = logging.getLogger("test_json")
    log_event(
        logger,
        "unit_test",
        run_id=uuid4(),
        lead_id=uuid4(),
        stage="test",
        message="hi",
    )
    # Smoke: formatter produces valid JSON
    fmt = JsonLineFormatter()
    r = logging.LogRecord(
        name="x", level=20, pathname="", lineno=0, msg="m", args=(), exc_info=None
    )
    r.event = "e"
    r.run_id = "rid"
    line = fmt.format(r)
    o = json.loads(line)
    assert o["level"] == "INFO"
    assert "timestamp" in o
