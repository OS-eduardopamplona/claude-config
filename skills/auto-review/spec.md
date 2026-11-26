# Automated PR review: spec

Derived from Ruben's, Francisco's and Nuno's reviewers and the RDMST-5044 loop reviewer. Vocabulary:
`skills/pr-review/CONTEXT.md`. Redesigned Nov 26 2026 into three parts with one job each.

## Parts
- **Review skill** (`skills/pr-review/`): prepares a run, reviews, verifies, writes `verified.json`. Works on a PR or a
  local branch and never posts. Entry `/pr-review`; other flows reuse its `SKILL.md` steps.
- **`pr-reviewer` agent** (`agents/pr-reviewer.md`): Opus at xhigh effort. Reviews with `reviewer.md`, verifies with
  `verifier.md`. Its own PreToolUse hook (`readonly-hook.mjs`) refuses git writes, GitHub writes, `prepare` and the
  watcher's posting and lock commands, wherever it runs.
- **Watcher and publisher** (`skills/auto-review/`): picks due PRs, runs the review skill for each, posts with `ar post`,
  notifies Slack. Entries: the scheduled task and `/review-now`.

## Trigger
- The Claude desktop scheduled task `auto-review`, weekdays hourly at :40 from 08:40 to 19:40 Lisbon
  (`40 8-19 * * 1-5`), on Sonnet with bypass permissions, which the reviewer agent inherits.
- A pass reviews due PRs **one at a time**, at most 4, then exits. The lock is `lock.json` (token + time), renewed
  before each PR, lapsing 3 hours after its last renewal. A pass that finds it held exits.
- **Due**: an open, non-draft PR in Model, ModelExtensions or ModelQL, not by Eduardo or a bot, updated in the last 7
  days, that requests Eduardo by name (`user-review-requested:@me`; a pick from model-team's auto-assignment counts,
  a model-team request that picked others does not), and either has no round yet or has a `review_requested` event for
  Eduardo newer than the request its last round answered. Pushes alone never make a PR due; a re-request does, on a new
  head or the same one (how a rebuttal gets its answer). Re-requests after Eduardo's own manual review count too.
- Order: follow-ups, then first rounds.
- `/review-now <PRs>` runs a pass for those PRs whether or not they are due. With a pass in progress they go to
  `requested.txt`, which that pass takes next; `unlock` refuses while the queue is not empty.
- Every post carries `<!-- auto-review head=<sha> round=<n> requested=<time> -->`; `requested` is the re-request the
  round answered (older posts without it count from their post time).

## Workspace
- Detached worktrees `C:/git/ar-model`, `ar-mx`, `ar-mql` for the watcher, `ar-*-chat` for `/pr-review` by hand.
- The run dir `~/.claude/pr-review/runs/<repo>-<n>-<sha>-r<round>/` (local branch: `<repo>-local-<branch>-<sha>/`)
  holds `pr.json`, `diff.patch`, `delta.patch`, `threads.json`, `conversation.json`, `checks.txt`, `base.patch`
  (the base's changes to the PR's files since the merge base; `baseConflicts` lists files conflicting with its tip) and
  `overlaps.json` (merge-tree against other open PRs).
- A local branch's head is `git stash create` when the working tree has uncommitted changes to tracked files, else
  `HEAD`; the source must be the clone or one of its worktrees.

## What it reviews
- Round 1: the whole diff. Later rounds: the delta since the last reviewed head plus every open thread, and the whole PR
  still holding together.
- **CI is the build and test oracle**; `deep` adds a build, red/green and probe tests.
- Checklist: CI; tests reach the change; merges and base drift; every repo rule including the PR body; consumer impact;
  tooling. Then the code read: completeness, left-out and edge input, failure paths, test code, purpose.
- Nov 2026 comparison with teammates' reviewers (150 PRs, ~190 missed defects) shaped the checklist and xhigh effort.

## Verification
- `needs-verify`: a rebuttal or a Blocker/Major sends the verdict to the same agent in Verify mode, at xhigh; otherwise
  `verdict.json` is copied to `verified.json`.

## Findings
- Confidence: CONFIRMED (shown by the code, a CI result or, in `deep`, a probe) or PLAUSIBLE (would block if true).
- Severity: 🔴 Blocker · 🟠 Major (both block) · 🟡 Minor · ⚪ Nit (author decides).
- Inline template: `<emoji> **<Severity>** · <Category> · <CONFIRMED|PLAUSIBLE>` / defect / **Scenario** / **Fix** /
  `— Automated review by Claude`.

## Publishing
- Every round posts all its findings, every severity; there is no last round.
- A Minor or Nit within 3 lines of an own thread is never raised again; a rejected rebuttal gets one reply, never two.
- Replies only in its own threads: `fixed` and `accepted` resolve the thread.
- Every round is one COMMENTED review, all-clears included, so the author can re-request. Never approves.
- A round with findings, or with a thread still open or rebutted, ends with: "Once you've addressed these, or replied in
  a thread where you disagree, re-request my review."
- An all-clear tags @OS-eduardopamplona for the human pass.

## Slack
- On an all-clear and on a failed pass (throttled 4h per text): `ar` POSTs `repo`, `pr`, `title`, `url`, `summary` to
  the "Auto-reviewer" workflow's webhook in `~/.claude/auto-review/slack-webhook.txt` (never committed). With no file
  or a failed POST it prints `DM: <text>` and the session sends it to Eduardo's DM through the Slack connector.

## Removed
Before Nov 19 2026: parallel batches, the fetch mutex, local builds by default, the always-on verifier, `run.sh` and
headless `claude -p`, the pid lock. On Nov 26 2026: the last-round filter, reviews on pushes without a re-request, the
`reviewed-by`/`commenter` searches, max-effort verification, issue-comment all-clears, the global read-only hook.
