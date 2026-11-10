---
name: orchestration-telemetry
description: Tokens, cost, active time, CI minutes, review rounds, CPU, RAM, disk and tool time per Claude session and per ticket, from local files, plus a capacity sizing for a dedicated agent machine. Use when asked for "telemetry for this session" or for session `local_…`, what a session and the sessions it started, a ticket or an orchestrator's family cost or used, what every session on this machine used since a date, how big a machine for the agents should be, to refresh the ledger dashboard, or when the OTel export or the resource sampler stops writing.
---

# Orchestration telemetry

Everything lives under `~/.claude`: the scripts in `telemetry-tools/`, the data in `telemetry/` (git-ignored). Python 3, no packages.

| Piece | What it does | Output |
|---|---|---|
| `otlp_receiver.py` | OTLP/HTTP JSON receiver on `127.0.0.1:14318`, started at logon by the `claude-otlp-receiver` Startup shortcut (pythonw) | `telemetry/otel/{logs,metrics}-<date>.jsonl` |
| `settings.json` `env` | `CLAUDE_CODE_ENABLE_TELEMETRY` and the `OTEL_*` vars point every new session at the receiver | — |
| `resource_sampler.py` | started by the receiver: every 15 s reads every process's CPU, memory and I/O, attributes it to the CLI session above it in the process tree, and writes one line a minute (machine, per session, desktop app, unattributed); `--once` prints a sample | `telemetry/resources/samples-<date>.jsonl` |
| `hooks/telemetry-register.sh` | `SessionStart` and `UserPromptSubmit` hook: maps a CLI's pid to its desktop session | `telemetry/pids/<pid>.json` |
| `backfill.py` | tokens by type and model, list-price cost, idle-capped active minutes per CLI session, from `projects/**/*.jsonl` (subagents folded into their parent) | `telemetry/backfill/sessions.json` |
| `rollup.py` + `capacity.py` | one row per ticket for a session and its descendants (`--root`), or per ticket, repo or family for every session on the machine (`--all`): sessions, local or cloud, cost, active and wall time, tool time by kind (build, test, git, ...), CPU hours, peak RAM, worktree disk, PRs, CI runs/minutes/reruns, human review rounds, Jira state; and a `capacity` block (concurrency, peaks, footprint per session, `sizing`) | `telemetry/rollup/<root>.json` (or `all-<group>-<date>.json`) and `.csv` |
| `dashboard.py` + `dashboard.html` | renders a roll-up as one page, whose title and copy follow its shape: one session, a family, or all sessions | `telemetry/dashboard/<root>.html` |

## Telemetry for one session, on demand

1. `python ~/.claude/telemetry-tools/rollup.py --root self --report` for the session asking (`CLAUDE_CODE_HOST_SESSION_ID`, else `telemetry/pids/<CLAUDE_PID>.json`), or `--root <local_ id or prefix>` for another. It takes that session and every session it started, recursively, since the root started (`--since` overrides); `--state` and `--root-ticket` are optional. `--report` prints a Markdown summary per row: cost, tokens, active and wall time, tool time by kind, CPU, RAM, disk, PRs, CI and review rounds.
2. Answer from that summary. Say "not measured" with its reason for a value the roll-up has none for, never 0.
3. When a page helps, `python ~/.claude/telemetry-tools/dashboard.py telemetry/rollup/<root>.json` and publish `telemetry/dashboard/<root>.html` as a new artifact. Never publish it over the ledger below.

## Every session on the machine

`python ~/.claude/telemetry-tools/rollup.py --all --since <YYYY-MM-DD> --group ticket|repo|family --report`: every desktop session active since then, and every CLI transcript with no desktop record, one row per ticket, repo or family (the top session's ticket or title). Its `capacity` counts every local session on the machine, so size a machine request from this view, not from one family.

## Refresh the ledger

1. Refresh the Jira cache when statuses matter: run the Atlassian MCP `searchJiraIssuesUsingJql` (cloudId `3755dbe1-fa22-4c37-956e-59bea84af9cf`, `parent = <epic> OR key = <epic>`, fields `summary,status,created,resolutiondate,statuscategorychangedate,assignee,parent`) and write `telemetry/jira/issues.json` as `{fetched_at, source, issues: {KEY: {summary, status, status_category, created, resolutiondate, statuscategorychangedate, assignee, parent}}}`. Summary fields only: a changelog costs ~10K tokens per issue.
2. `python ~/.claude/telemetry-tools/rollup.py --root <local_ id or prefix> --state <orchestrator state file> --root-ticket <epic> --since <YYYY-MM-DD>`; `--no-remote` skips `gh` and `az`; `--no-disk` skips measuring worktrees (cached 6 h in `telemetry/cache/disk.json`).
3. `python ~/.claude/telemetry-tools/dashboard.py` renders the newest roll-up.
4. Publish `telemetry/dashboard/<root>.html` with the Artifact tool. The RDMST-5555 ledger is `https://claude.ai/code/artifact/2753cc60-a9ae-4fe5-b1f6-6c552b3ceea1`: pass it as `url` from any other session, which keeps the link.

Done when the publish returns a new version and every ticket worked since `--since` has a row.

## How a session finds its ticket

`rollup.py` walks the desktop session records (`Claude-Data/*/claude-code-sessions/**/local_*.json`) down from the root through `spawnedFrom.sessionId`; `--all` takes every record instead. A session's ticket is its row in the state file's Worker column, else the first non-epic `RDMST-nnnn` in its title, spawn name, branch or PR branches. A PR belongs to the ticket its title or branch names. The root finds its own ticket the same way; it is `orchestration` only when it started sessions and names no ticket (`--root-ticket` otherwise), and `unmapped` alone.

## Capacity sizing

`capacity.sizing` gives cores, RAM and disk for a machine that runs the local sessions, each input marked measured or missing with its source. Cores and RAM are the 95th percentile of concurrent local sessions times the 95th percentile footprint of one session (plus 4 GB for the OS); disk is the worktrees times 1.2. Multiplying two 95th percentiles overstates RAM, since sessions rarely peak together: compare with the machine's own peak (`capacity.resources`). The footprint needs days of samples before it is a basis for a request.

## Gaps

- Resource data exists only from 2026-11-10 16:12 UTC, when the sampler started; earlier sessions have tool time from their transcripts, not CPU or RAM. A row without samples says "not measured" and why (before the sampler, receiver down, CLI never mapped, cloud), in `resources_notes`; one sampled for under 90% of its active minutes says "partly measured".
- A process that lives under 15 s is partly missed; processes left behind by a CLI that has exited are unattributed. A CLI started before the hook maps on its next prompt.
- Cloud sessions have no resource data, and their concurrency counts from their first to their last mention in the transcripts.
- Tool time is wall time, not CPU. A worktree shared by two tickets counts in both rows.
- Cloud sessions have no local transcripts or OTel: counted from `cloudSpawnedTasks` and the state file's `session_` ids, never costed.
- Cost is list price from `PRICES` in `backfill.py`; add a model there when a row lists it under `unpriced_models`. OTel `claude_code.cost.usage` and `active_time.total` show beside the estimate once a session exported them.
- Jira cycle time is created to resolved (or now), with no transitions.
- Repos with no Azure DevOps definition (rd-ai-agent-lib, evals) take CI from `gh run list` on the head branch.

## When the export stops

- The sampler runs inside the receiver and never counts its own CPU against a session (about 50 ms of CPU per 15 s). Once a day it deletes `resources/samples-*` and `otel/*-<date>.jsonl` older than 90 days and `pids/` files untouched for 30 days. A sampler error lands in `telemetry/otel/receiver.log`; `python ~/.claude/telemetry-tools/resource_sampler.py --once` checks it by hand.
- `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:14318/health` answers 200 while the receiver runs; otherwise start the Startup shortcut again. Ports 4317/4318 belong to the os-ts Aspire containers, hence 14318.
- Only sessions started after the `env` change export. `claude -p` with an expired login exports startup events but no `api_request`.
- On Windows, `subprocess` needs `shutil.which` to find `az` (`az.cmd`).
