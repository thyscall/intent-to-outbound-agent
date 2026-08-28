"""
This file turns AI output into reliable business records for GTM workflows.
It standardizes signal, research, draft, and QA data into strict schemas so
reporting and approvals are based on consistent fields instead of free text.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import ValidationError

from shared.schemas import (
    CompanyContext,
    OutreachDraft,
    PersonaContact,
    QARubricScores,
    QAVerdict,
    QAStatus,
    ResearchDossier,
    SignalEvent,
    SignalType,
)

logger = logging.getLogger(__name__)

INCOMPLETE_RUBRIC_ISSUE = "incomplete_qa_rubric"


_FENCE_RE = re.compile(r"```(?:[a-zA-Z0-9_+-]*)\s*\n(.*?)```", re.DOTALL)


def parse_agent_json(raw: str) -> Any:
    """
    Extract JSON from agent output.

    Models differ in how much prose they wrap around the payload: some return a
    bare object, others narrate their reasoning and then present the result in a
    fenced block. This tries, in order, the whole string, each fenced block
    (last first — the final block is the answer, earlier ones tend to be
    working), then the first balanced JSON span found anywhere in the text.

    Raises json.JSONDecodeError if nothing parses, so callers can keep treating
    a parse failure as one error type.
    """
    text = raw.strip()

    # 1) The whole payload is already JSON.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2) A fenced code block somewhere in the message.
    for block in reversed(_FENCE_RE.findall(text)):
        try:
            return json.loads(block.strip())
        except json.JSONDecodeError:
            continue

    # 3) A bare object or array embedded in prose.
    span = _first_json_span(text)
    if span is not None:
        try:
            return json.loads(span)
        except json.JSONDecodeError:
            pass

    raise json.JSONDecodeError("No JSON object or array found in agent output", text, 0)


def _first_json_span(text: str) -> str | None:
    """Return the first balanced {...} or [...] substring, ignoring braces in strings."""
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if not starts:
        return None
    start = min(starts)

    pairs = {"{": "}", "[": "]"}
    stack: list[str] = []
    in_string = False
    escaped = False

    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in pairs:
            stack.append(pairs[ch])
        elif ch in ("}", "]"):
            if not stack or stack.pop() != ch:
                return None
            if not stack:
                return text[start : i + 1]
    return None


def as_first_dict(data: Any) -> dict[str, Any]:
    # Some model responses are single objects and others are 1-item lists.
    # This keeps both forms usable for the same lead processing flow.
    if isinstance(data, list):
        return data[0] if data else {}
    if isinstance(data, dict):
        return data
    return {}


def parse_signal_events(
    data: Any,
) -> tuple[list[SignalEvent], list[str]]:
    """
    Coerce list/dict of signal dicts into validated SignalEvent models.
    Returns (valid_events, error_messages for dropped rows).
    """
    # Business behavior:
    # - Keep valid signal rows moving through the pipeline.
    # - Capture row-level errors so operators can audit dropped records.
    if isinstance(data, dict):
        items: list[Any] = [data]
    elif isinstance(data, list):
        items = data
    else:
        return [], [f"Signal batch must be object or list, got {type(data)!r}"]

    valid: list[SignalEvent] = []
    errors: list[str] = []

    for i, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"index {i}: not an object")
            continue
        try:
            payload = _normalize_signal_dict(item)
            valid.append(SignalEvent.model_validate(payload))
        except (ValidationError, ValueError) as exc:
            errors.append(f"index {i}: {exc}")

    return valid, errors


def _normalize_signal_dict(item: dict[str, Any]) -> dict[str, Any]:
    # Normalize naming variants so the same business signal type is counted once.
    out = dict(item)
    st = out.get("signal_type", "funding_round")
    if isinstance(st, SignalType):
        out["signal_type"] = st
    elif isinstance(st, str):
        st_clean = st.strip().lower()
        # Map common variants
        for member in SignalType:
            if member.value == st_clean:
                out["signal_type"] = member
                break
        else:
            out["signal_type"] = SignalType.FUNDING_ROUND
    return out


def parse_research_dossier(
    data: dict[str, Any],
    company_fallback: str,
    domain_fallback: str,
) -> ResearchDossier:
    """
    Build ResearchDossier from researcher JSON, using signal fields when
    nested blocks are empty or invalid.
    """
    # We fall back to known signal values so sales still gets usable context
    # when partial enrichment data is missing or malformed.
    persona_raw = data.get("persona") or {}
    company_raw = data.get("company") or {}
    if not isinstance(persona_raw, dict):
        persona_raw = {}
    if not isinstance(company_raw, dict):
        company_raw = {}

    try:
        persona = PersonaContact(
            full_name=str(persona_raw.get("full_name") or "Unknown"),
            title=str(persona_raw.get("title") or "Unknown"),
            email=persona_raw.get("email"),
            linkedin_url=persona_raw.get("linkedin_url"),
            company=str(persona_raw.get("company") or company_fallback),
            seniority=persona_raw.get("seniority"),
            department=persona_raw.get("department"),
        )
    except ValidationError:
        persona = PersonaContact(
            full_name="Unknown",
            title="Unknown",
            company=company_fallback,
        )

    try:
        company = CompanyContext(
            name=str(company_raw.get("name") or company_fallback),
            domain=str(company_raw.get("domain") or domain_fallback),
            industry=company_raw.get("industry"),
            employee_count=company_raw.get("employee_count"),
            funding_stage=company_raw.get("funding_stage"),
            description=company_raw.get("description"),
            recent_news=list(company_raw.get("recent_news") or []),
            tech_stack=list(company_raw.get("tech_stack") or []),
            website_summary=company_raw.get("website_summary"),
        )
    except ValidationError:
        company = CompanyContext(
            name=company_fallback,
            domain=domain_fallback,
        )

    return ResearchDossier(persona=persona, company=company)


def parse_outreach_draft(data: dict[str, Any]) -> OutreachDraft:
    # Draft normalization ensures QA and reporting read the same field names.
    return OutreachDraft.model_validate(
        {
            "subject_line": str(data.get("subject_line", "")).strip(),
            "body": str(data.get("body", "")).strip(),
            "call_to_action": str(data.get("call_to_action", "")).strip(),
            "tone": str(data.get("tone", "professional-casual")).strip()
            or "professional-casual",
        }
    )


def _rubric_from_dict(d: dict[str, Any]) -> QARubricScores | None:
    # Accept both nested and flat score shapes so rubric data is still usable
    # across prompt or model formatting differences.
    keys = (
        "signal_reference",
        "personalization",
        "factual_accuracy",
        "brevity_clarity",
        "cta_quality",
    )
    nested = d.get("rubric")
    source: dict[str, Any] = {}
    if isinstance(nested, dict):
        source = nested
    else:
        for k in keys:
            if k in d:
                source[k] = d[k]
    if not all(k in source for k in keys):
        return None
    try:
        return QARubricScores(
            signal_reference=float(source["signal_reference"]),
            personalization=float(source["personalization"]),
            factual_accuracy=float(source["factual_accuracy"]),
            brevity_clarity=float(source["brevity_clarity"]),
            cta_quality=float(source["cta_quality"]),
        )
    except (TypeError, ValueError, ValidationError):
        return None


def parse_qa_verdict(
    data: dict[str, Any],
    raw_text_fallback: str = "",
) -> QAVerdict:
    """
    Parse LLM reviewer JSON into QAVerdict.
    If rubric dimensions are missing, returns NEEDS_HUMAN_REVIEW and issue
    `incomplete_qa_rubric` — never approves on incomplete data.
    """
    # Business policy:
    # 1) Missing rubric data cannot be auto-approved.
    # 2) Pass threshold and zero-score rules are enforced consistently.
    # 3) Output is normalized for downstream approval and analytics logic.
    rubric = _rubric_from_dict(data)
    if rubric is None:
        return QAVerdict(
            rubric=QARubricScores(
                signal_reference=0.0,
                personalization=0.0,
                factual_accuracy=0.0,
                brevity_clarity=0.0,
                cta_quality=0.0,
            ),
            approved=False,
            feedback=str(data.get("feedback", raw_text_fallback) or ""),
            issues=list(data.get("issues", [])) + [INCOMPLETE_RUBRIC_ISSUE],
            qa_status=QAStatus.NEEDS_HUMAN_REVIEW,
        )

    issues = [str(x) for x in (data.get("issues") or []) if x is not None]
    feedback = str(data.get("feedback", ""))
    raw_approved = bool(data.get("approved", False))

    rubric_sum = round(rubric.rubric_sum(), 2)
    # Pass threshold 35/50; any dimension 0 is auto-fail (from reviewer prompt)
    any_zero = any(
        getattr(rubric, name) == 0.0
        for name in (
            "signal_reference",
            "personalization",
            "factual_accuracy",
            "brevity_clarity",
            "cta_quality",
        )
    )
    if any_zero and raw_approved:
        raw_approved = False
        if "dimension_zero_fails" not in issues:
            issues.append("dimension_zero_fails")
    if rubric_sum < 35.0 and raw_approved:
        raw_approved = False
        if "below_pass_threshold" not in issues:
            issues.append("below_pass_threshold")

    if raw_approved:
        qa_st = QAStatus.QA_PASSED
    else:
        qa_st = QAStatus.QA_FAILED

    return QAVerdict(
        rubric=rubric,
        approved=raw_approved,
        feedback=feedback,
        issues=issues,
        qa_status=qa_st,
    )
