# autonomous_sdr

Core module containing the four-agent pipeline for intent-to-outbound automation.

## Agents

| Agent              | File           | Role 
|--------------------|----------------|--------------------------------------------------------|
| Signal Monitor     | `agent_monitor.py`    | Scans Clay for buying signals and filters noise from real triggers   |
| Account Researcher | `agent_researcher.py` | Identifies target personas via Apollo and scrapes company context |
| Copywriter         | `agent_copywriter.py` | Drafts hyper-personalized outreach tied to the specific signal |
| QA Reviewer        | `agent_reviewer.py`   | Scores drafts on a 50-point rubric and triggers revision loops  |

## Tools

| Tool                    | File             | External API                   |
|-------------------------|------------------|--------------------------------|
| Clay Signal Search      | `tool_clay.py`   | Clay v3 table rows API         |
| Apollo Person Search    | `tool_apollo.py` | Apollo mixed_people/search API |
| Company Website Scraper | `tool_apollo.py` | BeautifulSoup + requests       |

## Running

```bash
# Full pipeline with default query
python -m autonomous_sdr.main

# Custom signal query
python -m autonomous_sdr.main --query "series B healthcare"

# Limit to 3 signals
python -m autonomous_sdr.main --max-signals 3
```

## QA Self-Correction Loop

The Copywriter → Reviewer loop runs up to 3 iterations. If the QA Reviewer rejects a draft (score < 35/50 or any dimension at 0), it sends specific feedback back to the Copywriter for revision. After 3 attempts, the best draft is forwarded with QA notes for human review.

All agents use **Google Gemini** (`shared/llm.py` → `ChatGoogleGenerativeAI`). Set `GEMINI_API_KEY` and optionally `GEMINI_MODEL` in `.env`.
