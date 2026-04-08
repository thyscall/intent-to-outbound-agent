"""
Apollo.io API integration tool for the Account Researcher agent.

Searches for target personas (VP Sales, Head of Engineering, CTO, etc.)
at a given company and returns structured contact data.
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

APOLLO_API_BASE = "https://api.apollo.io/api/v1"

TARGET_TITLES = [
    "VP of Sales",
    "VP of Engineering",
    "Head of Sales",
    "Head of Growth",
    "Chief Technology Officer",
    "Chief Revenue Officer",
    "Director of Sales",
    "Director of Engineering",
    "Co-Founder",
    "CEO",
]


class ApolloSearchInput(BaseModel):
    company_domain: str = Field(
        description="The company domain to search contacts for (e.g. 'elationhealth.com')."
    )
    target_title: str = Field(
        default="",
        description=(
            "Optional title filter such as 'VP of Sales' or 'CTO'. "
            "Leave empty to search for all senior go-to-market and engineering personas."
        ),
    )


class ApolloPersonSearchTool(BaseTool):
    name: str = "Apollo Person Search"
    description: str = (
        "Search the Apollo.io database for target personas at a specific "
        "company. Returns names, titles, emails, LinkedIn URLs, and seniority. "
        "Best used after a buying signal has been validated."
    )
    args_schema: Type[BaseModel] = ApolloSearchInput

    def _run(
        self, company_domain: str, target_title: str = ""
    ) -> str:
        api_key = os.getenv("APOLLO_API_KEY")

        if not api_key:
            return self._demo_contacts(company_domain, target_title)

        return self._search_apollo(api_key, company_domain, target_title)

    def _search_apollo(
        self, api_key: str, domain: str, title_filter: str
    ) -> str:
        headers = {
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
        }

        titles = [title_filter] if title_filter else TARGET_TITLES

        payload: dict[str, Any] = {
            "api_key": api_key,
            "q_organization_domains": domain,
            "person_titles": titles,
            "person_seniorities": [
                "vp",
                "director",
                "c_suite",
                "founder",
                "owner",
            ],
            "page": 1,
            "per_page": 5,
        }

        try:
            resp = requests.post(
                f"{APOLLO_API_BASE}/mixed_people/search",
                headers=headers,
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()

            people = data.get("people", [])
            contacts = [
                {
                    "full_name": p.get("name", "Unknown"),
                    "title": p.get("title", "Unknown"),
                    "email": p.get("email"),
                    "linkedin_url": p.get("linkedin_url"),
                    "company": p.get("organization", {}).get("name", domain),
                    "seniority": p.get("seniority", "unknown"),
                    "department": p.get("departments", ["unknown"])[0]
                    if p.get("departments")
                    else "unknown",
                }
                for p in people
            ]

            logger.info(
                "Apollo returned %d contacts for %s", len(contacts), domain
            )
            return json.dumps(contacts, indent=2)

        except requests.HTTPError as exc:
            logger.error("Apollo API HTTP error: %s", exc)
            return json.dumps({"error": str(exc)})
        except requests.RequestException as exc:
            logger.error("Apollo API request failed: %s", exc)
            return json.dumps({"error": str(exc)})

    @staticmethod
    def _demo_contacts(domain: str, title_filter: str) -> str:
        """Return realistic sample contacts when no Apollo API key is set."""
        logger.info(
            "APOLLO_API_KEY not set — returning demo contacts for %s.", domain
        )
        demo = [
            {
                "full_name": "Sarah Chen",
                "title": "VP of Sales",
                "email": f"sarah.chen@{domain}",
                "linkedin_url": f"https://linkedin.com/in/sarah-chen-{domain.split('.')[0]}",
                "company": domain.split(".")[0].title(),
                "seniority": "vp",
                "department": "sales",
            },
            {
                "full_name": "Marcus Rivera",
                "title": "CTO",
                "email": f"marcus.r@{domain}",
                "linkedin_url": f"https://linkedin.com/in/marcus-rivera-{domain.split('.')[0]}",
                "company": domain.split(".")[0].title(),
                "seniority": "c_suite",
                "department": "engineering",
            },
        ]

        if title_filter:
            demo = [
                c
                for c in demo
                if title_filter.lower() in c["title"].lower()
            ] or demo[:1]

        return json.dumps(demo, indent=2)


class WebScraperInput(BaseModel):
    url: str = Field(
        description="Full URL to scrape (e.g. 'https://elationhealth.com/about')."
    )


class WebScraperTool(BaseTool):
    name: str = "Company Website Scraper"
    description: str = (
        "Scrape a company website page using BeautifulSoup and return the "
        "visible text content. Useful for gathering context about a company's "
        "products, leadership, recent news, and initiatives."
    )
    args_schema: Type[BaseModel] = WebScraperInput

    def _run(self, url: str) -> str:
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return "ERROR: beautifulsoup4 is not installed."

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }

        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.warning("Failed to scrape %s: %s", url, exc)
            return f"ERROR: Could not reach {url} — {exc}"

        soup = BeautifulSoup(resp.text, "html.parser")

        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)

        max_chars = 8_000
        if len(text) > max_chars:
            text = text[:max_chars] + "\n\n[...truncated]"

        logger.info("Scraped %s (%d chars)", url, len(text))
        return text
