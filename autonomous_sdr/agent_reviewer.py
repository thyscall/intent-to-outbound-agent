"""
Agent 4 — QA Reviewer

Evaluates drafted outreach against strict quality criteria.
Acts as the final gate before any message reaches a human rep.
Rejects drafts that are generic, contain hallucinated facts,
or violate tone guidelines — triggering a revision loop.
"""

from __future__ import annotations

from typing import Any

from crewai import Agent, Task


QA_RUBRIC = """\
Score each dimension from 0-10. The "score" field must equal the sum of the
five rubric values (0–50 total).

1. SIGNAL REFERENCE (0-10): Does the email explicitly mention the
   specific buying signal (funding round, hire, product launch)?
   A generic opener scores 0. A direct reference with context scores 10.

2. PERSONALIZATION (0-10): Does the email reference the prospect's
   actual company, role, or business? Could this email only be sent
   to THIS person at THIS company? Swap-the-name-and-send scores 0.

3. FACTUAL ACCURACY (0-10): Are all claims about the company verifiable
   from the research dossier? Any hallucinated facts (fake metrics,
   made-up products, wrong names) score 0 and AUTOMATICALLY FAIL the email.

4. BREVITY & CLARITY (0-10): Is the email under 150 words? Is it written
   at an 8th-grade reading level? Are sentences short and punchy?

5. CTA QUALITY (0-10): Is there a clear, low-friction call to action?
   "Let me know your thoughts" is weak (3). "Worth a 15-min call Thursday?"
   is strong (8+).

PASS THRESHOLD: Total score must be >= 35/50 to approve.
Any dimension scoring 0 is an automatic failure regardless of total.
"""


def create_reviewer_agent(llm: Any) -> Agent:
    return Agent(
        role="QA Reviewer",
        goal=(
            "Rigorously evaluate outreach email drafts against strict quality "
            "criteria. Reject anything generic, hallucinated, or spammy. "
            "Only approve emails that are genuinely personalized, factually "
            "accurate, and would make a busy executive want to reply."
        ),
        backstory=(
            "You are a former VP of Sales who has received tens of thousands "
            "of cold emails and can instantly tell when one was mass-produced "
            "versus carefully crafted. You have zero tolerance for generic "
            "outreach. If an email mentions 'synergy' or opens with 'I hope "
            "this finds you well', you reject it immediately. You are the "
            "quality gate that protects the team's reputation. A bad email "
            "that reaches a prospect damages trust permanently."
        ),
        llm=llm,
        verbose=True,
        memory=True,
        max_iter=3,
    )


def create_reviewer_task(
    agent: Agent,
    draft_json: str,
    research_json: str,
    signal_json: str,
) -> Task:
    return Task(
        description=(
            f"{QA_RUBRIC}\n\n"
            "ORIGINAL BUYING SIGNAL:\n"
            f"{signal_json}\n\n"
            "RESEARCH DOSSIER:\n"
            f"{research_json}\n\n"
            "EMAIL DRAFT TO REVIEW:\n"
            f"{draft_json}\n\n"
            "Return valid JSON only. Include all keys below. "
            "The sum of the five rubric numbers must match 'score'."
        ),
        expected_output=(
            "A single JSON object with these exact keys: "
            "rubric (object with keys: signal_reference, personalization, "
            "factual_accuracy, brevity_clarity, cta_quality — each 0-10), "
            "approved (boolean), "
            "score (number 0-50, equal to the sum of the five rubric values), "
            "feedback (string), "
            "issues (array of strings — empty if approved)."
        ),
        agent=agent,
    )
