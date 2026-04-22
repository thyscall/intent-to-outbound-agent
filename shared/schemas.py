"""
These are the shared business data contracts for the outbound pipeline.
Every stage writes into these models so teams can trust that signals, research,
QA outcomes, and delivery states are consistent across runs and reporting.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, computed_field

from shared.versioning import PIPELINE_SCHEMA_VERSION


class SignalType(str, Enum):
    FUNDING_ROUND = "funding_round"
    LEADERSHIP_CHANGE = "leadership_change"
    EXPANSION = "expansion"
    PRODUCT_LAUNCH = "product_launch"
    PARTNERSHIP = "partnership"
    JOB_POSTING = "job_posting"


class SignalEvent(BaseModel):
    company_name: str
    domain: str
    signal_type: SignalType
    headline: str
    details: str
    source_url: Optional[str] = None
    detected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class CompanyContext(BaseModel):
    name: str
    domain: str
    industry: Optional[str] = None
    employee_count: Optional[int] = None
    funding_stage: Optional[str] = None
    funding_amount: Optional[str] = None
    headquarters: Optional[str] = None
    description: Optional[str] = None
    recent_news: list[str] = Field(default_factory=list)
    tech_stack: list[str] = Field(default_factory=list)
    website_summary: Optional[str] = None


class PersonaContact(BaseModel):
    full_name: str
    title: str
    email: Optional[str] = None
    linkedin_url: Optional[str] = None
    company: str
    seniority: Optional[str] = None
    department: Optional[str] = None


class OutreachDraft(BaseModel):
    subject_line: str
    body: str
    call_to_action: str
    tone: str = "professional-casual"


class DraftValidationResult(BaseModel):
    """Deterministic, non-LLM validation outcome for a draft."""

    passed: bool
    rule_version: str
    failed_rules: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    body_word_count: int = 0
    subject_word_count: int = 0


class QARubricScores(BaseModel):
    """Five rubric dimensions, 0–10 each (50 points total with score)."""

    signal_reference: float = Field(ge=0.0, le=10.0)
    personalization: float = Field(ge=0.0, le=10.0)
    factual_accuracy: float = Field(ge=0.0, le=10.0)
    brevity_clarity: float = Field(ge=0.0, le=10.0)
    cta_quality: float = Field(ge=0.0, le=10.0)

    def rubric_sum(self) -> float:
        return (
            self.signal_reference
            + self.personalization
            + self.factual_accuracy
            + self.brevity_clarity
            + self.cta_quality
        )


class QAStatus(str, Enum):
    """QA layer outcome (LLM + business rules), distinct from terminal pipeline status."""

    QA_PASSED = "qa_passed"
    QA_FAILED = "qa_failed"
    NEEDS_HUMAN_REVIEW = "needs_human_review"


class LeadTerminalStatus(str, Enum):
    """End state for a lead in a pipeline run (for logging and JSONL)."""

    DELIVERED = "delivered"  # QA approved, deterministic pass, Slack success
    APPROVED_NOT_DELIVERED = "approved_not_delivered"  # QA ok but no Slack or Slack failed
    NEEDS_HUMAN_REVIEW = "needs_human_review"
    QA_FAILED = "qa_failed"  # e.g. max revisions without approval


class QAVerdict(BaseModel):
    """LLM reviewer output: five dimensions (0–10 each) and total score 0–50."""

    rubric: QARubricScores
    approved: bool
    feedback: str
    issues: list[str] = Field(default_factory=list)
    qa_status: QAStatus = QAStatus.NEEDS_HUMAN_REVIEW

    @computed_field  # type: ignore[prop-decorator]
    @property
    def score(self) -> float:
        """Total score is always the sum of the five rubric dimensions (0–50)."""
        return round(self.rubric.rubric_sum(), 2)


class ResearchDossier(BaseModel):
    """Structured account research: persona + company blocks."""

    persona: PersonaContact
    company: CompanyContext


class PipelineResult(BaseModel):
    """End-to-end output for a single lead that passed through all four agents."""

    run_id: UUID
    lead_id: UUID
    schema_version: str = PIPELINE_SCHEMA_VERSION
    signal: SignalEvent
    company: CompanyContext
    persona: PersonaContact
    draft: OutreachDraft
    qa: QAVerdict
    revision_count: int = 0
    delivered: bool = False
    terminal_status: LeadTerminalStatus = LeadTerminalStatus.NEEDS_HUMAN_REVIEW
    deterministic_validation: Optional[DraftValidationResult] = None
