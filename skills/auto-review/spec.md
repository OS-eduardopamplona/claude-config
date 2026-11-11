# Automated PR reviewer: combined spec

Derived from Ruben's (825 posts, 193 PRs), Francisco's review routine (115 reviews) and the RDMST-5044 loop reviewer
(`tools/roundtrip/loop/src/review.mjs`, `prompts/reviewer.md` on `origin/RDMST-5044-loop-map`), and Nuno's (101 posts).
Raw data: `scratchpad/ruben/all.jsonl`.

## Trigger
- Hourly scheduled run on weekdays. Picks every open, non-draft PR in the team's repos (OutSystems.Model,
  OutSystems.ModelExtensions, OutSystems.ModelQL) not authored by Eduardo, PRs requesting him first, follow-up rounds before first ones, rounds past the last one at
  the end; batches of 3 back to back until nothing is due, a run that starts meanwhile exiting on the lock. (Ruben: review-requested, hourly at :20. Francisco: every open PR,
  too noisy. Nuno: batch over open PRs.)
- On demand: `/review-now <PRs>` (`now.sh`) starts named PRs at once, beside a running batch, on spare worktree slots.
  A claims file (PR, pid, slot) keeps two runs off the same PR and the same worktree; a dead pid's claims lapse.
- Stateless idempotency: hidden `<!-- auto-review head=<full sha> round=<n> -->` in every post. Skip a head already
  marked. (Francisco)
- Skip a new head whose only change since the last reviewed head is a clean merge of the base (no conflict
  resolutions touching the PR's own files); post nothing. (Fixes Ruben's 11-round PR 1462 noise.)

## What it reviews
- Round 1: the whole diff. Later rounds: only the delta since the last reviewed head plus the status of every open
  earlier finding, including other reviewers' and bots' threads. (Ruben, Nuno, loop)
- Checklist before the code read (loop + Nuno):
  1. Every new or changed test fails without the production change (revert non-test files in a worktree) and passes at
     head. A vacuous test is a finding.
  3. Conflict resolutions in merges are checked; semantic conflicts with other open PRs (`git merge-tree`) noted.
  4. Repo rules: `CLAUDE.md`, `.claude/rules`, feature-toggle safety in Model (toggle off == master, real uuid).
  5. Consumer impact for public API changes (`consumer-impact` skill).
- Runs in its own detached worktree, read-only: a hook blocks push, commit, merge, approve. (loop)

## Findings
- Confidence: CONFIRMED (reproduced by a probe test or shown by the code) or PLAUSIBLE (would block if true, not
  verified). A verify pass drops findings that don't survive before posting. (loop, Nuno)
- Severity, fixed legend every time: 🔴 Blocker · 🟠 Major (both block) · 🟡 Minor · ⚪ Nit (author decides). (Ruben)
- Format per inline comment (fixed template, no drift):
  `<emoji> **<Severity>** · <Category> · <CONFIRMED|PLAUSIBLE>` / defect in one sentence / **Scenario:** concrete input
  → wrong outcome, with file:line / **Fix:** one line, naming the test to add / `— Automated review by Claude`.
  (Ruben format, Francisco's scenario-first style)

## Convergence
- Round 3 onwards (last-round rule): only CONFIRMED Blocker/Major findings on changed lines are posted; PLAUSIBLE ones
  go in one "Left to the human reviewer" note; nothing new on unchanged lines. (loop question 30, Ruben)
- Minor/Nit never re-raised once posted.

## Replies
- Reply in-thread only on its own findings: "Fixed at <sha>" (then resolve the thread), "Still open at <sha>: why",
  corrections, retractions of a wrong all-clear. (Ruben)
- An author's rebuttal is re-checked at higher effort; accepted → resolve with one line, rejected → one reply with the
  evidence, never a second argument. Human decisions ("Eduardo's call: …") are final. (loop, Nuno)

## Outcome
- Model returns a JSON verdict; the script decides in code what to post. (loop)
- Blocking findings → one COMMENTED review with inline comments and a summary line.
- Nothing blocking → one comment "no blocking issues at <sha>", list of resolved threads, tag @OS-eduardopamplona for
  the human pass. Never approves under Eduardo's account. (Ruben; Nuno's agent-approvals got dismissed)
