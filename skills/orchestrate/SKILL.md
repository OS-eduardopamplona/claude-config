---
name: orchestrate
description: >-
  Orchestrate a Jira parent's sub-tasks as worker sessions, each ending in a merged PR. Use when asked to orchestrate or
  work through a ticket's sub-tasks, to resume or close an orchestration, when a cron or scheduled task says to run an
  orchestration's tick, pickup or retro, or when writing a worker, cloud worker or relay brief.
argument-hint: "[start|resume|tick|pickup|retro|close] <KEY>"
---

# Orchestrate

An **orchestration** works one Jira parent `<KEY>`: one **worker** session per sub-task, each ending in a merged PR.
You, the **orchestrator**, decide, track and react; workers write the code. Its single state file is
`~/.claude/orchestrations/<KEY>/STATE.md` ([layout and statuses](reference/state.md)). Eduardo's dated decisions in it
override the defaults here. Repo specifics (paths, CI, merge policy, Jira transitions) are in
[repos.md](reference/repos.md).

## Platform facts

- `start_session` works only on a turn Eduardo typed. Cron, scheduled-task and side-session-event turns propose
  `own_initiative` cards instead.
- After about 10 cross-session messages with no turn from Eduardo, the app holds further ones. Log the pending
  reaction and tell Eduardo; his next message releases them.
- A CronCreate job expires 7 days after creation. Recreate it with the same prompt on the first tick on or after
  `expires`, delete the old one, and update STATE.md.
- A worker's turn-end note quotes only its first 400 characters. Its RESULT block is in its `<name>.md` in your family
  folder.
- You have linked children: at the context handoff note, ask Eduardo for `/compact` instead of handing off.

## Start

1. Read `<KEY>` and its sub-tasks (`parent = <KEY>`).
2. Write STATE.md from [state.md](reference/state.md), with a row per sub-task. Write
   `side-session-notes/<own local_ id>/STATE.md` as one line pointing to it.
3. CronCreate every 15 minutes with the prompt `Run the orchestrate skill's tick for <KEY>.`; record its id and expiry.
4. When Eduardo wants continuous pickup, create an hourly scheduled task with the prompt
   `Run the orchestrate skill's pickup for <KEY>.`; record its name.
5. Run **Pickup**.

Done when every sub-task has a row, the cron is recorded, and every pickable ticket has a worker, a card, or a capacity
line in the Log.

## Resume

A new session taking over `<KEY>`: read STATE.md, set the `Orchestrator` line to your id, write the pointer in your own
family folder, SendMessage every live worker your id, and create the tick cron with the prompt from **Start**, deleting
any older tick cron for `<KEY>` that `CronList` shows.

## Pickup

A ticket is **pickable** when it is To Do, unassigned or Eduardo's, its row is `queued`, and no PR in any of the
orchestration's repos has its key in the title (`gh pr list --repo <repo> --search "<SUBKEY> in:title" --state all`).
First add a `queued` row for every To Do sub-task without one, and set each `held` row whose blocker cleared to
`queued`.

1. **Gate.** Stop with one Log line when active workers reach `Capacity` or the machine is busy (repos.md, Shared
   machine).
2. **Claim.** Take pickable tickets in rank order. On a turn that can start sessions, transition the ticket to In
   Progress first, so a concurrent pickup skips it, then start its worker with the brief in
   [briefs.md](reference/briefs.md). On any other turn, propose the same brief as a card and leave Jira as it is.
3. **Record.** Row → `working` with the worker's `local_` id; one Log line; when you are the scheduled task, SendMessage
   the orchestrator one line.

Done when every pickable ticket has a worker or a card, or the gate stopped you.

## Tick

1. For every `working`, `in-review` and `paused` row, apply [pr-lifecycle.md](reference/pr-lifecycle.md).
2. For every worker whose `<name>.md` carries a RESULT block newer than its row's `Checked`: check its `EVIDENCE` with
   one call (the PR, the named test run) before you record it. `done` without a merged PR stays `in-review`; `blocked`
   becomes `blocked` or `waiting-eduardo`; each `OPEN` line becomes a new unassigned sub-task (jira-conventions.md), a
   question you answer, or a question for Eduardo. Add one to `RESULTs since`.
3. Run **Pickup** (cards only, on a cron turn).
4. Run **Retro** when due.
5. Reply with one line per row that changed, or one line in total.

Done when every active row has this tick's `Checked` time and `Head`.

## Retro

Due when `RESULTs since` reaches 30, or 6 hours passed since the last retro and at least one RESULT came in. Follow
[retro.md](reference/retro.md).

## Close

When every row is `done`, `dropped` or `skipped`: run a final retro, delete the cron and the scheduled task, archive the
remaining workers, report the family's cost with `orchestration-telemetry` (`--root self`), and ask Eduardo whether to
move `<KEY>` itself.

## Escalate to Eduardo

A scope change, another team's decision, a PR by someone else on a ticket, a signing failure, a PR closed unmerged.
Everything else you decide, within STATE.md's Decisions.
