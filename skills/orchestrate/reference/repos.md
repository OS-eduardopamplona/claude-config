# Repo profiles

## Jira RDMST

cloudId `3755dbe1-fa22-4c37-956e-59bea84af9cf`. Transitions: To Do 11, In Progress 31, Discarded 41, Done 51, In Code
Review 61. Eduardo's account `712020:fa0241f3-5314-4e06-8cf8-dd975bf1bb12`.

## Shared machine

- Workers share one machine: stop a process by its PID only (a worker that killed by image name took down every
  dotnet process).
- **Busy** for pickup: free RAM under 8 GB (`(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1MB`), or,
  when STATE.md's Rules allow one build at a time, a `dotnet.exe` running ` build`, ` test` or `vstest.console`.

## OutSystems.ModelExtensions

- **Worker rules:**
  - Work in a short worktree `C:\git\me-<n>` from `C:\git\OutSystems.ModelExtensions`; the app's worktree path is too
    long for GitVersion (LibGit2 "path too long").
  - Full `dotnet build` first.
  - Before each push: `dotnet format whitespace . --folder --exclude '**/Results/**' localpackages '**/bin/**' '**/obj/**'`.
  - Never commit `GitVersion.yml`.
- **CI:** Azure pipeline, project ArtifactRepository, definition 432. Green when every Azure check passes, including
  `OutSystems.ModelExtensions`. Failed tasks: `az devops invoke --organization https://dev.azure.com/OutSystemsRD --area build --resource timeline --route-parameters project=ArtifactRepository buildId=<id> --api-version 7.1`,
  then `--resource logs ... logId=<id>`. Infra rerun:
  `az pipelines build queue --organization https://dev.azure.com/OutSystemsRD --project ArtifactRepository --definition-id 432 --branch <headRefName>`.
- **Merge:** the worker turns on auto-merge once green.
- **Cloud:** environment `ts-agent-p1`. Restore needs the private NuGet feed, the `@outsystems` npm packages and Node
  22.18+; a restore failure means the ticket goes to a local worker.

## OutSystems.Model

- **Worker rules:** work in a short worktree `C:\git\om-<n>` from `C:\git\OutSystems.Model`; the
  `outsystems-model` rule applies.
- **CI:** GitHub checks; green when all pass. Infra rerun: `gh run rerun <run-id> --failed`.
- **Merge:** auto-merge only with Eduardo's OK, unless a Decision allows it.
- **Release:** consumers see a change once a Model release carrying it is on the feed (pipeline 298's tag run); hold
  dependent tickets until then.

## Owner-merged (rd-ai-agents-evals, rd-ai-agent-lib)

- Track the PR by the URL the worker reports. Code owners merge: never turn on auto-merge.
