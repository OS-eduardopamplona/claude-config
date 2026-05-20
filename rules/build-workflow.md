# Build Workflow

- OutSystems.Model repo: in a fresh worktree or at the start of a task, ALWAYS run `dotnet build` (full solution) first — NEVER `dotnet build <specific-project>`. Plugin generators and other build-time dependencies must build first. Only build individual projects for subsequent incremental changes after the full build has succeeded.
