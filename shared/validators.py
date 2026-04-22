"""
This file enforces non-negotiable outreach quality rules before anything is approved.
It checks draft constraints like brevity, personalization, and banned language using
deterministic logic so quality standards do not depend only on model judgment.
"""

from __future__ import annotations

import re
from typing import Any, Union

from shared.schemas import (
    CompanyContext,
    DraftValidationResult,
    OutreachDraft,
    ResearchDossier,
    SignalEvent,
    SignalType,
)
from shared.versioning import VALIDATION_RULE_VERSION

BANNED_PHRASES = (
    "synergy",
    "leverage",
    "circle back",
    "touch base",
)

SIGNAL_KEYWORDS_BY_TYPE = {
    "funding_round": ("funding", "series", "raised", "round"),
    "leadership_change": ("leadership", "hired", "appointed", "joined"),
    "expansion": ("expansion", "expand", "new market", "growth"),
    "product_launch": ("launch", "product", "release", "rollout"),
    "partnership": ("partnership", "partner", "alliance", "collaboration"),
    "job_posting": ("hiring", "job", "opening", "recruiting"),
}


def _word_count(text: str) -> int:
    # Keep counting simple and stable so score thresholds are predictable.
    return len(re.findall(r"\b\w+\b", text))


def _contains_any(text: str, candidates: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(candidate in lowered for candidate in candidates)


def _draft_fields(
    draft: Union[OutreachDraft, dict[str, Any]]
) -> tuple[str, str, str]:
    # Accept typed models and raw dicts so rules can run at multiple pipeline steps.
    if isinstance(draft, OutreachDraft):
        return (draft.subject_line, draft.body, draft.call_to_action)
    return (
        str(draft.get("subject_line", "")).strip(),
        str(draft.get("body", "")).strip(),
        str(draft.get("call_to_action", "")).strip(),
    )


def _company_name(
    signal: Union[SignalEvent, dict[str, Any]],
    research: Union[ResearchDossier, dict[str, Any]],
) -> str:
    # Prefer the signal's account name, then fallback to enrichment output.
    if isinstance(signal, SignalEvent):
        name = signal.company_name.strip()
        if name:
            return name
    else:
        name = str(signal.get("company_name") or "").strip()
        if name:
            return name
    if isinstance(research, ResearchDossier):
        return (research.company.name or "").strip()
    return str(research.get("company", {}).get("name", "") or "").strip()


def _signal_type_key(
    signal: Union[SignalEvent, dict[str, Any]]
) -> str:
    if isinstance(signal, SignalEvent):
        return signal.signal_type.value
    st = signal.get("signal_type", "funding_round")
    if isinstance(st, SignalType):
        return st.value
    return str(st).strip().lower()


def validate_outreach_draft(
    draft: Union[OutreachDraft, dict[str, Any]],
    signal: Union[SignalEvent, dict[str, Any]],
    research: Union[ResearchDossier, dict[str, Any]],
) -> DraftValidationResult:
    # Business purpose:
    # - Apply objective pass/fail policy that protects brand quality.
    # - Return a versioned result so teams can audit which rule set was used.
    failed_rules: list[str] = []
    warnings: list[str] = []

    subject, body, cta = _draft_fields(draft)
    combined_text = f"{subject}\n{body}"

    subject_words = _word_count(subject)
    body_words = _word_count(body)

    # Rule group: minimum required fields for a usable outbound message.
    if not subject:
        failed_rules.append("Subject line is required.")
    if not body:
        failed_rules.append("Email body is required.")
    if not cta:
        failed_rules.append("Call-to-action is required.")

    # Rule group: hard brevity limits aligned to outreach playbook.
    if subject_words > 8:
        failed_rules.append(
            f"Subject line exceeds 8 words ({subject_words})."
        )
    if body_words > 150:
        failed_rules.append(f"Email body exceeds 150 words ({body_words}).")

    # Rule group: disallow low-quality phrasing that hurts response rates.
    lowered_text = combined_text.lower()
    for phrase in BANNED_PHRASES:
        if phrase in lowered_text:
            failed_rules.append(f'Banned phrase detected: "{phrase}".')

    # Rule group: require account-specific personalization.
    company_name = _company_name(signal, research)

    if company_name:
        if company_name.lower() not in lowered_text:
            failed_rules.append(
                f'Company name "{company_name}" is not referenced.'
            )
    else:
        warnings.append("Could not determine company name for validation.")

    # Rule group: ensure the message actually reflects the triggering signal.
    signal_type = _signal_type_key(signal)
    signal_keywords = SIGNAL_KEYWORDS_BY_TYPE.get(signal_type, ())
    if signal_keywords and not _contains_any(lowered_text, signal_keywords):
        failed_rules.append(
            "Draft does not reference expected signal context keywords."
        )

    return DraftValidationResult(
        passed=not failed_rules,
        rule_version=VALIDATION_RULE_VERSION,
        failed_rules=failed_rules,
        warnings=warnings,
        body_word_count=body_words,
        subject_word_count=subject_words,
    )
