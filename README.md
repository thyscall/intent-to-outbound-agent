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

## Production contracts (M1 + M2)

* **Pydantic schemas** in `shared/schemas.py`: each lead has `run_id`, `lead_id`, `schema_version`, five-dimension QA `rubric`, `terminal_status`, and the latest **deterministic** `DraftValidationResult` (including `rule_version`).
* **Stage parsing** in `shared/parsing.py` turns agent JSON into these models. Incomplete reviewer JSON → `qa_status: needs_human_review` and issue `incomplete_qa_rubric` (no fake scores).
* **JSONL envelope** in `output/leads.jsonl` (local CRM fallback): one line per `push_lead` with `recorded_at`, `run_id`, `lead_id`, `schema_version`, `terminal_status`, `deterministic_validation`, and nested `result` (full `PipelineResult`). Salesforce/HubSpot clients still log to the same file until real CRM upserts exist.
* **HTTP**: Clay, Apollo, website fetches, and Slack use a shared `requests` session with retries, backoff, and timeouts (`shared/http.py`, env: `HTTP_*`).
* **Slack idempotency**: SQLite at `output/.intent_outbound_dedupe.sqlite` (override with `IDEMPOTENCY_DB_PATH`) records a key **after** a successful POST so retries do not double-send. Assumes a single writer.
* **Logging**: one JSON object per line on stdout (`shared/logging_config.py`) with `event`, `run_id`, `lead_id`, `stage`, and optional `log_payload`. Set `LOG_REDACT=true` to redact obvious emails/phones in nested payloads.

## Project Structure

```text
intent-to-outbound-ai-agent/
│
├── shared/
│   ├── crm_client.py
│   ├── http.py
│   ├── idempotency.py
│   ├── logging_config.py
│   ├── llm.py
│   ├── parsing.py
│   ├── redact.py
│   ├── schemas.py
│   ├── validators.py
│   └── versioning.py
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
├── tests/
│   └── ...
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
# Edit .env with your keys: GEMINI_API_KEY, CLAY_API_KEY, APOLLO_API_KEY, SLACK_WEBHOOK_URL
# Optional: see .env.example for HTTP timeouts, log level, and idempotency DB path.
```

## Demo Modes

### 1) Fast Local Demo (No Keys Required)

Use this for interviews, code review, and dry-runs when external APIs are not configured.

```bash
python -m autonomous_sdr.main --max-signals 1
```

What this demonstrates:
- Full signal -> research -> draft -> QA -> persistence flow
- Deterministic validation and terminal statuses
- Structured logs and `output/leads.jsonl` record generation

### 2) Live Integration Demo (Optional)

If you have credentials ready, the same command path will use live services:
- **Clay** for signals (`CLAY_API_KEY`, `CLAY_TABLE_ID`)
- **Gemini** for agent reasoning (`GEMINI_API_KEY`)
- **Slack** for delivery (`SLACK_WEBHOOK_URL`)

Apollo is optional for this sprint and can remain in demo fallback mode.

## Tests

```bash
python -m pytest tests/ -q
```

## Usage

```bash
# Run pipeline (no keys = local demo mode; with GEMINI key = live agent mode)
python -m autonomous_sdr.main

# Custom signal query
python -m autonomous_sdr.main --query "series B healthcare startups"

# Limit to 3 signals
python -m autonomous_sdr.main --max-signals 3
```

Results are saved to `output/leads.jsonl` and delivered to Slack (if configured).

## Current Sprint Scope and Roadblocks

For this demo-focused sprint, the project intentionally prioritizes runnable workflow quality over full production integrations:

- **Included now:** reliable local demo mode, QA self-correction loop, deterministic validation, structured logs, and persisted outcomes.
- **Attempted but blocked by missing keys in current environment:** live Clay and Slack verification.
- **Deferred intentionally:** Apollo production setup, Postgres M3 ledger implementation, CRM production sync, and soak-testing automation.

See [Roadblocks and Next Steps](docs/ROADBLOCKS_AND_NEXT_STEPS.md) for a concise handoff plan.

## Documentation

* [Architecture Diagram](docs/ARCHITECTURE.md)
* [Project Proposal](docs/PROPOSAL.md)
* [SDR Module Details](autonomous_sdr/README.md)
