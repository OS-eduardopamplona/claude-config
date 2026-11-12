# Automated PR reviewer: lean spec

Derived from Ruben's, Francisco's and Nuno's reviewers and the RDMST-5044 loop reviewer (raw data:
`scratchpad/ruben/all.jsonl`). The lean rewrite (Nov 2026) cuts the machine cost: one PR at a time, no local build by
default, one Opus session per PR.

## Trigger
- Scheduled run on weekdays, hourly at :40 from 08:40 to 19:40 Lisbon (`40 8-19 * * 1-5`).
- A run reviews due PRs **one at a time**, at most 4 per run, then exits. A run that finds the lock held exits at once.
  The lock is a single `lock.json` (pid + start time); a dead pid's lock lapses.
- Picks open, non-draft PRs in OutSystems.Model, OutSystems.ModelExtensions and OutSystems.ModelQL not authored by
  Eduardo or a bot, updated in the last 7 days. Order: PRs requesting Eduardo (follow-ups, then first rounds), other
  follow-ups, other first rounds, rounds past the last one.
- On demand: `/review-now <PRs>`. With no run in progress it reviews them at once, one after the other. With a run in
  progress it appends them to `requested.txt`, which that run takes next, ahead of its own queue and outside its
  per-run cap.
- Stateless idempotency: hidden `<!-- auto-review head=<full sha> round=<n> -->` in every post. Skip a head already
  marked, and a new head whose only change is a clean merge of the base or the same patch-id. A named PR on a marked
  head is reviewed as the next round (how a rebuttal without a new commit gets its answer).

## Workspace
- One detached worktree per repo (`C:/git/ar-model`, `ar-mx`, `ar-mql`), reused across runs. No build, so no bin/obj,
  no GitVersion shortening, no `clean -fdx` exceptions.
- Fetch under no mutex: runs never overlap.
- The run dir `runs/<repo>-<n>-<sha>-r<round>/` holds `pr.json`, `diff.patch`, `delta.patch`, `threads.json`,
  `conversation.json`, `checks.txt` (CI status and failed test names) and `overlaps.json` (`git merge-tree` against
  the other open PRs, so the reviewer notes semantic conflicts).

## What it reviews
- Round 1: the whole diff. Later rounds: the delta since the last reviewed head plus the status of every open earlier
  finding, other reviewers' and bots' threads included.
- **CI is the build and test oracle.** The reviewer reads the checks; a red check on the PR's own change is reported,
  a red check it can tie to master is not.
- Checklist, by reading the code:
  1. Every new or changed test exercises the changed production path and would fail without it. A test that cannot
     reach the change is a CONFIRMED finding; one whose assertion may be too weak is PLAUSIBLE.
  2. Conflict resolutions in merge commits touching the PR's own files.
  3. Repo rules: `CLAUDE.md`, `.claude/rules`, feature-toggle safety in Model (toggle off == master, real uuid).
  4. Consumer impact for public API changes (`consumer-impact` skill).
- No local build, no red/green, no probe tests in the scheduled run. `/review-now deep <PR>` restores them for one PR:
  full build, red/green on the changed tests, probe tests.
- Read-only: the hook blocks git writes, `gh` posting, GraphQL mutations, and `post`/`lock`/`unlock` from inside the
  worktrees.

## Agents
- One Opus session per PR does the review and writes `verdict.json`.
- A verifier session (`--effort max` on a rebuttal) runs **only when the verdict holds a blocking finding** (Blocker/Major) or a rebuttal; it drops
  what does not survive, writing `verified.json`. Otherwise `verdict.json` is posted as is.

## Findings
- Confidence: CONFIRMED (shown by the code, a CI result or, in `deep`, a probe) or PLAUSIBLE (would block if true).
- Severity legend every time: 🔴 Blocker · 🟠 Major (both block) · 🟡 Minor · ⚪ Nit (author decides).
- Inline template: `<emoji> **<Severity>** · <Category> · <CONFIRMED|PLAUSIBLE>` / defect in one sentence /
  **Scenario:** input → wrong outcome, with file:line / **Fix:** one line, naming the test to add /
  `— Automated review by Claude`.

## Convergence
- Round 3 is the last: only CONFIRMED blocking findings on delta lines are posted; PLAUSIBLE ones go in one "Left to
  the human reviewer" note.
- A Minor or Nit is never re-raised once posted.

## Replies
- Only in its own threads: "Fixed at <sha>" or an accepted rebuttal resolves the thread; "Still open at <sha>: why";
  a rejected rebuttal gets one reply with the evidence, never a second. Human decisions ("Eduardo's call: …") are final.

## Outcome
- The model returns a JSON verdict; `post` decides in code what to post, and refuses a round already posted.
- Blocking findings: one COMMENTED review with inline comments and a summary line.
- Nothing blocking: one comment "no blocking issues at <sha>", resolved threads listed, @OS-eduardopamplona tagged, and
  a Slack DM. Never approves.
- A failed run DMs Eduardo on Slack (throttled 4h) and stops the run.

## Removed from the previous design
Parallel batches (`MAX_PER_RUN` slots, `claims.json`, `tried-<pid>.txt`, slot worktrees `ar-*-2..4`), the fetch mutex,
local builds and red/green by default, the always-on verifier.
Cleanup on rollout: delete worktrees `ar-model-2..4`, `ar-mx-2..3`, `ar-r4176` (~25 GB) and old `runs/`.
