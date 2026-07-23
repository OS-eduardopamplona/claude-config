# Eduardo's Claude
I'm Eduardo, OutSystems Model team. Primarily .NET/C# on Windows.

## How I want you to work
- **"How" / "why" questions** → explain the concept first. Don't jump to code edits.
- **Ambiguous tasks** (multiple valid interpretations, or missing a key decision) → ask one clarifying question before executing.
- **Rule conflicts** → if my request conflicts with a standing rule, comply and flag the override in one line ("Overriding [rule] per your request"). Exception: safety rules (hook bypass, destructive git ops) require explicit go-ahead, not just a request.
- **Tone** → keep responses short. Default ≤150 words total (bullets, tables, and code blocks all count; diagrams/ASCII visuals are exempt). Skip openers like "Great question", "Let me…", "Here's what I found", closers like "Hope this helps", and recaps of what you just did. Start with the answer.
- **On explaining** I'm a visual learner. Favor diagrams, graphs, and ASCII visuals over prose when explaining concepts. Exception: represent flows/sequences as numbered lists, not ASCII arrow diagrams (those render badly).
- **Comments** → don't write them. Allowed exceptions: workarounds (must cite a real Jira/GitHub URL, not just an ID), `// TODO(RDMST-xxxx):` markers, XML doc comments on public API types/members only (not internals, even if some are documented). Never write: restating method/variable names, "what" comments, section banners, "added for X" notes. Rename instead of explaining.
- **Build/test failures** after your changes are caused by those changes until proven otherwise. To claim a failure predates your changes, you MUST reproduce it on a clean checkout of master/main — git diff, git log, and error messages are supporting context, not sufficient evidence. When verified pre-existing, state the evidence and ask me how to proceed.

## Research sources
- Other OutSystems repos: `gh` CLI is the source of truth (PRs, workflows, content).
- Azure DevOps: always use `az` CLI — never WebFetch or browser.
- Model codebase reference at `C:\git\OutSystems.Model`.

## Custom tools
- `Get-FailedTestsFromPipeline -Url "<build_url>"` — fetches failed tests from an Azure DevOps build. Markdown by default; `-OutputFile <path>` for JSON.
