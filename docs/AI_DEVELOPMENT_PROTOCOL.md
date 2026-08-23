# AI Development Protocol

## Purpose

`codex-auto` defines a reusable, project-agnostic engineering governance protocol for AI-assisted software development. It separates planning and judgment from implementation and uses GitHub as the durable source of truth.

## Roles

### Product Owner (Human)
- Defines product goals, priorities, constraints, and final acceptance.
- Retains merge authority unless a project explicitly adopts a different policy.
- Resolves product ambiguities that cannot be derived from repository evidence.

### Lead / Reviewer Agent (default: Sol High)
- Reads the target repository before planning.
- Performs architecture and impact analysis.
- Produces a bounded Task Contract.
- Reviews the actual PR diff, repository state, tests, and CI evidence.
- Must not treat implementer summaries as evidence.
- Does not perform routine implementation unless a task is explicitly reassigned.

### Implementer Agent (default: Luna Max)
- Executes only the bounded Task Contract.
- Creates a feature branch, implements, tests, commits, pushes, and opens/updates a PR.
- Does not redefine architecture or expand scope without escalation.
- If the contract is insufficient or conflicts with repository reality, returns `BLOCKED` with evidence and a proposed resolution.

## Source of Truth

GitHub is the coordination layer. Durable state must be represented by repository artifacts whenever practical:

1. base branch and base SHA;
2. Task Contract / issue;
3. feature branch;
4. commits;
5. pull request;
6. CI/test evidence;
7. review decision.

Conversation memory, model summaries, and unstored assumptions are not authoritative project state.

## Workflow State Machine

```text
REQUESTED
  -> PLANNED
  -> IMPLEMENTING
  -> PR_OPEN
  -> REVIEWING
       -> APPROVED -> MERGE_READY -> HUMAN_MERGE
       -> CHANGES_REQUESTED -> IMPLEMENTING
       -> BLOCKED -> ESCALATION -> PLANNED/IMPLEMENTING
```

A state transition must be supported by repository evidence. `APPROVED` means no blocking issue remains within the agreed scope; it does not mean every optional improvement has been implemented.

## Planning Gate

Before implementation, the Lead must inspect the target repository and produce a Task Contract containing at least:
- Task ID;
- base ref and SHA;
- objective;
- in-scope and out-of-scope work;
- architecture constraints;
- implementation requirements;
- acceptance criteria;
- required verification;
- expected deliverables;
- escalation conditions.

Planning should minimize speculative refactoring and avoid unrelated cleanup.

## Implementation Gate

The Implementer must:
1. branch from the contract base;
2. implement the minimum change satisfying the contract;
3. add or update appropriate tests;
4. run applicable verification;
5. document deviations explicitly;
6. commit and push only to the feature branch;
7. open or update a PR using the repository PR template.

The Implementer must not directly push to protected integration or production branches under the default policy.

## Review Gate

The Lead/Reviewer re-reads the PR independently. Review must cover:
1. Contract Compliance;
2. Functional Correctness;
3. Architecture and data-flow integrity;
4. Verification evidence and regression risk;
5. Engineering quality, including unnecessary complexity.

Review outcome is exactly one of:
- `APPROVED`;
- `CHANGES_REQUESTED`;
- `BLOCKED`.

Blocking findings must include severity, location, evidence, required change, and acceptance condition.

## Evidence Policy

The following are evidence, in descending practical value:
- actual code/diff;
- deterministic test and CI output;
- runtime/reproduction evidence;
- versioned repository documentation.

The following are not sufficient by themselves:
- an agent saying a test passed;
- a previous planning assumption;
- a generated completion summary;
- an unverified statement that there is no regression.

## Escalation Rules

Escalate rather than silently expanding scope when any of the following occurs:
- required architecture change not authorized by the contract;
- incompatible existing implementation discovered;
- security/authentication/authorization boundary changes;
- destructive or ambiguous database migration;
- public API or persisted data contract changes outside scope;
- missing access, environment, test fixture, or external dependency;
- acceptance criteria conflict with repository reality.

The escalation response must include `Reason`, `Evidence`, `Impact`, and `Proposed resolution`.

## Human Merge Gate

Default policy: AI agents may plan, implement, test, push feature branches, open PRs, and review. Final merge remains a human action.

Projects may strengthen this policy with branch protection, required CI, required review, CODEOWNERS, deployment gates, or environment approvals.

## Project-Specific Profiles

This repository is intentionally project-agnostic. Each target project supplies its own constraints through a Project Profile, such as:
- repository and integration branch;
- architecture boundaries;
- protected domains;
- required test layers;
- data persistence rules;
- deployment/runtime checks;
- prohibited refactors;
- domain-specific Definition of Done.

Project-specific rules override generic defaults only where the profile states the override explicitly.