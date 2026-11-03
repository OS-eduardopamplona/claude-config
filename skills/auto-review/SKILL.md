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
your own shell stays out of the review worktrees (`C:/git/ar-model`, `C:/git/ar-mx`, `C:/git/ar-mql`): the read-only hook guards them.

**Dry run** (`dry-run` in the args): the whole run, with `post --dry-run`, which prints what it would post. Nothing
reaches GitHub. PRs named in the args are reviewed even when selection would skip them (`candidates --force`).

## Steps

1. `node $S/auto-review.mjs lock`. Exit 3 means another run holds it: end the run with that one line.
2. `node $S/auto-review.mjs candidates [--force <PRs from the args>]`. It prints `due` (at most 3 a run, follow-up rounds first, then PRs
   requesting Eduardo, then newest first), `deferred` (next hour) and `skipped` with why: a head already reviewed, a draft, or a head whose only change
   since the reviewed one is a clean merge of the base. Nothing due → step 5.
3. Each due PR, one at a time:
   1. `node $S/auto-review.mjs prepare <repo>#<n> <round> <lastHead or ->` prints the **run dir**: `pr.json`,
      `diff.patch`, `delta.patch` (later rounds), `threads.json`, `conversation.json`, `checks.txt`, `overlaps.json`.
      The PR's head is checked out detached in `pr.json`'s `worktree`.
   2. Reviewer: `Agent` (general-purpose), prompt: "Read `$S/reviewer.md` and follow it. Run dir: <dir>." Done when
      `<dir>/verdict.json` exists.
   3. Verifier: `Agent` (general-purpose), prompt: "Read `$S/verifier.md` and follow it. Run dir: <dir>." Pass
      `effort: "max"` when `verdict.json` has a reply with `"rebuttal": true` (a rebuttal is re-checked at a higher
      effort). Done when `<dir>/verified.json` exists.
   4. `node $S/auto-review.mjs post <dir>` (`--dry-run` in a dry run). It applies the last-round rule, drops re-raised
      Minor/Nit and replies outside Eduardo's own threads, renders the fixed templates, and posts one COMMENTED review
      (inline findings) or one comment (nothing to anchor), each carrying the head marker. A malformed `verified.json`
      fails here: send the error to the verifier (SendMessage) to fix, then post again.
   A PR whose step fails (build, fetch, a subagent ending without its file) is reported and left for the next run; the
   next PR goes on.
4. Between PRs, nothing carries over: each subagent starts fresh from its brief.
5. `node $S/auto-review.mjs unlock`, then report one line per PR: posted (url), would post (`<dir>/post.md`), skipped
   (why) or failed (why).
