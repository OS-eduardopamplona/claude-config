# Tests Must Fail Without the Change (TDD)

Every test I add or modify must be shown to fail without the production change it covers — red first, then green. A passing-anyway test is vacuous.

- Prove it before done: revert/stash the change (or toggle the feature off) and confirm the test fails; report the red→green result.
- Bug fixes: the test must reproduce the bug on un-fixed code.
- If it still passes without the change, fix the test, not the record: target the exact code path the change affects, strengthen the assertion, or delete the test.
