"""
This module stores final lead outcomes in a consistent format for GTM operations.
It chooses the available destination (CRM adapter or local JSONL fallback) and
writes a traceable record that includes status, validation results, and IDs.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from shared.schemas import PipelineResult

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"


class CRMClient(Protocol):
    def push_lead(self, result: PipelineResult) -> str: ...


def _envelope(result: PipelineResult) -> dict[str, Any]:
    # Keep metadata at top level so RevOps can query lead outcomes quickly.
    return {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "run_id": str(result.run_id),
        "lead_id": str(result.lead_id),
        "schema_version": result.schema_version,
        "terminal_status": result.terminal_status.value,
        "deterministic_validation": (
            result.deterministic_validation.model_dump(mode="json")
            if result.deterministic_validation
            else None
        ),
        "result": result.model_dump(mode="json"),
    }


class LocalJSONClient:
    """Appends versioned pipeline envelopes to a newline-delimited JSON file."""

    def __init__(self, filepath: Path | None = None):
        # Local file acts as temporary source-of-truth until full CRM coverage exists.
        self.filepath = filepath or OUTPUT_DIR / "leads.jsonl"
        self.filepath.parent.mkdir(parents=True, exist_ok=True)

    def push_lead(self, result: PipelineResult) -> str:
        # Append-only history supports audits and post-run business analysis.
        record = _envelope(result)
        with open(self.filepath, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")

        logger.info("Lead written to %s", self.filepath)
        return str(self.filepath)


class SalesforceClient:
    """Placeholder for a real Salesforce integration via simple-salesforce."""

    def __init__(self) -> None:
        self.instance_url = os.getenv("SF_INSTANCE_URL", "")
        self.access_token = os.getenv("SF_ACCESS_TOKEN", "")

    def push_lead(self, result: PipelineResult) -> str:
        # Safety behavior: if CRM sync is not ready, still preserve the lead record.
        logger.warning(
            "SalesforceClient.push_lead called but not implemented — "
            "falling back to local JSON."
        )
        return LocalJSONClient().push_lead(result)


class HubSpotClient:
    """Placeholder for a real HubSpot integration via hubspot-api-client."""

    def __init__(self) -> None:
        self.api_key = os.getenv("HUBSPOT_API_KEY", "")

    def push_lead(self, result: PipelineResult) -> str:
        # Mirror Salesforce fallback so behavior stays predictable by provider.
        logger.warning(
            "HubSpotClient.push_lead called but not implemented — "
            "falling back to local JSON."
        )
        return LocalJSONClient().push_lead(result)


def get_crm_client() -> CRMClient:
    """Return the best available CRM client based on environment variables."""
    # Provider choice is env-driven so GTM teams can switch destinations
    # without changing business logic in the orchestrator.
    if os.getenv("SF_ACCESS_TOKEN"):
        return SalesforceClient()
    if os.getenv("HUBSPOT_API_KEY"):
        return HubSpotClient()

    logger.info("No CRM credentials found — using local JSON writer.")
    return LocalJSONClient()
