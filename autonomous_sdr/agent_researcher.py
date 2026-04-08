"""
Agent 2 — Account Researcher

Takes a validated signal, identifies the right persona to contact at the
company, and compiles a rich research dossier combining Apollo contact
data with scraped website intelligence.
"""

from __future__ import annotations

from typing import Any

from crewai import Agent, Task

from autonomous_sdr.tool_apollo import ApolloPersonSearchTool, WebScraperTool


def create_researcher_agent(llm: Any) -> Agent:
    return Agent(
        role="Account Researcher",
        goal=(
            "Given a company with a validated buying signal, identify the "
            "best target persona to reach out to and compile a concise "
            "research dossier covering the company's product, recent "
            "initiatives, pain points, and the persona's background."
        ),
        backstory=(
            "You are a world-class sales intelligence analyst who spent "
            "years at Gartner before joining this team. You know how to "
            "find the decision-maker who actually owns the budget. You "
            "never target the wrong persona — if a company just raised "
            "funding to expand engineering, you find the VP of Engineering, "
            "not the office manager. You enrich every lead with enough "
            "context to write an email that feels like it was written by "
            "someone who genuinely understands their business."
        ),
        tools=[ApolloPersonSearchTool(), WebScraperTool()],
        llm=llm,
        verbose=True,
        memory=True,
        max_iter=8,
    )


def create_researcher_task(agent: Agent, signal_json: str) -> Task:
    return Task(
        description=(
            "You have received the following validated buying signal:\n\n"
            f"{signal_json}\n\n"
            "Your job:\n\n"
            "1. FIND THE PERSONA: Use Apollo Person Search to identify the "
            "best decision-maker at this company. Target titles like VP of "
            "Sales, VP of Engineering, CTO, Head of Growth, or CRO. If the "
            "signal is about hiring engineers, target engineering leadership. "
            "If it's about revenue growth, target sales/revenue leadership.\n\n"
            "2. RESEARCH THE COMPANY: Use the Company Website Scraper to "
            "visit the company's homepage and /about page. Extract:\n"
            "   - What the company does (one paragraph)\n"
            "   - Their industry and approximate size\n"
            "   - Any recent news, product launches, or initiatives\n"
            "   - Technologies or integrations they mention\n\n"
            "3. COMPILE THE DOSSIER: Combine persona contact details with "
            "company research into a structured research brief."
        ),
        expected_output=(
            "A JSON object with two top-level keys:\n"
            "- 'persona': {full_name, title, email, linkedin_url, company, seniority, department}\n"
            "- 'company': {name, domain, industry, employee_count, funding_stage, "
            "description, recent_news (array of strings), tech_stack (array of strings), "
            "website_summary}"
        ),
        agent=agent,
    )
