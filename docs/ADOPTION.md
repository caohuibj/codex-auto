# Adopting codex-auto in Another Project

`codex-auto` remains the canonical home of generic agent roles, task contracts, review rules, and
runtime implementation. Target repositories keep a generated repo-scoped skill, a thin launcher,
project-specific configuration, and optionally thin GitHub templates/workflows.

## Recommended Consumer Layout

In the target repository:

```text
.agents/skills/codex-auto/
├── SKILL.md
└── agents/openai.yaml

.codex/
├── config.toml
└── agents/luna-implementer.toml

.codex-auto/
├── bin/codex-auto
├── project.yml
├── orchestrator.yml
├── .env.example
└── runtime/               # ignored project-local environment
```

This layout is created by `codex-auto init-project`. The repo-scoped skill makes the workflow
discoverable only inside the consumer repository, while the project-local runtime and Codex config
avoid modifying the system Python, user skill directory, or user-level Codex configuration. In App
mode the project config fixes the primary Sol route and registers the named Luna worker; route
mismatches fail closed.

See [`PROJECT_LOCAL_INSTALLATION.md`](PROJECT_LOCAL_INSTALLATION.md) for complete installation,
ChatGPT desktop local-project setup, invocation, update, and removal instructions.

## Minimal `project.yml`

```yaml
protocol:
  repository: caohuibj/codex-auto
  version: v1

project:
  repository: owner/project
  integration_branch: dev
  production_branch: main

workflow:
  human_merge_required: true
  feature_branch_pattern: "feature/*"

architecture:
  protected_boundaries: []
  prohibited_changes: []

verification:
  required:
    - lint
    - typecheck
    - unit
  conditional: []
  regression_scope: []

runtime:
  required_environments: []

quality:
  avoid:
    - unrelated refactor
    - unnecessary abstraction

escalation:
  always_escalate:
    - auth/security boundary changes
    - destructive data migration
    - public API break
```

Use `docs/PROJECT_PROFILE_TEMPLATE.md` when more detail is required.

## Execution Sequence

### 1. Product Request
The human states the goal in the target-project context.

### 2. Sol Planning
Sol reads:
1. the target repository and current branch/SHA;
2. `.codex-auto/project.yml`;
3. the pinned `codex-auto` protocol version;
4. relevant target-project documentation and code.

Sol then creates a bounded Task Contract.

### 3. Luna Implementation
Luna reads the same project profile and Task Contract, creates a feature branch, implements, tests, pushes, and opens a PR.

### 4. Sol Independent Review
Sol re-reads the actual PR/diff/tests/CI and returns `APPROVED`, `CHANGES_REQUESTED`, or `BLOCKED`.

### 5. Human Merge
The human merges only after required repository gates are satisfied.

## Protocol Versioning

Consumer projects should pin a released protocol version rather than implicitly following `main` once releases exist.

Recommended lifecycle:

```text
codex-auto main
  -> protocol changes via PR
  -> tag/release v1.x
  -> consumer project updates its pinned version deliberately
```

A protocol upgrade should not silently change an in-progress Task Contract. The contract records which protocol/profile version governed the task.

## Repository Templates

There are two valid deployment styles:

### Central-only
The execution agent reads templates directly from `codex-auto`. Target repositories contain only
`.codex-auto/project.yml`. This is protocol-only adoption; it does not install the executable API
orchestrator or make it automatically discoverable in a ChatGPT/Codex local project.

### Project-local executable integration

Run `init-project` to add the repo-scoped skill, project Sol/Luna agent configuration, local launcher,
orchestrator configuration, and ignored runtime. This is the recommended style when development
tasks should invoke codex-auto directly without affecting other projects or user-level Codex
settings.

A target repository may additionally contain local GitHub issue/PR templates or workflows for
better GitHub UX. Those files should identify the canonical `codex-auto` version they implement and
should remain thin adapters rather than forks of the protocol.

## Project-Specific Rules

Keep domain rules in the consumer profile, not in this repository's core protocol. Examples include:
- authentication/user invariants;
- specific database versioning fields;
- required E2E suites;
- Docker/Kubernetes runtime checks;
- regulated-data handling;
- protected modules;
- project-specific Definition of Done.

This separation allows the same Sol/Luna governance model to be reused across unrelated repositories.
