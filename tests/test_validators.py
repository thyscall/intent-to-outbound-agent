"""Exercise deterministic draft validation rules and typed input support.

The tests verify required fields, hard constraints, banned phrases, and schema
version tagging across model and dict inputs. This is important because
deterministic checks are the non-LLM safety gate before approval.
"""

import pytest

from shared.schemas import (
    CompanyContext,
    DraftValidationResult,
    OutreachDraft,
    PersonaContact,
    ResearchDossier,
    SignalEvent,
    SignalType,
)
from shared.validators import validate_outreach_draft
from shared.versioning import VALIDATION_RULE_VERSION


def _minimal_signal() -> SignalEvent:
    return SignalEvent(
        company_name="Acme",
        domain="acme.com",
        signal_type=SignalType.FUNDING_ROUND,
        headline="funding",
        details="d",
    )


def _minimal_research() -> ResearchDossier:
    return ResearchDossier(
        persona=PersonaContact(
            full_name="Pat",
            title="VP",
            company="Acme",
        ),
        company=CompanyContext(name="Acme", domain="acme.com"),
    )


def test_rule_version_present() -> None:
    s = _minimal_signal()
    r = _minimal_research()
    d = OutreachDraft(
        subject_line="Acme raised series A",
        body="funding " * 10,
        call_to_action="Reply yes",
    )
    out = validate_outreach_draft(d, s, r)
    assert isinstance(out, DraftValidationResult)
    assert out.rule_version == VALIDATION_RULE_VERSION
    assert out.passed is True
    assert out.subject_word_count <= 8


def test_banned_phrase() -> None:
    s = _minimal_signal()
    r = _minimal_research()
    d = OutreachDraft(
        subject_line="Acme raised funding",
        body="funding is great synergy and acme is cool " * 4,
        call_to_action="acme",
    )
    out = validate_outreach_draft(d, s, r)
    assert out.passed is False
    assert any("synergy" in x.lower() for x in out.failed_rules)


def test_dict_inputs_equivalent() -> None:
    out = validate_outreach_draft(
        {
            "subject_line": "Acme funding",
            "body": "funding and series for acme " * 5,
            "call_to_action": "acme",
        },
        {
            "company_name": "Acme",
            "domain": "acme.com",
            "signal_type": "funding_round",
            "headline": "h",
            "details": "d",
        },
        {
            "persona": {"full_name": "P", "title": "T", "company": "Acme"},
            "company": {"name": "Acme", "domain": "acme.com"},
        },
    )
    assert out.rule_version == VALIDATION_RULE_VERSION
