# OutSystems.Model Repo

Applies only when working in the OutSystems.Model repository (C:\git\OutSystems.Model).

## Build
- In a fresh worktree or at the start of a task, ALWAYS run `dotnet build` (full solution) first — NEVER `dotnet build <specific-project>`. Plugin generators and other build-time dependencies must build first. Only build individual projects for subsequent incremental changes after the full build has succeeded.
- Stale .NET test hosts lock bin DLLs after `dotnet test` — full rebuilds fail with MSB3027 "file locked by .NET Host (PID)". Fix: `taskkill //PID <pid> //F`, rebuild. Recurs regularly.
- LSP/IDE diagnostics are unreliable in this repo (`extern alias V1` breaks resolution; mass phantom CS0012/CS0234/CS0246 on every edit). `dotnet build` output is the only arbiter.
