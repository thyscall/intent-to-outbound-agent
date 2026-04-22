"""Provide stable provider connectivity for signal, enrichment, and delivery data.

It centralizes retry, backoff, and timeout behavior for Clay, Apollo, and Slack
so temporary API failures do not become dropped leads or missing notifications.
"""

from __future__ import annotations

import os

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

DEFAULT_MAX_RETRIES = 4
DEFAULT_BACKOFF = 0.5
DEFAULT_STATUS_FORCELIST = (429, 500, 502, 503, 504)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return int(raw)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return float(raw)


def get_retrying_session(
    *,
    service_name: str = "http",
) -> requests.Session:
    """
    Build a Session that retries on 429/5xx with exponential backoff.
    Respects Retry-After when the server sends it.
    """
    connect_s = _env_int("HTTP_CONNECT_TIMEOUT_S", 10)
    read_s = _env_int("HTTP_READ_TIMEOUT_S", 60)
    max_retries = _env_int("HTTP_MAX_RETRIES", DEFAULT_MAX_RETRIES)
    backoff = _env_float("HTTP_BACKOFF_FACTOR", DEFAULT_BACKOFF)

    retry = Retry(
        total=max_retries,
        connect=max_retries,
        read=max_retries,
        status=max_retries,
        backoff_factor=backoff,
        status_forcelist=DEFAULT_STATUS_FORCELIST,
        allowed_methods=frozenset(
            ["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS"]
        ),
        raise_on_status=False,
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_maxsize=10)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.setdefault(
        "User-Agent", f"intent-to-outbound-ai-agent/{service_name}"
    )
    session._itoa_timeout = (connect_s, read_s)  # type: ignore[attr-defined]
    return session


def session_timeout(session: requests.Session) -> tuple[float, float]:
    t = getattr(session, "_itoa_timeout", (10, 60))
    return t  # type: ignore[return-value]
