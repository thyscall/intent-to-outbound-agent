"""
Pydantic models shared across every agent in the pipeline.

These schemas define the contract between pipeline stages:
Signal → Research → Copywriting → QA → Delivery.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


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


class QAVerdict(BaseModel):
    approved: bool
    score: float = Field(ge=0.0, le=10.0)
    feedback: str
    issues: list[str] = Field(default_factory=list)


class PipelineResult(BaseModel):
    """End-to-end output for a single lead that passed through all four agents."""

    signal: SignalEvent
    company: CompanyContext
    persona: PersonaContact
    draft: OutreachDraft
    qa: QAVerdict
    revision_count: int = 0
    delivered: bool = False
