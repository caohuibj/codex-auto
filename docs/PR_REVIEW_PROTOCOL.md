# Pull Request Review Protocol

The reviewer must verify the actual repository state and PR changes independently. Implementer summaries are useful navigation aids, not evidence.

## Review Order

### 1. Contract Compliance
- Match every acceptance criterion to code and/or test evidence.
- Check for missing requirements.
- Check for scope expansion, hidden refactors, or undeclared deviations.

### 2. Functional Correctness
- Happy path.
- Error paths and edge cases.
- State transitions and lifecycle behavior.
- Frontend/backend/API contract consistency where applicable.
- Authorization, ownership, validation, and concurrency where applicable.

### 3. Architecture and Data Integrity
- Respect project boundaries and dependency direction.
- Preserve persisted-data invariants and versioning rules.
- Reject parallel or duplicate systems introduced without authorization.
- Identify migration, compatibility, security, and rollback risks.

### 4. Verification
- Inspect the tests actually added or changed.
- Check CI/status evidence when available.
- Distinguish `not run`, `not applicable`, and `passed`.
- Verify the level of testing is sufficient for the changed behavior.
- Consider regression and runtime/deployment requirements from the Project Profile.

### 5. Engineering Quality
- Maintainability and readability.
- Type/schema correctness.
- Duplication and dead code.
- Error handling and observability.
- Unnecessary abstraction or defensive engineering.
- Unrelated dependency upgrades or formatting churn.

## Allowed Final States

### APPROVED
No blocking issue remains within the Task Contract. Optional improvements must be clearly identified as non-blocking.

### CHANGES_REQUESTED
At least one blocking issue is demonstrated and can be addressed within the current task.

Use this format:

```text
BLOCKER-01
Severity: Blocking
Acceptance criterion: <AC-id or N/A>
Location: <file/path/line or component>
Issue: <precise defect>
Evidence: <code/test/runtime evidence>
Required change: <minimum required correction>
Acceptance condition: <how the reviewer will verify the fix>
```

### BLOCKED
The reviewer cannot responsibly reach approval or request a bounded code fix because required evidence, access, environment, or contract clarity is missing.

Use:

```text
BLOCKED
Reason:
Evidence:
Impact:
Required decision or missing capability:
```

## Review Discipline

- Do not approve based on confidence language such as `looks fine`.
- Do not fail a PR solely for optional style preferences.
- Do not require unrelated refactors as a condition of approval.
- Do not infer passing runtime or regression tests from successful compilation.
- Re-review changed files and affected tests after each fix cycle.
- If the implementation changes the agreed architecture, return to planning unless the contract explicitly permits the change.

## Review Summary Template

```text
Review state: APPROVED | CHANGES_REQUESTED | BLOCKED
Task: <id>
Base reviewed: <base sha>
Head reviewed: <head sha>

Contract:
- AC-01 PASS/FAIL/UNVERIFIED — evidence
- AC-02 PASS/FAIL/UNVERIFIED — evidence

Verification:
- unit: PASS/FAIL/NOT_RUN/N/A
- component: PASS/FAIL/NOT_RUN/N/A
- integration: PASS/FAIL/NOT_RUN/N/A
- E2E: PASS/FAIL/NOT_RUN/N/A
- regression: PASS/FAIL/NOT_RUN/N/A
- build/runtime: PASS/FAIL/NOT_RUN/N/A

Blocking findings:
- ...

Non-blocking findings:
- ...

Merge recommendation:
<one precise sentence>
```