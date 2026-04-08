"""
Clay API integration tool for the Signal Monitor agent.

Queries a Clay enrichment table for companies exhibiting high-intent
buying signals (funding rounds, leadership changes, expansion events).
The table is assumed to be pre-configured in Clay with relevant
enrichment columns — this tool reads the output rows.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Type

import requests
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

CLAY_API_BASE = "https://api.clay.com/v3"


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
        api_key = os.getenv("CLAY_API_KEY")
        table_id = os.getenv("CLAY_TABLE_ID")

        if not api_key:
            return self._demo_signals(query)

        if not table_id:
            logger.error("CLAY_TABLE_ID is not configured.")
            return json.dumps({"error": "CLAY_TABLE_ID missing"})

        return self._fetch_clay_rows(api_key, table_id, query)

    def _fetch_clay_rows(
        self, api_key: str, table_id: str, query: str
    ) -> str:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        params: dict[str, Any] = {"limit": 25}
        if query:
            params["q"] = query

        try:
            resp = requests.get(
                f"{CLAY_API_BASE}/tables/{table_id}/rows",
                headers=headers,
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            rows = data.get("data", data.get("rows", []))
            logger.info(
                "Clay returned %d rows for query=%r", len(rows), query
            )
            return json.dumps(rows, indent=2, default=str)

        except requests.HTTPError as exc:
            logger.error("Clay API HTTP error: %s", exc)
            return json.dumps({"error": str(exc)})
        except requests.RequestException as exc:
            logger.error("Clay API request failed: %s", exc)
            return json.dumps({"error": str(exc)})

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
