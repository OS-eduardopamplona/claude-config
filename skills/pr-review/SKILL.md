---
name: pr-review
description: Review a pull request or a local branch of OutSystems.Model, ModelExtensions or ModelQL with Eduardo's reviewer, returning findings without posting. Use for /pr-review, to self-review a branch before opening its PR, or when another flow needs a verified review. Args: [deep] <owner/repo#n | PR URL | local [path]>.
---

# PR review

Reviews one change and returns its verified findings; it never posts. The review itself runs in the `pr-reviewer`
agent (Opus, xhigh, read-only), which follows [reviewer.md](reviewer.md) and [verifier.md](verifier.md).
[CONTEXT.md](CONTEXT.md) holds the vocabulary.

`pr` below means `node C:/Users/U005017/.claude/skills/pr-review/pr-review.mjs`, run from your session's folder.

1. **Prepare.** It prints the run dir.
   - A PR: `pr prepare <PR> [<round> <lastHead|->]`. Leave out round and lastHead to review the whole PR.
   - A local branch: `pr prepare --local [<path>] [--base <branch>]`. The default path is your working directory, the
     default base the repository's default branch, and the head includes uncommitted changes to tracked files.
   - Add `--deep` for `deep`, and `--chat` unless the auto-review watcher called you. `--chat` uses the `ar-*-chat`
     worktrees, so a review you run by hand never moves a watcher's worktree.
2. **Review.** The Agent tool with `subagent_type` `pr-reviewer`, prompt `Review. Run dir: <dir>.` (plus ` Deep.`). Wait
   for its completion notification; then `pr validate <dir>/verdict.json` must print `valid`.
3. **Verify.** `pr needs-verify <dir>` prints `skip` (copy `verdict.json` to `verified.json`) or `verify`: the same agent
   with `Verify. Run dir: <dir>.`, then `pr validate <dir>/verified.json` must print `valid`.
4. **Hand back.** Called by hand: summarise `verified.json` for Eduardo, one line per finding (severity, `file:line`,
   defect) and the dropped ones in a line, and name the run dir. Called by a flow: return the run dir.

A step that fails (non-zero exit, `validate` not printing `valid`, an agent that ended without writing its file) stops
the review; report which step failed and the run dir.
