"""
Intent-to-Outbound AI Engine — Pipeline Orchestrator

Wires the four agents (Monitor → Researcher → Copywriter → Reviewer)
into an end-to-end pipeline with a self-correction loop and Slack delivery.

Usage:
    python -m autonomous_sdr.main                          # run full pipeline
    python -m autonomous_sdr.main --query "series A funding"  # custom signal query
    python -m autonomous_sdr.main --max-signals 5          # limit signals processed
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import requests
from crewai import Crew, Process
from dotenv import load_dotenv

from autonomous_sdr.agent_monitor import (
    create_monitor_agent,
    create_monitor_task,
)
from autonomous_sdr.agent_researcher import (
    create_researcher_agent,
    create_researcher_task,
)
from autonomous_sdr.agent_copywriter import (
    create_copywriter_agent,
    create_copywriter_task,
)
from autonomous_sdr.agent_reviewer import (
    create_reviewer_agent,
    create_reviewer_task,
)

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from shared.schemas import (
    SignalEvent,
    CompanyContext,
    PersonaContact,
    OutreachDraft,
    QAVerdict,
    PipelineResult,
)
from shared.crm_client import get_crm_client
from shared.llm import get_gemini_llm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

MAX_QA_REVISIONS = 3


def load_env() -> None:
    env_path = ROOT_DIR / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        logger.info("Loaded .env from %s", env_path)

    if not os.getenv("GEMINI_API_KEY"):
        logger.error(
            "GEMINI_API_KEY is not set. Export it or add it to .env."
        )
        sys.exit(1)


def parse_json_from_output(raw: str) -> dict | list:
    """Extract JSON from agent output that may contain markdown fences."""
    text = raw.strip()

    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]  # drop opening fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    return json.loads(text)


def _as_dict(data: dict | list) -> dict:
    if isinstance(data, list):
        return data[0] if data else {}
    return data


# ── Stage 1: Signal Discovery ────────────────────────────────────────

def run_signal_monitor(query: str, llm) -> list[dict]:
    logger.info("STAGE 1 — Signal Monitor scanning for: %r", query)

    agent = create_monitor_agent(llm=llm)
    task = create_monitor_task(agent, signal_query=query)

    crew = Crew(
        agents=[agent],
        tasks=[task],
        process=Process.sequential,
        verbose=True,
    )
    result = crew.kickoff()

    try:
        signals = parse_json_from_output(result.raw)
        if isinstance(signals, dict):
            signals = [signals]
        logger.info("Signal Monitor found %d valid signal(s).", len(signals))
        return signals
    except (json.JSONDecodeError, TypeError) as exc:
        logger.error("Failed to parse signal output: %s", exc)
        logger.debug("Raw output: %s", result.raw)
        return []


# ── Stage 2: Account Research ─────────────────────────────────────────

def run_researcher(signal: dict, llm) -> dict:
    signal_json = json.dumps(signal, indent=2)
    company = signal.get("company_name", "Unknown")
    logger.info("STAGE 2 — Researching %s", company)

    agent = create_researcher_agent(llm=llm)
    task = create_researcher_task(agent, signal_json=signal_json)

    crew = Crew(
        agents=[agent],
        tasks=[task],
        process=Process.sequential,
        verbose=True,
    )
    result = crew.kickoff()

    try:
        return _as_dict(parse_json_from_output(result.raw))
    except (json.JSONDecodeError, TypeError) as exc:
        logger.error("Failed to parse research output for %s: %s", company, exc)
        return {"persona": {}, "company": {}}


# ── Stage 3 + 4: Copywriting with QA Loop ────────────────────────────

def run_copy_with_qa(
    signal: dict, research: dict, llm
) -> tuple[dict, dict, int]:
    """
    Run the Copywriter → Reviewer loop up to MAX_QA_REVISIONS times.
    Returns (draft_dict, qa_dict, revision_count).
    """
    signal_json = json.dumps(signal, indent=2)
    research_json = json.dumps(research, indent=2)

    copy_agent = create_copywriter_agent(llm=llm)
    qa_agent = create_reviewer_agent(llm=llm)

    feedback: str | None = None
    draft_dict: dict = {}
    qa_dict: dict = {}

    for attempt in range(1, MAX_QA_REVISIONS + 1):
        logger.info(
            "STAGE 3 — Copywriter drafting (attempt %d/%d)",
            attempt,
            MAX_QA_REVISIONS,
        )

        copy_task = create_copywriter_task(
            copy_agent,
            research_json=research_json,
            signal_json=signal_json,
            revision_feedback=feedback,
        )
        copy_crew = Crew(
            agents=[copy_agent],
            tasks=[copy_task],
            process=Process.sequential,
            verbose=True,
        )
        copy_result = copy_crew.kickoff()

        try:
            draft_dict = _as_dict(parse_json_from_output(copy_result.raw))
        except (json.JSONDecodeError, TypeError):
            draft_dict = {"subject_line": "", "body": copy_result.raw, "call_to_action": "", "tone": "unknown"}

        draft_json = json.dumps(draft_dict, indent=2)

        logger.info("STAGE 4 — QA Reviewer evaluating draft")

        qa_task = create_reviewer_task(
            qa_agent,
            draft_json=draft_json,
            research_json=research_json,
            signal_json=signal_json,
        )
        qa_crew = Crew(
            agents=[qa_agent],
            tasks=[qa_task],
            process=Process.sequential,
            verbose=True,
        )
        qa_result = qa_crew.kickoff()

        try:
            qa_dict = _as_dict(parse_json_from_output(qa_result.raw))
        except (json.JSONDecodeError, TypeError):
            qa_dict = {"approved": True, "score": 0, "feedback": qa_result.raw, "issues": []}

        if qa_dict.get("approved", False):
            logger.info(
                "QA APPROVED (score: %s) on attempt %d.",
                qa_dict.get("score", "?"),
                attempt,
            )
            return draft_dict, qa_dict, attempt - 1

        feedback = qa_dict.get("feedback", "Revise for quality.")
        issues = qa_dict.get("issues", [])
        logger.warning(
            "QA REJECTED (score: %s). Issues: %s. Sending back for revision.",
            qa_dict.get("score", "?"),
            issues,
        )

    logger.warning(
        "Max revisions reached (%d). Forwarding best draft with QA notes.",
        MAX_QA_REVISIONS,
    )
    return draft_dict, qa_dict, MAX_QA_REVISIONS


# ── Slack Delivery ────────────────────────────────────────────────────

def deliver_to_slack(result: PipelineResult) -> bool:
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        logger.info("SLACK_WEBHOOK_URL not set — skipping Slack delivery.")
        return False

    qa_status = "Approved" if result.qa.approved else "Needs Review"
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"New Lead: {result.signal.company_name}",
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Signal:*\n{result.signal.headline}"},
                {"type": "mrkdwn", "text": f"*Type:*\n{result.signal.signal_type.value}"},
                {"type": "mrkdwn", "text": f"*Persona:*\n{result.persona.full_name} — {result.persona.title}"},
                {"type": "mrkdwn", "text": f"*Email:*\n{result.persona.email or 'N/A'}"},
                {"type": "mrkdwn", "text": f"*QA Status:*\n{qa_status} (score: {result.qa.score})"},
                {"type": "mrkdwn", "text": f"*Revisions:*\n{result.revision_count}"},
            ],
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Subject:* {result.draft.subject_line}\n\n"
                    f"```{result.draft.body}```"
                ),
            },
        },
    ]

    try:
        resp = requests.post(
            webhook_url,
            json={"blocks": blocks},
            timeout=10,
        )
        resp.raise_for_status()
        logger.info("Delivered to Slack successfully.")
        return True
    except requests.RequestException as exc:
        logger.error("Slack delivery failed: %s", exc)
        return False


# ── Pipeline Assembly ─────────────────────────────────────────────────

def build_pipeline_result(
    signal: dict,
    research: dict,
    draft: dict,
    qa: dict,
    revision_count: int,
    delivered: bool,
) -> PipelineResult:
    """Hydrate raw dicts into validated Pydantic models."""

    signal_event = SignalEvent(
        company_name=signal.get("company_name", "Unknown"),
        domain=signal.get("domain", "unknown.com"),
        signal_type=signal.get("signal_type", "funding_round"),
        headline=signal.get("headline", ""),
        details=signal.get("details", ""),
        source_url=signal.get("source_url"),
    )

    persona_data = research.get("persona", {})
    persona = PersonaContact(
        full_name=persona_data.get("full_name", "Unknown"),
        title=persona_data.get("title", "Unknown"),
        email=persona_data.get("email"),
        linkedin_url=persona_data.get("linkedin_url"),
        company=persona_data.get("company", signal_event.company_name),
        seniority=persona_data.get("seniority"),
        department=persona_data.get("department"),
    )

    company_data = research.get("company", {})
    company = CompanyContext(
        name=company_data.get("name", signal_event.company_name),
        domain=company_data.get("domain", signal_event.domain),
        industry=company_data.get("industry"),
        employee_count=company_data.get("employee_count"),
        funding_stage=company_data.get("funding_stage"),
        description=company_data.get("description"),
        recent_news=company_data.get("recent_news", []),
        tech_stack=company_data.get("tech_stack", []),
        website_summary=company_data.get("website_summary"),
    )

    outreach = OutreachDraft(
        subject_line=draft.get("subject_line", ""),
        body=draft.get("body", ""),
        call_to_action=draft.get("call_to_action", ""),
        tone=draft.get("tone", "professional"),
    )

    verdict = QAVerdict(
        approved=qa.get("approved", False),
        score=min(float(qa.get("score", 0)), 10.0),
        feedback=qa.get("feedback", ""),
        issues=qa.get("issues", []),
    )

    return PipelineResult(
        signal=signal_event,
        company=company,
        persona=persona,
        draft=outreach,
        qa=verdict,
        revision_count=revision_count,
        delivered=delivered,
    )


def run_pipeline(
    query: str = "recent funding rounds in healthcare tech",
    max_signals: int = 10,
) -> list[PipelineResult]:
    load_env()
    llm = get_gemini_llm()
    logger.info(
        "Using Gemini model: %s",
        os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
    )
    crm = get_crm_client()
    results: list[PipelineResult] = []

    signals = run_signal_monitor(query, llm)

    if not signals:
        logger.warning("No valid signals found. Pipeline complete.")
        return results

    signals = signals[:max_signals]
    logger.info("Processing %d signal(s).", len(signals))

    for i, signal in enumerate(signals, start=1):
        company = signal.get("company_name", "Unknown")
        logger.info(
            "━━━ [%d/%d] %s ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            i,
            len(signals),
            company,
        )

        try:
            research = run_researcher(signal, llm)
            draft, qa, revisions = run_copy_with_qa(signal, research, llm)

            delivered = False
            if qa.get("approved", False):
                pipeline_result = build_pipeline_result(
                    signal, research, draft, qa, revisions, delivered=False
                )
                delivered = deliver_to_slack(pipeline_result)
                pipeline_result.delivered = delivered
            else:
                pipeline_result = build_pipeline_result(
                    signal, research, draft, qa, revisions, delivered=False
                )

            crm.push_lead(pipeline_result)
            results.append(pipeline_result)

            status = "APPROVED + DELIVERED" if delivered else (
                "APPROVED" if qa.get("approved") else "NEEDS REVIEW"
            )
            logger.info(
                "Finished %s — %s (QA score: %s, revisions: %d)",
                company,
                status,
                qa.get("score", "?"),
                revisions,
            )

        except Exception as exc:
            logger.error("Pipeline failed for %s: %s", company, exc, exc_info=True)

    approved = sum(1 for r in results if r.qa.approved)
    logger.info(
        "\n══════ PIPELINE SUMMARY ══════\n"
        "  Signals processed: %d\n"
        "  Approved:          %d\n"
        "  Needs review:      %d\n"
        "  Results saved:     output/leads.jsonl\n"
        "══════════════════════════════",
        len(results),
        approved,
        len(results) - approved,
    )

    return results


# ── CLI ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Intent-to-Outbound AI Engine"
    )
    parser.add_argument(
        "--query",
        default="recent funding rounds in healthcare tech",
        help="Signal search query (default: healthcare funding)",
    )
    parser.add_argument(
        "--max-signals",
        type=int,
        default=10,
        help="Max signals to process (default: 10)",
    )
    args = parser.parse_args()

    run_pipeline(query=args.query, max_signals=args.max_signals)


if __name__ == "__main__":
    main()
