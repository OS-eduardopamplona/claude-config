# Worker briefs

Every brief has the same shape and stays under 2,500 characters. A brief carries **pointers, not retelling**: a local
worker loads Eduardo's global rules (signing, TDD, comments, customer data, PR conventions) and can read
`~/.claude`, so its brief names files instead of restating them.

## Local worker

`start_session`: `initiation` "user_asked" (a card on turns that can't start sessions), `context` "fresh",
`use_worktree` true, `name` `<project>-<n>` (e.g. `rdmst-5761`), `title` `<SUBKEY> <purpose>`.

```text
Orchestration: <KEY> (<URL>), orchestrator <local_ id>. Read the Rules section of ~/.claude/orchestrations/<KEY>/STATE.md.
Ticket: <SUBKEY> (<URL>): <the gap, one sentence>. First check it still reproduces on <default branch>; if not, report done with the evidence.
Where: <repo>. Follow the "<profile>" worker rules in ~/.claude/skills/orchestrate/reference/repos.md.
Read first: <the ticket; files, PRs or a sibling's findings, as pointers>.
Ruled out: <what was tried or is out of scope | nothing>.
Done when: a draft PR per the repo's template, branch and title prefixed <SUBKEY>, assigned OS-eduardopamplona; the ticket moved to In Progress when you start.
As soon as the draft PR opens: bind it (ccd_pr bind_pr) and turn on Auto-fix (set_monitor). Then handle CI, conflicts and reviews yourself; merge as the profile says.
Report: when the PR opens, when blocked, and when done, put a RESULT block at the top of your <name>.md and end your message with it:
  RESULT: done|partial|blocked
  TICKET: <SUBKEY>
  EVIDENCE: <PR URL; tests red→green by name>
  OPEN: <one line per gap or question for the orchestrator | none>
A gap outside this ticket is an OPEN line, not a fix.
Start by running `/sync`.
```

## Cloud worker and relay

Use the briefs in the `cloud-relay` skill, with these slots filled:

- **Both:** the `Orchestration:` and `Ticket:` lines above.
- **Cloud worker:** the ticket's problem and acceptance criteria in full (it can't read Jira), and the profile's worker
  rules and STATE.md's Rules inlined (it can't read `~/.claude`). `target` "cloud", the profile's environment, `name`
  `<project>-<n>-cloud`.
- **Relay:** `model` sonnet, `name` and `branch_name` `<project>-<n>-relay`, the profile's worker rules by pointer. The
  relay reports to the orchestrator as a RESULT block: `READY` with the PR opened → none yet (row `in-review`),
  `NO-CHANGE` → `done` with its evidence, `GAP` → an `OPEN` line, `BLOCKED` → `blocked`.
