# PR review

Eduardo's automated code review of teammates' pull requests, and the review skill it shares with other callers.

## Language

**Review skill**:
The reusable capability that examines a PR or a local branch and produces findings; it never posts.
_Avoid_: reviewer prompt, auto-review

**Watcher**:
The scheduled pass that decides which PRs are due and hands each to the review skill and the publisher.
_Avoid_: orchestrator, runner, auto-reviewer

**Pass**:
One run of the watcher, reviewing the PRs due at that moment one at a time.
_Avoid_: run, batch

**Due**:
A PR that requests Eduardo by name and has had no round since its latest request.

**Reviewer agent**:
The read-only Opus agent that performs a review or a verification for the review skill.
_Avoid_: subagent, reviewer session

**Publisher**:
The step that turns a verdict into a GitHub review, thread replies and a Slack notification.
_Avoid_: poster

**Finding**:
One defect with a severity, a confidence and a concrete scenario.
_Avoid_: comment, issue

**Verdict**:
The review skill's output for one round: its findings, its replies to its own threads, and notes.

**Round**:
One review of one PR head, answering one review request.
_Avoid_: pass, iteration

**Re-request**:
The PR author asking Eduardo for review again after a round; the only thing that makes a follow-up round due.
_Avoid_: new commits, push

**All-clear**:
A round with no blocking findings, posted as a review so the author can re-request later.
