"""
This is the business workflow for turning intent data into outbound-ready leads.
It takes signal data (Clay), enriches people and company context (Apollo + scraping),
creates a draft, quality-checks it, and then sends approved output to Slack while
saving a full record for RevOps and GTM reporting.
"""

from __future__ import annotations

import autonomous_sdr._path  # noqa: F401  # project root for `shared` imports
import argparse
import json
import logging
import os
import uuid
from uuid import UUID

import requests
from crewai import Crew, Process
from dotenv import load_dotenv

from autonomous_sdr._path import _ROOT
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
from shared.crm_client import get_crm_client
from shared.http import get_retrying_session, session_timeout
from shared.idempotency import record_successful_send, slack_delivery_key, was_already_sent
from shared.llm import get_gemini_llm
from shared.logging_config import StageTimer, log_event, setup_logging
from shared.parsing import (
    INCOMPLETE_RUBRIC_ISSUE,
    as_first_dict,
    parse_agent_json,
    parse_outreach_draft,
    parse_qa_verdict,
    parse_research_dossier,
    parse_signal_events,
)
from shared.schemas import (
    CompanyContext,
    DraftValidationResult,
    LeadTerminalStatus,
    OutreachDraft,
    PersonaContact,
    PipelineResult,
    QAStatus,
    QAVerdict,
    ResearchDossier,
    SignalEvent,
    SignalType,
)
from shared.validators import validate_outreach_draft
from shared.versioning import PIPELINE_SCHEMA_VERSION, VALIDATION_RULE_VERSION

logger = logging.getLogger(__name__)
MAX_QA_REVISIONS = 3
ROOT_DIR = _ROOT


def _result_text(result: object) -> str:
    """Normalize Crew kickoff outputs into a safe text payload."""
    raw = getattr(result, "raw", result)
    if raw is None:
        return ""
    return raw if isinstance(raw, str) else str(raw)


def load_env() -> None:
    env_path = ROOT_DIR / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        log_event(logger, "env_loaded", message=f"Loaded .env from {env_path}")

    # No hard exit here: we support a no-key demo path for fast local validation.
    if not os.getenv("GEMINI_API_KEY"):
        log_event(
            logger,
            "gemini_key_missing",
            stage="orchestrator",
            message="GEMINI_API_KEY not set. Falling back to local demo mode.",
        )


def _demo_signal_events(max_signals: int) -> list[SignalEvent]:
    """Return deterministic sample signals for no-key local demos."""
    seed = [
        SignalEvent(
            company_name="Vela Health",
            domain="velahealth.com",
            signal_type=SignalType.FUNDING_ROUND,
            headline="Vela Health closes $18M Series A",
            details=(
                "Funding to expand engineering and enterprise go-to-market "
                "for care coordination infrastructure."
            ),
            source_url="https://example.com/vela-series-a",
        ),
        SignalEvent(
            company_name="Northline Labs",
            domain="northline.io",
            signal_type=SignalType.EXPANSION,
            headline="Northline expands into regulated healthcare workflows",
            details=(
                "Expansion announcement indicates new compliance-heavy buyer "
                "segments and potential tooling spend."
            ),
            source_url="https://example.com/northline-expansion",
        ),
    ]
    return seed[:max_signals]


def _demo_research(signal: SignalEvent) -> ResearchDossier:
    """Generate deterministic persona/company research for no-key demos."""
    return ResearchDossier(
        persona=PersonaContact(
            full_name="Jordan Lee",
            title="VP of Operations",
            email=f"jordan@{signal.domain}",
            linkedin_url="https://linkedin.com/in/jordan-lee-ops",
            company=signal.company_name,
            seniority="vp",
            department="operations",
        ),
        company=CompanyContext(
            name=signal.company_name,
            domain=signal.domain,
            industry="Healthcare SaaS",
            employee_count=180,
            funding_stage="Series A",
            description=(
                "Builds software that coordinates patient workflows "
                "for distributed care teams."
            ),
            recent_news=[signal.headline],
            tech_stack=["Python", "Postgres", "AWS"],
            website_summary=(
                "Focused on improving speed and compliance for care operations."
            ),
        ),
    )


def _demo_draft(signal: SignalEvent, research: ResearchDossier) -> OutreachDraft:
    """Generate deterministic outreach draft aligned to validation constraints."""
    signal_hint = {
        "funding_round": "your recent funding round and Series momentum",
        "leadership_change": "the recent leadership hire",
        "expansion": "the expansion into a new market",
        "product_launch": "the new product launch",
        "partnership": "the recent partnership move",
        "job_posting": "the hiring push in key roles",
    }.get(signal.signal_type.value, "the recent company momentum")
    return OutreachDraft(
        subject_line=f"{signal.company_name} expansion idea",
        body=(
            f"Saw {signal.company_name}'s update around {signal_hint}. "
            f"Given {research.persona.title} ownership of execution and scale, "
            "teams in this phase usually face pressure to speed onboarding "
            "while keeping workflows consistent across departments. "
            "We help operators shorten time-to-value for new initiatives "
            "without adding process overhead."
        ),
        call_to_action="Open to a quick 15-minute compare call this week?",
        tone="professional-casual",
    )


def _demo_qa(signal: SignalEvent, draft: OutreachDraft) -> QAVerdict:
    """Return a deterministic QA verdict that mirrors rubric semantics."""
    rubric = {
        "signal_reference": 8.0,
        "personalization": 8.0,
        "factual_accuracy": 8.0,
        "brevity_clarity": 7.0,
        "cta_quality": 8.0,
    }
    return parse_qa_verdict(
        {
            "rubric": rubric,
            "approved": True,
            "score": sum(rubric.values()),
            "feedback": (
                f"Draft references {signal.company_name} context and provides a "
                "clear, low-friction CTA."
            ),
            "issues": [],
        }
    )


def run_pipeline_demo(
    *,
    run_id: UUID,
    max_signals: int,
    crm,
    http: requests.Session,
) -> list[PipelineResult]:
    """No-key path for live demos and code reviews."""
    results: list[PipelineResult] = []
    signals = _demo_signal_events(max_signals)
    log_event(
        logger,
        "demo_mode_started",
        run_id=run_id,
        stage="orchestrator",
        extra={"signals": len(signals)},
    )
    for i, signal in enumerate(signals, start=1):
        lead_id = uuid.uuid4()
        log_event(
            logger,
            "lead_start",
            run_id=run_id,
            lead_id=lead_id,
            stage="orchestrator",
            extra={"index": i, "total": len(signals), "company": signal.company_name},
        )
        research = _demo_research(signal)
        draft = _demo_draft(signal, research)
        validation = validate_outreach_draft(draft=draft, signal=signal, research=research)
        qa = _demo_qa(signal, draft)
        can_deliver = bool(qa.approved and validation.passed)
        pipeline_result = build_pipeline_result(
            run_id=run_id,
            lead_id=lead_id,
            signal=signal,
            research=research,
            draft=draft,
            qa=qa,
            revision_count=0,
            delivered=False,
            last_validation=validation,
            terminal_status=LeadTerminalStatus.NEEDS_HUMAN_REVIEW,
        )
        delivered = False
        if can_deliver:
            delivered = deliver_to_slack(
                pipeline_result,
                run_id=run_id,
                lead_id=lead_id,
                http=http,
            )
        term = _compute_terminal_status(
            delivered=delivered,
            qa=qa,
            validation=validation,
            exhausted=False,
        )
        pipeline_result = pipeline_result.model_copy(
            update={"delivered": delivered, "terminal_status": term}
        )
        crm.push_lead(pipeline_result)
        results.append(pipeline_result)
    log_event(
        logger,
        "demo_mode_completed",
        run_id=run_id,
        stage="orchestrator",
        extra={"processed": len(results)},
    )
    return results


def _signal_to_json(signal: SignalEvent) -> str:
    return json.dumps(
        json.loads(
            signal.model_dump_json()
        ),
        indent=2,
    )


def _research_to_json(research: ResearchDossier) -> str:
    return json.dumps(
        {
            "persona": json.loads(research.persona.model_dump_json()),
            "company": json.loads(research.company.model_dump_json()),
        },
        indent=2,
    )


# ── Stage 1: Signal Discovery ────────────────────────────────────────


def run_signal_monitor(
    query: str, llm, run_id: UUID
) -> list[SignalEvent]:
    # Business intent: start with broad market activity and keep only signal rows
    # that are clean enough to trust in downstream sales workflows.
    t = StageTimer()
    log_event(
        logger,
        "stage_signal_monitor_start",
        run_id=run_id,
        stage="signal_monitor",
        message=f"scanning: {query!r}",
    )

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
        result_text = _result_text(result)
        raw = parse_agent_json(result_text)
        if isinstance(raw, dict):
            raw = [raw]
        events, errors = parse_signal_events(raw)
        for err in errors:
            log_event(
                logger,
                "signal_row_dropped",
                run_id=run_id,
                stage="signal_monitor",
                extra={"error": err},
            )
        log_event(
            logger,
            "signal_batch_parsed",
            run_id=run_id,
            stage="signal_monitor",
            duration_ms=t.ms(),
            extra={"valid": len(events), "dropped": len(errors)},
        )
        return events
    except (json.JSONDecodeError, TypeError) as exc:
        log_event(
            logger,
            "signal_parse_failed",
            run_id=run_id,
            stage="signal_monitor",
            message=str(exc),
        )
        logger.debug("Raw output: %s", result_text)
        return []


# ── Stage 2: Account Research ─────────────────────────────────────────


def run_researcher(
    signal: SignalEvent, llm, run_id: UUID, lead_id: UUID
) -> ResearchDossier:
    # Business intent: convert "something happened at this account" into
    # "who should we contact and why now" using persona + company context data.
    t = StageTimer()
    signal_json = _signal_to_json(signal)
    log_event(
        logger,
        "stage_research_start",
        run_id=run_id,
        lead_id=lead_id,
        stage="researcher",
        message=signal.company_name,
    )

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
        raw = as_first_dict(parse_agent_json(_result_text(result)))
        return parse_research_dossier(
            raw,
            company_fallback=signal.company_name,
            domain_fallback=signal.domain,
        )
    except (json.JSONDecodeError, TypeError) as exc:
        log_event(
            logger,
            "research_parse_failed",
            run_id=run_id,
            lead_id=lead_id,
            stage="researcher",
            message=str(exc),
        )
        return parse_research_dossier(
            {"persona": {}, "company": {}},
            company_fallback=signal.company_name,
            domain_fallback=signal.domain,
        )
    finally:
        log_event(
            logger,
            "research_completed",
            run_id=run_id,
            lead_id=lead_id,
            stage="researcher",
            duration_ms=t.ms(),
        )


# ── Stage 3 + 4: Copywriting with QA Loop ────────────────────────────


def run_copy_with_qa(
    signal: SignalEvent,
    research: ResearchDossier,
    llm,
    run_id: UUID,
    lead_id: UUID,
) -> tuple[OutreachDraft, QAVerdict, int, DraftValidationResult]:
    """
    Run Copywriter → Reviewer up to MAX_QA_REVISIONS times.
    Returns (draft, qa, revision_count, last_deterministic_validation).
    Early exit when QA approves and deterministic validation passes.
    """
    # Business loop:
    # 1) Draft outreach from signal + research context.
    # 2) Score quality and enforce hard policy checks.
    # 3) If quality is not acceptable, feed feedback back into revision.
    signal_json = _signal_to_json(signal)
    research_json = _research_to_json(research)

    copy_agent = create_copywriter_agent(llm=llm)
    qa_agent = create_reviewer_agent(llm=llm)

    feedback: str | None = None
    draft: OutreachDraft = OutreachDraft(
        subject_line="",
        body="",
        call_to_action="",
        tone="unknown",
    )
    qa: QAVerdict
    last_validation = DraftValidationResult(
        passed=False,
        rule_version=VALIDATION_RULE_VERSION,
        failed_rules=[],
    )

    for attempt in range(1, MAX_QA_REVISIONS + 1):
        t_copy = StageTimer()
        log_event(
            logger,
            "qa_attempt",
            run_id=run_id,
            lead_id=lead_id,
            stage="copywriter",
            extra={"attempt": attempt, "max": MAX_QA_REVISIONS},
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
            copy_text = _result_text(copy_result)
            raw_d = as_first_dict(parse_agent_json(copy_text))
            draft = parse_outreach_draft(raw_d)
        except (json.JSONDecodeError, TypeError, ValueError):
            # Keep raw output for operators so we can diagnose bad model responses.
            draft = OutreachDraft(
                subject_line="",
                body=copy_text[:4000],
                call_to_action="",
                tone="unknown",
            )

        validation = validate_outreach_draft(
            draft=draft,
            signal=signal,
            research=research,
        )
        last_validation = validation

        if validation.passed:
            log_event(
                logger,
                "validation_result",
                run_id=run_id,
                lead_id=lead_id,
                stage="deterministic",
                extra={
                    "passed": True,
                    "subject_words": validation.subject_word_count,
                    "body_words": validation.body_word_count,
                    "rule_version": validation.rule_version,
                },
            )
        else:
            log_event(
                logger,
                "validation_result",
                run_id=run_id,
                lead_id=lead_id,
                stage="deterministic",
                extra={
                    "passed": False,
                    "failed_rules": validation.failed_rules,
                    "rule_version": validation.rule_version,
                },
            )

        draft_json = json.dumps(
            {
                "subject_line": draft.subject_line,
                "body": draft.body,
                "call_to_action": draft.call_to_action,
                "tone": draft.tone,
            },
            indent=2,
        )

        t_qa = StageTimer()
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
            qa_text = _result_text(qa_result)
            raw_qa = as_first_dict(parse_agent_json(qa_text))
            qa = parse_qa_verdict(raw_qa, raw_text_fallback=qa_text)
        except (json.JSONDecodeError, TypeError):
            qa = parse_qa_verdict(
                {
                    "approved": False,
                    "issues": ["QA output was not valid JSON."],
                    "feedback": _result_text(qa_result)[:2000],
                },
                raw_text_fallback=_result_text(qa_result),
            )

        if validation.failed_rules:
            # Hard business rules always win (length, required context, banned phrasing).
            merged = list(qa.issues) + list(validation.failed_rules)
            det_fb = (
                "Deterministic validation failed. Fix these before approval: "
                + "; ".join(validation.failed_rules)
            )
            prior = (qa.feedback or "").strip()
            det_status = (
                QAStatus.NEEDS_HUMAN_REVIEW
                if INCOMPLETE_RUBRIC_ISSUE in qa.issues
                else QAStatus.QA_FAILED
            )
            qa = qa.model_copy(
                update={
                    "approved": False,
                    "feedback": f"{prior}\n\n{det_fb}" if prior else det_fb,
                    "issues": merged,
                    "qa_status": det_status,
                }
            )

        if qa.approved and validation.passed:
            log_event(
                logger,
                "qa_round_complete",
                run_id=run_id,
                lead_id=lead_id,
                stage="qa",
                duration_ms=t_qa.ms(),
                extra={"approved": True, "copy_ms": t_copy.ms()},
            )
            return draft, qa, attempt - 1, last_validation

        feedback = qa.feedback or "Revise for quality."
        log_event(
            logger,
            "qa_rejected",
            run_id=run_id,
            lead_id=lead_id,
            stage="qa",
            extra={"score": qa.score, "issues": qa.issues},
        )

    log_event(
        logger,
        "qa_max_revisions",
        run_id=run_id,
        lead_id=lead_id,
        stage="qa",
    )
    return draft, qa, MAX_QA_REVISIONS, last_validation


# ── Slack Delivery ────────────────────────────────────────────────────


def deliver_to_slack(
    result: PipelineResult,
    *,
    run_id: UUID,
    lead_id: UUID,
    http: requests.Session,
) -> bool:
    # Business intent: notify sellers once per lead, not once per retry.
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        log_event(
            logger,
            "slack_skipped",
            run_id=run_id,
            lead_id=lead_id,
            stage="slack",
            message="SLACK_WEBHOOK_URL not set",
        )
        return False

    key = slack_delivery_key(run_id, lead_id)
    payload = {
        "text": f"New lead: {result.signal.company_name}",
        "run_id": str(run_id),
        "lead_id": str(lead_id),
    }
    if was_already_sent(key):
        log_event(
            logger,
            "slack_skipped_duplicate",
            run_id=run_id,
            lead_id=lead_id,
            stage="slack",
        )
        return True

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
                {
                    "type": "mrkdwn",
                    "text": f"*Signal:*\n{result.signal.headline}",
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Type:*\n{result.signal.signal_type.value}",
                },
                {
                    "type": "mrkdwn",
                    "text": (
                        f"*Persona:*\n{result.persona.full_name} — "
                        f"{result.persona.title}"
                    ),
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Email:*\n{result.persona.email or 'N/A'}",
                },
                {
                    "type": "mrkdwn",
                    "text": (
                        f"*QA Status:*\n{qa_status} (score: {result.qa.score}/50)"
                    ),
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Revisions:*\n{result.revision_count}",
                },
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

    to = session_timeout(http)
    try:
        resp = http.post(
            webhook_url,
            json={"blocks": blocks},
            timeout=to,
        )
        resp.raise_for_status()
        record_successful_send(key, payload)
        log_event(
            logger,
            "slack_delivered",
            run_id=run_id,
            lead_id=lead_id,
            stage="slack",
        )
        return True
    except requests.RequestException as exc:
        log_event(
            logger,
            "slack_failed",
            run_id=run_id,
            lead_id=lead_id,
            stage="slack",
            message=str(exc),
        )
        return False


# ── Pipeline Assembly ─────────────────────────────────────────────────


def _compute_terminal_status(
    *,
    delivered: bool,
    qa: QAVerdict,
    validation: DraftValidationResult,
    exhausted: bool,
) -> LeadTerminalStatus:
    # These statuses are what GTM/RevOps teams use to report pipeline health.
    if qa.approved and validation.passed:
        if delivered:
            return LeadTerminalStatus.DELIVERED
        return LeadTerminalStatus.APPROVED_NOT_DELIVERED
    if exhausted and not (qa.approved and validation.passed):
        return LeadTerminalStatus.QA_FAILED
    if qa.qa_status == QAStatus.NEEDS_HUMAN_REVIEW or not validation.passed:
        return LeadTerminalStatus.NEEDS_HUMAN_REVIEW
    return LeadTerminalStatus.NEEDS_HUMAN_REVIEW


def build_pipeline_result(
    *,
    run_id: UUID,
    lead_id: UUID,
    signal: SignalEvent,
    research: ResearchDossier,
    draft: OutreachDraft,
    qa: QAVerdict,
    revision_count: int,
    delivered: bool,
    last_validation: DraftValidationResult,
    terminal_status: LeadTerminalStatus,
) -> PipelineResult:
    return PipelineResult(
        run_id=run_id,
        lead_id=lead_id,
        schema_version=PIPELINE_SCHEMA_VERSION,
        signal=signal,
        company=research.company,
        persona=research.persona,
        draft=draft,
        qa=qa,
        revision_count=revision_count,
        delivered=delivered,
        terminal_status=terminal_status,
        deterministic_validation=last_validation,
    )


def run_pipeline(
    query: str = "recent funding rounds in healthcare tech",
    max_signals: int = 10,
) -> list[PipelineResult]:
    # End-to-end value: process a batch of account signals into review-ready
    # outbound packages and store traceable outcomes for every lead.
    setup_logging()
    load_env()
    run_id = uuid.uuid4()
    log_event(
        logger,
        "pipeline_started",
        run_id=run_id,
        stage="orchestrator",
        extra={"query": query, "max_signals": max_signals},
    )
    http = get_retrying_session(service_name="outbound")
    crm = get_crm_client()
    results: list[PipelineResult] = []

    if not os.getenv("GEMINI_API_KEY"):
        return run_pipeline_demo(
            run_id=run_id,
            max_signals=max_signals,
            crm=crm,
            http=http,
        )

    llm = get_gemini_llm()
    log_event(
        logger,
        "llm_config",
        run_id=run_id,
        stage="orchestrator",
        extra={"model": os.getenv("GEMINI_MODEL", "gemini-2.0-flash")},
    )

    signals = run_signal_monitor(query, llm, run_id)

    if not signals:
        log_event(
            logger,
            "no_signals",
            run_id=run_id,
            stage="orchestrator",
        )
        return results

    signals = signals[:max_signals]
    log_event(
        logger,
        "processing_batch",
        run_id=run_id,
        stage="orchestrator",
        extra={"count": len(signals)},
    )

    for i, signal in enumerate(signals, start=1):
        lead_id = uuid.uuid4()
        t_lead = StageTimer()
        log_event(
            logger,
            "lead_start",
            run_id=run_id,
            lead_id=lead_id,
            stage="orchestrator",
            extra={"index": i, "total": len(signals), "company": signal.company_name},
        )

        try:
            research = run_researcher(signal, llm, run_id, lead_id)
            draft, qa, revisions, last_val = run_copy_with_qa(
                signal, research, llm, run_id, lead_id
            )

            exhausted = revisions >= MAX_QA_REVISIONS
            can_deliver = bool(qa.approved and last_val.passed)
            delivered = False
            if can_deliver:
                # Build the record before delivery so data is consistent everywhere.
                pipeline_result = build_pipeline_result(
                    run_id=run_id,
                    lead_id=lead_id,
                    signal=signal,
                    research=research,
                    draft=draft,
                    qa=qa,
                    revision_count=revisions,
                    delivered=False,
                    last_validation=last_val,
                    terminal_status=LeadTerminalStatus.NEEDS_HUMAN_REVIEW,
                )
                delivered = deliver_to_slack(
                    pipeline_result,
                    run_id=run_id,
                    lead_id=lead_id,
                    http=http,
                )
            else:
                pipeline_result = build_pipeline_result(
                    run_id=run_id,
                    lead_id=lead_id,
                    signal=signal,
                    research=research,
                    draft=draft,
                    qa=qa,
                    revision_count=revisions,
                    delivered=False,
                    last_validation=last_val,
                    terminal_status=LeadTerminalStatus.NEEDS_HUMAN_REVIEW,
                )

            term = _compute_terminal_status(
                delivered=delivered,
                qa=qa,
                validation=last_val,
                exhausted=exhausted,
            )
            pipeline_result = pipeline_result.model_copy(
                update={"delivered": delivered, "terminal_status": term}
            )

            # Local JSONL is a temporary source of truth for analysis and replay prep.
            crm.push_lead(pipeline_result)
            log_event(
                logger,
                "lead_persisted",
                run_id=run_id,
                lead_id=lead_id,
                stage="crm",
                duration_ms=t_lead.ms(),
                extra={"terminal_status": term.value},
            )
            results.append(pipeline_result)
        except Exception as exc:
            logger.exception("Pipeline failed for %s", signal.company_name)
            log_event(
                logger,
                "lead_failed",
                run_id=run_id,
                lead_id=lead_id,
                stage="orchestrator",
                message=str(exc),
            )

    approved = sum(1 for r in results if r.qa.approved)
    log_event(
        logger,
        "pipeline_summary",
        run_id=run_id,
        stage="orchestrator",
        extra={
            "processed": len(results),
            "qa_approved": approved,
            "needs_review": len(results) - approved,
        },
    )

    return results


# ── CLI ───────────────────────────────────────────────────────────────


def main() -> None:
    setup_logging()
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
