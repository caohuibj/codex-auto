# Project Profile Template

A Project Profile adapts the generic `codex-auto` protocol to one target repository without copying or modifying the core protocol.

```yaml
project:
  name: <name>
  repository: <owner/repo>
  integration_branch: <dev/main/etc>
  production_branch: <main/release/etc>

workflow:
  human_integration_required: true
  feature_branch_pattern: "feature/*"
  task_contract_required: true
  independent_review_required: true

architecture:
  protected_boundaries:
    - <boundary or invariant>
  dependency_rules:
    - <rule>
  prohibited_changes:
    - <change requiring separate approval>

persistence:
  invariants:
    - <data integrity/versioning rule>
  migration_policy:
    - <migration requirement>

verification:
  required:
    - lint
    - typecheck
    - unit
  conditional:
    - condition: <when>
      require: <integration/E2E/container/etc>
  regression_scope:
    - <critical subsystem>

runtime:
  required_environments:
    - <host/docker/staging/etc>
  deployment_constraints:
    - <constraint>

quality:
  avoid:
    - unrelated refactor
    - unnecessary abstraction
  definition_of_done:
    - <project-specific criterion>

escalation:
  always_escalate:
    - auth/security boundary changes
    - destructive data migration
    - public API break
```

## Precedence

1. Explicit human instruction for the current task.
2. Target project's versioned Project Profile.
3. `codex-auto` core protocol defaults.

A Project Profile should contain only project-specific constraints. Generic workflow rules belong in `codex-auto` so they can evolve centrally.
