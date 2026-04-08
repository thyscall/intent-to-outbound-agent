# Intent-to-Outbound AI Agent

This is an autonomous system built with LangChain and CrewAI that uses AI agents to constantly be on the lookout for high-intent buying signals, research the right people to talk to, and draft personalized outreach emails.

I wanted to build something that handles the heavy lifting of lead research without a human needing to click every button. The goal is to create a system that acts as a partner to a sales team by finding the best opportunities and doing the dirty work so they can focus on the human side of the business.

## Project Scope

This project is a multi-agent system designed to automate the initial stages of the outbound sales motion. The workflow utilizes four specific agent roles:

* **Signal Monitor:** Scans external data sources like Clay for specific company-level trigger events.
* **Account Researcher:** Identifies target personas within the signaled companies and compiles relevant background data using Apollo and BeautifulSoup
* **Copywriter:** Drafts targeted outreach messaging based on the signal and persona research.
* **QA Reviewer:** Evaluates the drafted text against strict criteria for relevance and tone. This enforces a self-correction loop before final output.

The system concludes by formatting the data and delivering it via Slack for human review and approval.

## Business Intent

Revenue operations and sales teams process large volumes of data to find qualified leads. Standard intent platforms deliver raw lists of companies showing generic activity. Sales representatives must manually research these companies to find the correct contacts and understand the context before writing an email. 

This system automates the research and drafting phases. By providing a verified signal, a researched contact, and a prepared draft, it allows sales professionals to allocate their time to direct prospect engagement.

## Architecture

View the architecture diagram in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## Tech Stack

* **Languages & Frameworks:** Python, LangChain, CrewAI
* **AI:** Google Gemini API (via LangChain `ChatGoogleGenerativeAI`)
* **GTM Tools & APIs:** Clay, Apollo, BeautifulSoup, and Salesforce/HubSpot developer docs
* **Communication:** Slack webhooks

## Project Structure

```text
intent-to-outbound-ai-agent/
│
├── shared/
│   ├── crm_client.py
│   └── schemas.py
│
├── autonomous_sdr/
│   ├── agent_monitor.py     
│   ├── agent_researcher.py
│   ├── agent_copywriter.py
│   ├── agent_reviewer.py
│   ├── tool_clay.py
│   ├── tool_apollo.py
│   ├── main.py
│   └── README.md
│
├── docs/
│   ├── ARCHITECTURE.md
│   └── PROPOSAL.md
│
└── README.md
```

## Setup

```bash
# Clone and enter the project
cd intent-to-outbound-ai-agent

# Create virtual environment
python -m venv .venv && source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure API keys
cp .env.example .env
# Edit .env with your keys: GEMINI_API_KEY (required), CLAY_API_KEY, APOLLO_API_KEY, SLACK_WEBHOOK_URL
```

## Usage

```bash
# Run the full pipeline (GEMINI_API_KEY required; Clay/Apollo optional — demo data if unset)
python -m autonomous_sdr.main

# Custom signal query
python -m autonomous_sdr.main --query "series B healthcare startups"

# Limit to 3 signals
python -m autonomous_sdr.main --max-signals 3
```

Results are saved to `output/leads.jsonl` and delivered to Slack (if configured).

## Documentation

* [Architecture Diagram](docs/ARCHITECTURE.md)
* [Project Proposal](docs/PROPOSAL.md)
* [SDR Module Details](autonomous_sdr/README.md)
