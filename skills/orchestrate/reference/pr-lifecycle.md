# PR lifecycle

Apply to each `working`, `in-review` and `paused` row on every tick. The row's repo profile in
[repos.md](repos.md) says how CI, reruns and merging work there.

## Read

- **No PR yet:** `gh pr list --repo <repo> --search "<SUBKEY> in:title" --state all` in each of the orchestration's
  repos. A PR by OS-eduardopamplona is the worker's: fill `PR`, row → `in-review`. A PR by anyone else means the
  ticket is theirs: tell the worker to stop, row → `skipped`, escalate.
- **PR:** `gh pr view <n> --repo <repo> --json state,isDraft,headRefOid,headRefName,mergeable,autoMergeRequest,reviewDecision,reviews`,
  `gh pr checks <n> --repo <repo>`, and unresolved review threads (`gh api graphql`, `pullRequest.reviewThreads` with
  `isResolved`, first comment's author and body).
- **Worker:** `get_session` with its full `local_` id.

Skip the row when `headRefOid` equals `Head`, it isn't CONFLICTING, and no review thread or CHANGES_REQUESTED review is
newer than `Checked`. Pending checks skip CI only.

## React

| PR state | Reaction |
|---|---|
| Opened | the worker binds it and turns on Auto-fix; if not, SendMessage it to |
| Green | `gh pr ready` if draft; ticket → In Code Review; one PR-link comment per ticket; merge per the profile |
| Red, test failure | failing tests and their first error lines → the worker, verbatim |
| Red, infra (agent lost, timeout, no test failure) | rerun per the profile yourself; `Head` → `—` |
| Conflicting | the worker merges the default branch, resolves, runs the targeted tests, pushes |
| Review | an unresolved thread or a person's CHANGES_REQUESTED → the worker, verbatim; it fixes or replies with the reason, pushes, resolves the thread |
| Merged | ticket → Done; archive the worker; row → `done` |
| Closed unmerged | row → `blocked`; escalate; keep the worker |

A cloud row's reactions go to its relay, which forwards them. Send reactions to a `paused` row's worker only once the
pause lifts.

## Stuck worker

A worker is **stuck** when it is "needs the user", or working with no activity for 45 minutes, or one tick after a
reaction brought no new head. Read its transcript's tail, then do the reaction yourself:

1. `git worktree add --detach <profile's short path>-orch origin/<headRefName>`.
2. Full build, the targeted tests, a signed commit. If signing fails, leave it staged, escalate, and stop.
3. `git push origin HEAD:<headRefName>`, reply on each thread you addressed, `git worktree remove`.
4. Notes: "done by orchestrator, <worker> stuck"; one Log line.

## Record

Set `Head` and `Checked` on every row you read, and keep `Notes` to the current picture.
