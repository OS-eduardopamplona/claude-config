# OutSystems.Model Repo

Applies only when working in the OutSystems.Model repository (C:\git\OutSystems.Model).

## Build
- In a fresh worktree or at the start of a task, ALWAYS run `dotnet build` (full solution) first — NEVER `dotnet build <specific-project>`. Plugin generators and other build-time dependencies must build first. Only build individual projects for subsequent incremental changes after the full build has succeeded.

## CLAUDE.md local policy
- CLAUDE.md learnings stay local for now: when creating or editing a CLAUDE.md (e.g. via the capture-learnings or capture-context skills), add its path to `.git/info/exclude` instead of committing it.
- This overrides the capture-learnings skill's commit step in this repo — report entries as "added locally" and still release the PR gate normally.
- If the team later decides to share CLAUDE.md files, remove the exclude entries and commit them through a PR.
