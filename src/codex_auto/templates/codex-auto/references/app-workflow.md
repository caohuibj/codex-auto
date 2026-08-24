# ChatGPT App workflow reference

This repository is `__REPOSITORY__`. The signed-in ChatGPT desktop App is the only model runtime.
The commands below are repository-local state/evidence validators and never invoke a model.

Use these stable paths for one task:

```text
TASK=.codex-auto/tasks/<task-id>.yml
SESSION=.codex-auto/results/<task-id>/session.json
PACKET=.codex-auto/results/<task-id>/packet.json
PLAN=.codex-auto/results/<task-id>/plan.yml
REVIEW=.codex-auto/results/<task-id>/review.yml
CONFIG=.codex-auto/orchestrator.yml
```

Every command needs `--config "$CONFIG" --repo-path . --session "$SESSION"`. Add
`--packet "$PACKET"` whenever the next Sol/Luna handoff needs refreshed evidence.

```text
app-start --task "$TASK"
app-accept-plan --plan "$PLAN"
app-begin-implementation
app-record-change
app-begin-review
app-submit-review --review "$REVIEW"
app-begin-fix
app-record-fix
app-status
```

PlanProposal fields:

```yaml
objective: A precise objective of at least ten characters.
in_scope: [Every human in-scope item]
out_of_scope: [Every human exclusion]
architecture_constraints: [At least one constraint]
implementation_requirements: [At least one requirement]
acceptance_criteria:
  - id: AC-01
    condition: A testable condition.
    evidence_required: Exact evidence needed.
verification: [Only configured verification names]
expected_deliverables: [At least one deliverable]
escalation_conditions: [At least one stop condition]
```

ReviewResult fields (copy task/base/head identifiers from the latest packet):

```yaml
decision: APPROVED # or CHANGES_REQUESTED or BLOCKED
task_id: TASK-001
base_sha: <40-character contract base SHA>
head_sha: <40-character current change head SHA>
criteria:
  - criterion_id: AC-01
    status: PASS # FAIL or UNVERIFIED when not approved
    evidence: Evidence from the actual local diff/checks.
findings: []
integration_recommendation: A precise human-facing recommendation.
```

Each blocking finding uses: `id`, `severity: blocking`, optional `criterion_id`, `location`, `issue`,
`evidence`, `required_change`, and `acceptance_condition`. `APPROVED` cannot contain blocking findings
or non-PASS criteria and cannot bypass failed local evidence or configured remote evidence.
