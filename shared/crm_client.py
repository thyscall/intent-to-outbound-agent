"""
Lightweight CRM abstraction layer.

Provides a unified write interface for logging pipeline results to
Salesforce, HubSpot, or a local JSON fallback when no CRM is configured.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from shared.schemas import PipelineResult

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"


class CRMClient(Protocol):
    def push_lead(self, result: PipelineResult) -> str: ...


class LocalJSONClient:
    """Appends pipeline results to a newline-delimited JSON file on disk."""

    def __init__(self, filepath: Path | None = None):
        self.filepath = filepath or OUTPUT_DIR / "leads.jsonl"
        self.filepath.parent.mkdir(parents=True, exist_ok=True)

    def push_lead(self, result: PipelineResult) -> str:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **result.model_dump(mode="json"),
        }
        with open(self.filepath, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")

        logger.info("Lead written to %s", self.filepath)
        return str(self.filepath)


class SalesforceClient:
    """Placeholder for a real Salesforce integration via simple-salesforce."""

    def __init__(self):
        self.instance_url = os.getenv("SF_INSTANCE_URL", "")
        self.access_token = os.getenv("SF_ACCESS_TOKEN", "")

    def push_lead(self, result: PipelineResult) -> str:
        logger.warning(
            "SalesforceClient.push_lead called but not implemented — "
            "falling back to local JSON."
        )
        return LocalJSONClient().push_lead(result)


class HubSpotClient:
    """Placeholder for a real HubSpot integration via hubspot-api-client."""

    def __init__(self):
        self.api_key = os.getenv("HUBSPOT_API_KEY", "")

    def push_lead(self, result: PipelineResult) -> str:
        logger.warning(
            "HubSpotClient.push_lead called but not implemented — "
            "falling back to local JSON."
        )
        return LocalJSONClient().push_lead(result)


def get_crm_client() -> CRMClient:
    """Return the best available CRM client based on environment variables."""
    if os.getenv("SF_ACCESS_TOKEN"):
        return SalesforceClient()
    if os.getenv("HUBSPOT_API_KEY"):
        return HubSpotClient()

    logger.info("No CRM credentials found — using local JSON writer.")
    return LocalJSONClient()
