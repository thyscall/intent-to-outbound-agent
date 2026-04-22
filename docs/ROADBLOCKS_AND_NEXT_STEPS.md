# Roadblocks and Next Steps

## What was completed for this demo sprint

- End-to-end autonomous GTM flow is runnable locally with no API keys.
- Pipeline persists reviewable results to `output/leads.jsonl`.
- QA + deterministic validation behavior is visible in logs and persisted records.

## Roadblocks encountered

- Live Clay verification could not be completed because `CLAY_API_KEY` and `CLAY_TABLE_ID` were not configured.
- Live Slack delivery could not be completed because `SLACK_WEBHOOK_URL` was not configured.
- Apollo was intentionally deprioritized for this sprint to keep scope realistic for a 4-hour delivery window.

## Why these were deferred

The priority for this cycle was to deliver a stable demo and clean code-review baseline. Integrations that require credentials and environment setup were treated as optional so the core workflow could be proven regardless of external dependencies.

## Recommended next steps (in order)

1. Configure Clay and run a live signal pull.
2. Configure Slack webhook and verify one successful outbound delivery event.
3. Add Postgres ledger (M3) for `pipeline_runs`, `leads`, `agent_actions`, and `outbound_events`.
4. Implement production CRM sync (M4) and then run staging soak + launch checks (M5).
