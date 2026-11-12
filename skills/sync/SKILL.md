---
name: sync
description: >-
  Sync with the sibling sessions of this session family: read STATE.md and the siblings' notes, check their PRs, and report what changed.
  Use when asked to sync, or to get updated on or catch up with what another session did.
argument-hint: "[sibling name or local_ id]"
---

# Sync

The layout of the family files is in the `session-family` rule.

1. **Folder.** Use the "Shared notes folder" your prompt names. If you are a parent, also use `side-session-notes/<own local_ id>/`.
2. **Read.** Read `STATE.md` (when it points to an orchestration's state file, read that file instead) and every `<name>.md` except your own, along with each file's modified time (`ls -l --time-style=+%FT%T`). With an argument, read only that sibling's file and its `STATE.md` row.
3. **Live state.**
   - Run `list_sessions {"linked": true}` to see whether each sibling is running, idle or archived.
   - For every PR the files list, run `gh pr view <n> --repo <owner/repo> --json state,isDraft,reviewDecision,reviews,updatedAt,statusCheckRollup`, and count the checks as pass/fail/pending.
4. **Report.** Report changes since this conversation's last `Synced:` stamp: newer files, newer PR activity, changed session state. If there is no stamp yet, report the current state. Write one line per sibling: what changed and whether it touches your task. Then list open questions addressed to you or to Eduardo. End with `Synced: <ISO time>`.
5. **Parent only.** Bring `STATE.md` up to date with what you found.

The sync is done when the report has accounted for every sibling file and every listed PR, including a "no change" line for each one that did not change.
