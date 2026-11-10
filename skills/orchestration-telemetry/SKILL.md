---
name: orchestration-telemetry
description: Tokens, cost, active time, CI minutes and review rounds per Claude session and per ticket, from local files. Use when asked what a session, a ticket or an orchestrator's family of sessions cost, to refresh the ledger dashboard, or when the OTel export stops writing.
---

# Orchestration telemetry

Everything lives under `~/.claude`: the scripts in `telemetry-tools/`, the data in `telemetry/` (git-ignored). Python 3, no packages.

| Piece | What it does | Output |
|---|---|---|
| `otlp_receiver.py` | OTLP/HTTP JSON receiver on `127.0.0.1:14318`, started at logon by the `claude-otlp-receiver` Startup shortcut (pythonw) | `telemetry/otel/{logs,metrics}-<date>.jsonl` |
| `settings.json` `env` | `CLAUDE_CODE_ENABLE_TELEMETRY` and the `OTEL_*` vars point every new session at the receiver | — |
| `backfill.py` | tokens by type and model, list-price cost, idle-capped active minutes per CLI session, from `projects/**/*.jsonl` (subagents folded into their parent) | `telemetry/backfill/sessions.json` |
| `rollup.py` | one row per ticket for an orchestrator and its descendants: sessions, cost, active and wall time, PRs, CI runs/minutes/reruns, human review rounds, Jira state | `telemetry/rollup/<root>.json` and `.csv` |
| `dashboard.py` + `dashboard.html` | renders a roll-up as the "<ticket> Ledger" page | `telemetry/dashboard/<root>.html` |

## Refresh the ledger

1. Refresh the Jira cache when statuses matter: run the Atlassian MCP `searchJiraIssuesUsingJql` (cloudId `3755dbe1-fa22-4c37-956e-59bea84af9cf`, `parent = <epic> OR key = <epic>`, fields `summary,status,created,resolutiondate,statuscategorychangedate,assignee,parent`) and write `telemetry/jira/issues.json` as `{fetched_at, source, issues: {KEY: {summary, status, status_category, created, resolutiondate, statuscategorychangedate, assignee, parent}}}`. Summary fields only: a changelog costs ~10K tokens per issue.
2. `python ~/.claude/telemetry-tools/rollup.py --root <local_ id or prefix> --state <orchestrator state file> --root-ticket <epic> --since <YYYY-MM-DD>`; `--no-remote` skips `gh` and `az`.
3. `python ~/.claude/telemetry-tools/dashboard.py` renders the newest roll-up.
4. Publish `telemetry/dashboard/<root>.html` with the Artifact tool. The RDMST-5555 ledger is `https://claude.ai/code/artifact/2753cc60-a9ae-4fe5-b1f6-6c552b3ceea1`: pass it as `url` from any other session, which keeps the link.

Done when the publish returns a new version and every ticket worked since `--since` has a row.

## How a session finds its ticket

`rollup.py` walks the desktop session records (`Claude-Data/*/claude-code-sessions/**/local_*.json`) down from the root through `spawnedFrom.sessionId`. A session's ticket is its row in the state file's Worker column, else the first non-epic `RDMST-nnnn` in its title, spawn name, branch or PR branches. A PR belongs to the ticket its title or branch names. The root's own row is `orchestration`.

## Gaps

- Cloud sessions have no local transcripts or OTel: counted from `cloudSpawnedTasks` and the state file's `session_` ids, never costed.
- Cost is list price from `PRICES` in `backfill.py`; add a model there when a row lists it under `unpriced_models`. OTel `claude_code.cost.usage` and `active_time.total` show beside the estimate once a session exported them.
- Jira cycle time is created to resolved (or now), with no transitions.
- Repos with no Azure DevOps definition (rd-ai-agent-lib, evals) take CI from `gh run list` on the head branch.

## When the export stops

- `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:14318/health` answers 200 while the receiver runs; otherwise start the Startup shortcut again. Ports 4317/4318 belong to the os-ts Aspire containers, hence 14318.
- Only sessions started after the `env` change export. `claude -p` with an expired login exports startup events but no `api_request`.
- On Windows, `subprocess` needs `shutil.which` to find `az` (`az.cmd`).
