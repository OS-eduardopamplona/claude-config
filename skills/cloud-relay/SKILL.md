---
name: cloud-relay
description: >-
  Pair a cloud Claude session (does the code and tests) with a local relay session (signs commits, runs gh, Jira, az)
  that talk through the cloud session's git branch. Use when starting cloud sessions to run more tasks at once, when a
  cloud session's work never showed up, or when writing a cloud worker's or relay's brief.
---

# Cloud worker + local relay

A cloud session has no YubiKey, often no gh/Jira/az credentials, and cannot message any session back. So each cloud
**worker** gets a local **relay**: the worker pushes code to its branch and signals in its last commit's body; the relay
reads that branch, turns the diff into a signed commit on its own branch, and does every outward step (PR, reviews,
auto-merge, Jira, pipelines). The branch is the only channel from worker to relay.

## Platform facts (each one broke a run)

- **Start.** `start_session` with `target: "cloud"` works only on a turn the user typed. A cron, scheduled-task or
  side-session-event turn can only propose a card. The session appears asynchronously, up to ~10 minutes later, and the
  call returns a `task_…` id, not the session's id. It starts from the repository's default branch (or this session's
  pushed branch when started from a worktree).
- **Invisible.** Cloud sessions are not in `list_sessions` and send no turn-end note. Their branch is the only progress
  signal.
- **Branch name.** The cloud harness names the branch itself: `claude/<adjective>-<name>-<suffix>`, with no ticket
  number. Never watch `claude/*<n>*`. Identify the branch by its commits' subjects, which the brief makes start with
  the task key.
- **Session id.** It is in every worker commit's trailer: `Claude-Session: https://claude.ai/code/session_<id>`. Use it
  to message the worker (`SendMessage` to that id); the worker receives but cannot reply except by pushing.
- **Environment.** A private feed the environment can't restore fails at the first build. The worker reports it as
  `RELAY: BLOCKED`, and the task goes to a local worker.

## Signals (last commit's body)

| Line | Relay does |
|---|---|
| `RELAY: READY` + PR description | applies the diff as a signed commit, verifies, opens/updates the draft PR |
| `RELAY: NO-CHANGE <evidence>` | reports to the orchestrator, which closes the task |
| `RELAY: GAP <description>` | reports the out-of-scope gap, keeps going |
| `RELAY: BLOCKED <reason>` | reports and waits |

## Cloud worker brief (fill `<KEY>`, `<repo>`, the problem and acceptance)

1. Read the repo's `CLAUDE.md`, build first. If restore fails, push one empty commit with `RELAY: BLOCKED <first error
   lines>` and end.
2. TDD: tests red on unfixed code, then green. Tests already green on unfixed code → empty commit `RELAY: NO-CHANGE
   <tests and output>`, end.
3. Commit on the branch the harness gave you; keep its name and push only to it. Every commit subject starts with
   `<KEY> `. The last commit's body ends with `RELAY: READY` and a PR description in the repo's template sections.
4. Afterwards you may receive CI failures or review comments: fix, push a new last commit ending `RELAY: READY` with a
   reply per comment. A gap outside the task → a commit with `RELAY: GAP <description>`. Stuck → `RELAY: BLOCKED`.

## Relay brief (local, `use_worktree: true`, a cheaper model is enough)

1. **Find the branch.** In a background loop every 3 minutes (re-invoked on exit, never a foreground sleep):
   ```bash
   git fetch origin '+refs/heads/claude/*:refs/remotes/origin/claude/*'
   for b in $(git for-each-ref --sort=-committerdate --format='%(refname:short)' refs/remotes/origin/claude); do
     git log origin/<default>.."$b" --format=%s | grep -q '^<KEY> ' && { echo "$b"; break; }; done
   ```
   Exit when it finds a branch or that branch's head moves. Read the session id from its `Claude-Session` trailer and
   watch that exact branch from then on.
2. **Apply READY.** In a worktree of your own branch, `git diff $(git merge-base origin/<default> <b>) <b> | git apply
   --index` the first time, `git merge --squash <b>` later. Check the diff against the user's standing rules, build, run
   the named tests, confirm red→green yourself, format, commit signed, push, open the draft PR.
3. **Loop.** Forward real CI failures and review comments to the worker verbatim; re-run infra failures yourself; reply
   on and resolve each thread with the worker's reply. Worker silent 2 hours after a message → do the fix yourself.
4. Report NO-CHANGE, GAP and BLOCKED to whoever started you.
