"""
This integration pulls account-level buying signals from Clay.
It reads pre-enriched rows like funding, hiring, and expansion events and
returns them in a consistent shape so the team can prioritize outbound motion.
"""

from __future__ import annotations

import csv
import json
import logging
import os
from pathlib import Path
from typing import Any, Type

import requests
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from shared.http import get_retrying_session, session_timeout

logger = logging.getLogger(__name__)
_clay_session: requests.Session | None = None
CLAY_API_BASES = ("https://api.clay.com/v3", "https://api.clay.com/v2")
LOCAL_SIGNAL_COLUMNS = (
    "company_name",
    "domain",
    "signal_type",
    "headline",
    "details",
    "source_url",
)


def _clay_http() -> requests.Session:
    # Use one shared session so provider reliability settings stay consistent.
    global _clay_session
    if _clay_session is None:
        _clay_session = get_retrying_session(service_name="clay")
    return _clay_session


class ClaySearchInput(BaseModel):
    query: str = Field(
        description=(
            "Search filter to apply against the Clay signals table. "
            "Examples: 'series A funding', 'new VP of Engineering hire', "
            "'healthcare expansion'. Leave empty to pull all recent rows."
        )
    )


class ClaySignalSearchTool(BaseTool):
    name: str = "Clay Signal Search"
    description: str = (
        "Query a Clay enrichment table for companies showing high-intent "
        "buying signals such as recent funding rounds, leadership changes, "
        "or market expansion events. Returns structured JSON rows."
    )
    args_schema: Type[BaseModel] = ClaySearchInput

    def _run(self, query: str = "") -> str:
        # Reliability path:
        # 1) Live Clay API (if configured)
        # 2) Local signals file fallback
        # 3) Built-in demo rows
        api_key = os.getenv("CLAY_API_KEY")
        table_id = os.getenv("CLAY_TABLE_ID")

        if api_key and table_id:
            rows = self._fetch_clay_rows(api_key, table_id, query)
            if rows is not None:
                return rows
            return self._local_or_demo_signals(
                query=query,
                reason="Clay request failed",
            )

        missing: list[str] = []
        if not api_key:
            missing.append("CLAY_API_KEY")
        if not table_id:
            missing.append("CLAY_TABLE_ID")
        reason = f"Clay config missing: {', '.join(missing)}"
        logger.warning("%s. Using fallback source.", reason)
        return self._local_or_demo_signals(query=query, reason=reason)

    def _fetch_clay_rows(
        self, api_key: str, table_id: str, query: str
    ) -> str | None:
        # Business flow:
        # - Pull latest qualifying signal rows from Clay.
        # - Return clean JSON that the monitor can validate and prioritize.
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        params: dict[str, Any] = {"limit": 25}
        if query:
            params["q"] = query

        http = _clay_http()
        last_error: str | None = None
        for api_base in CLAY_API_BASES:
            try:
                resp = http.get(
                    f"{api_base}/tables/{table_id}/rows",
                    headers=headers,
                    params=params,
                    timeout=session_timeout(http),
                )
                resp.raise_for_status()
                data = resp.json()

                rows = data.get("data", data.get("rows", []))
                logger.info(
                    "Clay returned %d rows via %s for query=%r",
                    len(rows),
                    api_base,
                    query,
                )
                return json.dumps(rows, indent=2, default=str)
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                last_error = str(exc)
                # Try next API version when we still have one to test.
                if api_base != CLAY_API_BASES[-1]:
                    logger.warning(
                        "Clay HTTP %s via %s. Trying next base.",
                        status,
                        api_base,
                    )
                    continue
                logger.error("Clay API HTTP error (%s): %s", api_base, exc)
            except requests.RequestException as exc:
                last_error = str(exc)
                if api_base != CLAY_API_BASES[-1]:
                    logger.warning("Clay request failed via %s. Trying next base.", api_base)
                    continue
                logger.error("Clay API request failed (%s): %s", api_base, exc)

        logger.error("Clay request failed on all bases: %s", last_error or "unknown")
        return None

    def _local_or_demo_signals(self, *, query: str, reason: str) -> str:
        local_rows = self._load_local_signals(query=query)
        if local_rows is not None:
            logger.info(
                "Using local fallback signals (%d rows) due to: %s",
                len(local_rows),
                reason,
            )
            return json.dumps(local_rows, indent=2)
        logger.info("Local fallback unavailable. Using built-in demo due to: %s", reason)
        return self._demo_signals(query)

    def _load_local_signals(self, *, query: str) -> list[dict[str, str]] | None:
        path = self._resolve_local_signals_path()
        if not path.exists():
            return None
        if path.suffix.lower() == ".json":
            return self._load_local_json(path=path, query=query)
        return self._load_local_csv(path=path, query=query)

    @staticmethod
    def _resolve_local_signals_path() -> Path:
        configured = os.getenv("LOCAL_SIGNALS_PATH")
        if configured:
            candidate = Path(configured).expanduser()
            if not candidate.is_absolute():
                candidate = Path.cwd() / candidate
            return candidate
        return Path(__file__).resolve().parents[1] / "data" / "fallback_signals.csv"

    @staticmethod
    def _normalize_row(row: dict[str, Any]) -> dict[str, str]:
        return {
            "company_name": str(row.get("company_name", "")).strip(),
            "domain": str(row.get("domain", "")).strip(),
            "signal_type": str(row.get("signal_type", "")).strip(),
            "headline": str(row.get("headline", "")).strip(),
            "details": str(row.get("details", "")).strip(),
            "source_url": str(row.get("source_url", "")).strip(),
        }

    @staticmethod
    def _apply_query_filter(
        rows: list[dict[str, str]], *, query: str
    ) -> list[dict[str, str]]:
        q = query.strip().lower()
        if not q:
            return rows
        filtered: list[dict[str, str]] = []
        for row in rows:
            haystack = " ".join(
                row.get(col, "") for col in LOCAL_SIGNAL_COLUMNS
            ).lower()
            if q in haystack:
                filtered.append(row)
        return filtered

    def _load_local_csv(self, *, path: Path, query: str) -> list[dict[str, str]] | None:
        try:
            with path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                if reader.fieldnames is None:
                    logger.error("Local fallback CSV has no header: %s", path)
                    return None
                rows = [
                    self._normalize_row(row)
                    for row in reader
                    if row.get("company_name")
                ]
        except OSError as exc:
            logger.error("Failed reading local fallback CSV (%s): %s", path, exc)
            return None

        return self._apply_query_filter(rows, query=query)

    def _load_local_json(self, *, path: Path, query: str) -> list[dict[str, str]] | None:
        try:
            with path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Failed reading local fallback JSON (%s): %s", path, exc)
            return None

        if not isinstance(payload, list):
            logger.error("Local fallback JSON must be a list of objects: %s", path)
            return None
        rows = [
            self._normalize_row(row)
            for row in payload
            if isinstance(row, dict) and row.get("company_name")
        ]
        return self._apply_query_filter(rows, query=query)

    @staticmethod
    def _demo_signals(query: str) -> str:
        """Return realistic sample data when no Clay API key is set."""
        logger.info(
            "CLAY_API_KEY not set — returning demo signal data (query=%r).",
            query,
        )
        demo = [
            {
                "company_name": "Vela Health",
                "domain": "velahealth.com",
                "signal_type": "funding_round",
                "headline": "Vela Health closes $18M Series A to modernize post-acute care coordination",
                "details": (
                    "Vela Health announced an $18M Series A led by General Catalyst. "
                    "The company builds care coordination software for home health "
                    "and hospice agencies and plans to expand its engineering team."
                ),
                "source_url": "https://techcrunch.com/example/vela-health-series-a",
            },
            {
                "company_name": "Medallion",
                "domain": "medallion.co",
                "signal_type": "funding_round",
                "headline": "Medallion raises $65M Series C for provider network management platform",
                "details": (
                    "Medallion secured $65M in Series C funding to scale its "
                    "credentialing and payer enrollment automation platform. "
                    "They serve large health systems and digital health companies."
                ),
                "source_url": "https://techcrunch.com/example/medallion-series-c",
            },
            {
                "company_name": "Elation Health",
                "domain": "elationhealth.com",
                "signal_type": "expansion",
                "headline": "Elation Health expands EHR platform with new claims management module",
                "details": (
                    "Elation Health is adding direct claims submission capabilities "
                    "to its primary care EHR. The company currently serves over "
                    "35,000 clinicians and is hiring backend engineers for the "
                    "new billing infrastructure."
                ),
                "source_url": "https://elationhealth.com/blog/claims-expansion",
            },
        ]
        return json.dumps(demo, indent=2)
