"""Expose the project's core schema models from one import surface.

This module re-exports the most-used Pydantic contracts so pipeline and test
code can import consistent types without repeating long import paths. Keeping
these exports centralized helps reduce schema drift across the codebase.
"""

from shared.schemas import (
    CompanyContext,
    DraftValidationResult,
    LeadTerminalStatus,
    OutreachDraft,
    PersonaContact,
    PipelineResult,
    QARubricScores,
    QAStatus,
    QAVerdict,
    ResearchDossier,
    SignalEvent,
    SignalType,
)

__all__ = [
    "CompanyContext",
    "DraftValidationResult",
    "LeadTerminalStatus",
    "OutreachDraft",
    "PersonaContact",
    "PipelineResult",
    "QARubricScores",
    "QAStatus",
    "QAVerdict",
    "ResearchDossier",
    "SignalEvent",
    "SignalType",
]
