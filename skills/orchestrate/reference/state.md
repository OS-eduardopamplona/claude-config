# STATE.md

`~/.claude/orchestrations/<KEY>/STATE.md` is the orchestration's single source of truth. The orchestrator owns it; the
pickup task may add rows' workers and Log lines. It holds the **current picture**: a cell says where a row stands now,
never its history.

```markdown
# <KEY> orchestration
Updated: <ISO time>
Goal: <the parent ticket's URL and what done means, one paragraph>
Orchestrator: <local_ id> since <date>. Family notes: side-session-notes/<local_ id>/
Repos: <profile names from repos.md>
Capacity: <n> local workers; cloud <environment | no>
Tick cron: <id>, expires <date>. Pickup task: <name | none>
Retro: last <ISO time>; RESULTs since: <n>

## Decisions
- <YYYY-MM-DD>: "<Eduardo's words>" → <what it changes>

## Rules
- <rules every brief of this orchestration carries: files never to commit, build throttles>

## Tickets
| Ticket | Status | Worker | PR | Head | Checked | Notes |
|---|---|---|---|---|---|---|

## Log
- <ISO time> <one line>
```

## Decisions

Quote Eduardo's words and date them. A later decision that reverses one marks the old line `SUPERSEDED <date>`. The
retro removes superseded lines whose replacement has held for a week.

## Statuses

| Status | Meaning | Leaves when |
|---|---|---|
| `queued` | pickable once capacity allows | Pickup starts a worker → `working` |
| `held` | waits on a named blocker (a PR, a release) | the blocker clears → `queued` |
| `skipped` | someone else's, or out of scope; Notes says why | Eduardo reverses it |
| `working` | worker started, no PR yet | its PR appears → `in-review` |
| `in-review` | PR open | merged → `done`; closed → `blocked` |
| `paused` | worker stopped by a decision | the decision lifts → back to its previous status |
| `waiting-eduardo` | needs Eduardo; every other row keeps moving | he answers |
| `blocked` | worker reported `blocked`, or the PR closed unmerged | the cause is fixed |
| `done` | PR merged, ticket Done | — |
| `dropped` | discarded, with its reason | — |

`PR` is `<repo>#<n>` for any repo other than the first in `Repos`. `Head` is the last-handled head sha, or `—` to force
the next tick to look. A cloud row's `Worker` is `<cloud session id> via <relay local_ id>`.

## Log

One line per event, newest last: workers started, archived, stuck; decisions applied; retros. The retro prunes it.
