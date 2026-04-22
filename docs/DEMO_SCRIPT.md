# Demo Script (10-15 minutes)

Use this script for a live walkthrough and code review conversation.

## 1) Open with business value (1 minute)

Suggested talk track:

> "This agent takes raw account activity and turns it into outbound-ready work.  
> Instead of manually researching every lead, SDR/AE teams get a validated signal, a target persona, a draft message, and a traceable record of what happened."

## 2) Show architecture and role separation (1-2 minutes)

- Open `docs/ARCHITECTURE.md`.
- Explain the four agents:
  - Signal Monitor
  - Account Researcher
  - Copywriter
  - QA Reviewer

## 3) Run the no-key demo (2-3 minutes)

```bash
cd intent-to-outbound-ai-agent
python -m autonomous_sdr.main --max-signals 1
```

What to point out:
- Pipeline runs end-to-end without external credentials.
- Logs show stage progression and QA/validation decisions.
- This is intended for reliable interview/demo mode.

## 4) Show output artifact and explain data (2-3 minutes)

Open `output/leads.jsonl` and point to:
- `run_id`, `lead_id`, `schema_version`
- `signal`, `persona`, `draft`, `qa`
- `deterministic_validation`
- `terminal_status` (`approved_not_delivered`, etc.)

Suggested line:

> "This gives RevOps and GTM engineering a replayable, auditable record even before Postgres is added."

## 5) Explain optional live integrations (1-2 minutes)

- Clay live mode requires `CLAY_API_KEY` + `CLAY_TABLE_ID`.
- Slack live delivery requires `SLACK_WEBHOOK_URL`.
- Apollo is intentionally optional for this sprint.

Mention current status:
- If keys are missing, the project stays demo-ready with fallback mode.

## 6) Code review focus points (2-3 minutes)

Show these files and why they matter:
- `autonomous_sdr/main.py` -> orchestration and QA loop
- `shared/parsing.py` -> strict contract parsing from model output
- `shared/validators.py` -> deterministic quality gate
- `shared/crm_client.py` -> persisted lead envelope for reporting

## 7) Close with realistic next steps (1 minute)

- Complete live Clay + Slack verification with keys.
- Implement M3 Postgres ledger.
- Add M4 CRM sync and M5 soak/release gates.

Reference: `docs/ROADBLOCKS_AND_NEXT_STEPS.md`
