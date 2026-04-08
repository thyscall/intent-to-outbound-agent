"""
Agent 1 — Signal Monitor

Scans Clay enrichment tables for company-level trigger events
(funding rounds, leadership changes, expansion signals) and decides
whether each signal is valid and worth pursuing.
"""

from __future__ import annotations

from typing import Any

from crewai import Agent, Task

from autonomous_sdr.tool_clay import ClaySignalSearchTool


def create_monitor_agent(llm: Any) -> Agent:
    return Agent(
        role="Signal Monitor",
        goal=(
            "Continuously scan external data sources for high-intent "
            "buying signals — specifically recent funding rounds, senior "
            "leadership hires, market expansion announcements, and new "
            "product launches at B2B software or healthcare companies."
        ),
        backstory=(
            "You are the first line of intelligence for an elite outbound "
            "sales team. Your entire job is to spot the companies that just "
            "experienced a trigger event making them 5-10x more likely to "
            "buy in the next 90 days. You have deep pattern recognition for "
            "what separates noise from genuine buying signals. A Series B "
            "with a top-tier lead? That's a signal. A minor blog post about "
            "company culture? That's noise. You filter ruthlessly."
        ),
        tools=[ClaySignalSearchTool()],
        llm=llm,
        verbose=True,
        memory=True,
        max_iter=5,
    )


def create_monitor_task(agent: Agent, signal_query: str = "") -> Task:
    return Task(
        description=(
            f"Search for companies exhibiting high-intent buying signals. "
            f"Query focus: '{signal_query or 'recent funding rounds in healthcare tech'}'\n\n"
            "For EACH signal found, evaluate:\n"
            "1. Is this a genuine trigger event (funding, leadership change, expansion)?\n"
            "2. Is the company in B2B software, healthcare, or a related vertical?\n"
            "3. Is the signal recent (within the last 30 days)?\n\n"
            "Discard signals that are just PR fluff, minor blog posts, or "
            "irrelevant verticals. Return ONLY validated signals.\n\n"
            "For each validated signal, provide:\n"
            "- company_name\n"
            "- domain\n"
            "- signal_type (funding_round / leadership_change / expansion / product_launch)\n"
            "- headline (one sentence)\n"
            "- details (2-3 sentences of context)\n"
            "- source_url (if available)"
        ),
        expected_output=(
            "A JSON array of validated signal objects. Each object has keys: "
            "company_name, domain, signal_type, headline, details, source_url. "
            "Return an empty array [] if no valid signals are found."
        ),
        agent=agent,
    )
