---
paths:
  - "**/tests/**"
  - "**/*.Tests/**"
  - "**/*Tests.cs"
  - "**/*.test.*"
  - "**/test_*.py"
---

# Test Placement: Reuse Existing Test Classes

Default to adding tests to an existing test class. A new test class is the exception and needs a stated reason.

## Required before writing any test
1. Search for existing coverage of the type/method under test — by production type name, by method name, and by the feature/domain keyword (e.g. `grep -r "MyType" tests/`).
2. Check the mirrored test project/folder for the production file's path, and list its test classes.
3. Pick the class whose subject matches (same production type, same feature area) and add the test there, following its existing setup/helpers/naming.

## Only create a new class when
- No test class covers the production type or feature area, or
- The subject is genuinely new production code, or
- The existing class's fixture/setup cannot express the new scenario (e.g. different `[SetUp]` state, different mocks) — say so in one line.

Class size alone is not a reason to split. "Cleaner separation" is not a reason.

## Report it
When adding tests, state where they went and why in one line:
- `Added to FooCommandTests (covers IFooCommand)` — or —
- `New class BarValidatorTests: no existing coverage for BarValidator`

Never silently create a parallel class (`FooTests2`, `FooExtraTests`, `FooNewBehaviorTests`) next to one that already covers the same subject.
