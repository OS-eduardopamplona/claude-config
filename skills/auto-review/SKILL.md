---
name: auto-review
description: Eduardo's automated PR reviewer for the team's OutSystems.Model, OutSystems.ModelExtensions and OutSystems.ModelQL PRs. Args: [dry-run] [owner/repo#n ...].
disable-model-invocation: true
hooks:
  PreToolUse:
    - matcher: Bash
      hooks:
        - type: command
          command: node "C:/Users/U005017/.claude/skills/auto-review/readonly-hook.mjs"
          timeout: 10
---

# Automated PR review

You orchestrate. Each PR is reviewed by a **reviewer** subagent and checked by a **verifier** subagent; `auto-review.mjs`
selects, prepares and posts, so what reaches GitHub is decided in code, never written by hand. Everything posts under
Eduardo's account: the only GitHub writes of a run are the `post` step's, and a run approves nothing, ever.

`S` below is `C:/Users/U005017/.claude/skills/auto-review`. Run every command with absolute paths from where you are;
your own shell stays out of the review worktrees (`C:/git/ar-model`, `C:/git/ar-mx`, `C:/git/ar-mql`, and their
`-2`, `-3`… slots): the read-only hook guards them.

The run is headless: it exits when your turn ends, killing every agent and command still running. Run every command
and agent in the foreground, and end your turn only after step 5.

**No red/green** (`no-red-green` in the args): every reviewer prompt ends with "No red/green." The authors ran it.

**Dry run** (`dry-run` in the args): the whole run, with `post --dry-run`, which prints what it would post. Nothing
reaches GitHub. PRs named in the args are reviewed even when selection would skip them (`candidates --force`).

## Steps

1. `node $S/auto-review.mjs lock`. Exit 3 means another run holds it: end the run with that one line.
2. `node $S/auto-review.mjs candidates [--force <PRs from the args>]`. It prints `due` (PRs named in the args in
   their order; otherwise at most 3 a run: PRs requesting Eduardo, then the others, follow-up rounds before first ones in
   each, rounds past the last one at the end, newest first within each), `deferred` (next hour) and `skipped` with why: a head already reviewed, a draft, or a head whose only change
   since the reviewed one is a clean merge of the base, and `slots`, how many PRs are reviewed at once (3;
   `AUTO_REVIEW_SLOTS`). Nothing due → step 5.
3. The due PRs in batches of `slots`, in `due`'s order. Each batch:
   1. Each PR of the batch, one after the other: `node $S/auto-review.mjs prepare <repo>#<n> <round> <lastHead or ->
      <slot>`, the slot its position in the batch (1, 2, 3…), so no two PRs of a batch share a worktree. It prints the
      **run dir**: `pr.json`, `diff.patch`, `delta.patch` (later rounds), `threads.json`, `conversation.json`,
      `checks.txt`, `overlaps.json`. The PR's head is checked out detached in `pr.json`'s `worktree`.
   2. Reviewers: one message with an `Agent` call (general-purpose, `run_in_background: false`) per prepared PR, so they run at once and the message returns when all have ended, prompt: "Read
      `$S/reviewer.md` and follow it. Run dir: <dir>." Wait until each `<dir>/verdict.json` exists or its agent ended.
   3. Verifiers: one message with an `Agent` call (general-purpose, `run_in_background: false`) per PR that has its `verdict.json`, prompt: "Read
      `$S/verifier.md` and follow it. Run dir: <dir>." Pass `effort: "max"` on a PR whose `verdict.json` has a reply
      with `"rebuttal": true` (a rebuttal is re-checked at a higher effort). Wait until each `<dir>/verified.json`
      exists or its agent ended.
   4. Each PR with its `verified.json`, one after the other: `node $S/auto-review.mjs post <dir>` (`--dry-run` in a dry
      run). It applies the last-round rule, drops re-raised Minor/Nit and replies outside Eduardo's own threads, renders
      the fixed templates, and posts one COMMENTED review (inline findings) or one comment (nothing to anchor), each
      carrying the head marker. A round with nothing blocking also DMs Eduardo through the Slack
      workflow whose webhook URL is in `~/.claude/auto-review/slack-webhook.txt` (no file, no DM). A malformed `verified.json` fails here: send the error to that PR's verifier
      (SendMessage) to fix, then post again.
   A PR whose step fails (build, fetch, a subagent ending without its file) is reported and left for the next run; the
   other PRs go on.
4. Between PRs, nothing carries over: each subagent starts fresh from its brief.
5. `node $S/auto-review.mjs unlock`, then report one line per PR: posted (url), would post (`<dir>/post.md`), skipped
   (why) or failed (why).
