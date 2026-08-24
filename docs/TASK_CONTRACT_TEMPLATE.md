# Task Contract Template

Use one Task Contract per bounded implementation unit.

```text
TASK ID
<stable identifier>

TITLE
<concise implementation title>

TARGET REPOSITORY
<owner/repo>

BASE
<branch> @ <commit SHA>

OBJECTIVE
<observable product or engineering outcome>

IN SCOPE
- ...

OUT OF SCOPE
- ...

PROJECT PROFILE
<path or version of project-specific constraints>

ARCHITECTURE CONSTRAINTS
- ...

IMPLEMENTATION REQUIREMENTS
1. ...
2. ...

ACCEPTANCE CRITERIA
AC-01 <testable condition>
AC-02 <testable condition>

REQUIRED VERIFICATION
- unit: required / not applicable
- component: required / not applicable
- API/integration: required / not applicable
- E2E: required / not applicable
- regression: required / not applicable
- build/type/lint: required / not applicable
- runtime/container/deployment: required / not applicable

EXPECTED DELIVERABLES
- feature branch
- implementation commits
- tests and evidence
- committed feature branch and change evidence
- deviation/risk disclosure

ESCALATION CONDITIONS
Return BLOCKED instead of guessing when:
- implementation requires a contract-external architecture change;
- persisted schema or public API must change outside scope;
- required evidence cannot be obtained;
- repository state contradicts an acceptance criterion;
- access or environment prevents verification.

ESCALATION FORMAT
Reason:
Evidence:
Impact:
Proposed resolution:
```

## Contract Rules

- The base SHA freezes the planning reference point. If the target branch moves materially before implementation, the implementer must report it.
- Acceptance criteria must be observable and reviewable; avoid statements such as `works correctly` without a verification condition.
- Out-of-scope items are explicit guardrails, not suggestions.
- `not applicable` verification layers should include a short reason in the PR.
- A contract may reference project-specific definitions of done instead of duplicating them.
