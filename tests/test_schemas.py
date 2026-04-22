"""Validate schema-level QA rubric contracts and invariants.

This module confirms scoring rules stay bounded and the aggregate score behavior
matches the rubric model semantics. It protects data integrity by catching
contract drift before pipeline results are persisted.
"""

import pytest
from pydantic import ValidationError

from shared.schemas import QARubricScores, QAVerdict, QAStatus


def test_rubric_sum_aligns() -> None:
    r = QARubricScores(
        signal_reference=6,
        personalization=6,
        factual_accuracy=6,
        brevity_clarity=6,
        cta_quality=6,
    )
    q = QAVerdict(
        rubric=r,
        approved=False,
        feedback="",
        issues=[],
        qa_status=QAStatus.QA_FAILED,
    )
    assert q.score == 30.0


def test_rubric_rejects_out_of_range() -> None:
    with pytest.raises(ValidationError):
        QARubricScores(
            signal_reference=11,
            personalization=0,
            factual_accuracy=0,
            brevity_clarity=0,
            cta_quality=0,
        )
