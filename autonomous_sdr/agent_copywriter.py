"""
Agent 3 — Copywriter

Takes the research dossier (persona + company context + signal) and
crafts a hyper-personalized outreach email that ties the buying signal
to the prospect's specific situation.
"""

from __future__ import annotations

from typing import Any

from crewai import Agent, Task


COPYWRITING_FRAMEWORK = """\
You follow a proven sales copywriting framework:

STRUCTURE:
1. HOOK (first line): Reference the specific trigger event. Never open
   with "I hope this email finds you well" or "I wanted to reach out."
   Instead, lead with something like "Saw that [Company] just closed
   your Series B — congrats."
2. BRIDGE (2-3 sentences): Connect the signal to a pain point or
   opportunity the prospect likely has. Show you understand their world.
3. VALUE PROP (1-2 sentences): Explain what you offer and why it matters
   to them specifically. No generic feature dumps.
4. CTA (1 sentence): A low-friction ask. "Worth a 15-min call this week?"
   or "Happy to send a quick demo link — interested?"

RULES:
- Total email body must be under 150 words
- Never use the word "synergy", "leverage", "circle back", or "touch base"
- Never lie or fabricate facts about the prospect's company
- Write at an 8th-grade reading level — short sentences, no jargon
- The tone should feel like a sharp colleague, not a robot or a used-car salesman
- Subject line must be under 8 words and reference the signal or pain point
"""


def create_copywriter_agent(llm: Any) -> Agent:
    return Agent(
        role="Sales Copywriter",
        goal=(
            "Write a concise, hyper-personalized cold outreach email that "
            "references the specific buying signal and demonstrates genuine "
            "understanding of the prospect's business. The email should feel "
            "human, relevant, and impossible to ignore."
        ),
        backstory=(
            "You are a former journalist turned sales copywriter who writes "
            "emails with a 40%+ open rate and 12%+ reply rate. You despise "
            "generic templates. Every email you write references something "
            "specific — a funding round, a product launch, a LinkedIn post. "
            "You believe that if an email could be sent to any company by "
            "changing the name, it's a bad email. Your style is direct, warm, "
            "and refreshingly honest."
        ),
        llm=llm,
        verbose=True,
        memory=True,
        max_iter=5,
    )


def create_copywriter_task(
    agent: Agent,
    research_json: str,
    signal_json: str,
    revision_feedback: str | None = None,
) -> Task:
    revision_block = ""
    if revision_feedback:
        revision_block = (
            "\n\n--- QA REVISION REQUEST ---\n"
            "Your previous draft was rejected by the QA Reviewer. "
            "Address the following feedback:\n"
            f"{revision_feedback}\n"
            "--- END REVISION REQUEST ---\n"
        )

    return Task(
        description=(
            f"{COPYWRITING_FRAMEWORK}\n\n"
            "BUYING SIGNAL:\n"
            f"{signal_json}\n\n"
            "RESEARCH DOSSIER:\n"
            f"{research_json}\n\n"
            f"{revision_block}"
            "Write the outreach email now. Return a JSON object with keys: "
            "subject_line, body, call_to_action, tone."
        ),
        expected_output=(
            "A JSON object with keys: subject_line (under 8 words), "
            "body (the full email under 150 words), "
            "call_to_action (the specific ask), "
            "tone (one-word description of the email's tone)."
        ),
        agent=agent,
    )
