"""Validate shared HTTP client defaults used by external integrations.

These tests check that session creation exposes timeout configuration in the
shape expected by callers. They matter because timeout regressions can silently
degrade reliability across Clay, Apollo, and Slack requests.
"""

from shared.http import get_retrying_session, session_timeout


def test_session_has_timeouts() -> None:
    s = get_retrying_session(service_name="test")
    t = session_timeout(s)
    assert isinstance(t, tuple)
    assert len(t) == 2
