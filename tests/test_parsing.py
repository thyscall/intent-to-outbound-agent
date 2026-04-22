"""Test parsing utilities that coerce agent output into strict models.

These tests cover fenced JSON extraction, stage parsing fallbacks, and QA
verdict behavior when rubric fields are missing. They matter because malformed
LLM output is common and must not produce ambiguous pipeline states.
"""

import pytest

from shared.parsing import (
    INCOMPLETE_RUBRIC_ISSUE,
    as_first_dict,
    parse_agent_json,
    parse_qa_verdict,
    parse_signal_events,
    parse_research_dossier,
)
from shared.schemas import SignalType, QAStatus


def test_parse_agent_json_fenced() -> None:
    raw = '```json\n{"a": 1}\n```'
    assert parse_agent_json(raw) == {"a": 1}


def test_as_first_list() -> None:
    assert as_first_dict([{"x": 1}]) == {"x": 1}
    assert as_first_dict({}) == {}


def test_parse_signal_valid() -> None:
    data = [
        {
            "company_name": "C",
            "domain": "c.com",
            "signal_type": "funding_round",
            "headline": "h",
            "details": "d",
        }
    ]
    ev, err = parse_signal_events(data)
    assert len(err) == 0
    assert len(ev) == 1
    assert ev[0].signal_type is SignalType.FUNDING_ROUND


def test_parse_signal_drops_invalid() -> None:
    data = [
        {
            "company_name": "C",
            "domain": "c.com",
            "signal_type": "funding_round",
            "headline": "h",
            "details": "d",
        },
        "bad",
    ]
    ev, err = parse_signal_events(data)
    assert len(ev) == 1
    assert len(err) == 1


def test_incomplete_qa() -> None:
    q = parse_qa_verdict(
        {"approved": True, "score": 50, "feedback": "x"},
    )
    assert q.approved is False
    assert INCOMPLETE_RUBRIC_ISSUE in q.issues
    assert q.qa_status is QAStatus.NEEDS_HUMAN_REVIEW


def test_parse_qa_full() -> None:
    q = parse_qa_verdict(
        {
            "rubric": {
                "signal_reference": 7,
                "personalization": 7,
                "factual_accuracy": 7,
                "brevity_clarity": 7,
                "cta_quality": 7,
            },
            "approved": True,
            "score": 35,
            "feedback": "ok",
            "issues": [],
        }
    )
    assert q.approved is True
    assert q.score == 35.0
    assert q.qa_status is QAStatus.QA_PASSED


def test_parse_research() -> None:
    r = parse_research_dossier(
        {
            "persona": {
                "full_name": "A",
                "title": "T",
                "company": "Co",
            },
            "company": {
                "name": "Co",
                "domain": "co.com",
            },
        },
        company_fallback="Co",
        domain_fallback="co.com",
    )
    assert r.persona.full_name == "A"
    assert r.company.domain == "co.com"
