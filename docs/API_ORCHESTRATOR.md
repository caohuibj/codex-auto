# API Orchestrator MVP

## Objective

The service turns the governance protocol into an executable, fail-closed workflow. Sol performs
planning and independent review. Luna produces bounded implementation and fix patches. Git and
GitHub own branches, commits, pull requests, checks, and review evidence. A human always owns merge.

The names Sol and Luna describe configured routes, not hard-coded providers. Provider and model IDs
are runtime configuration.

## Runtime Flow

```text
TaskRequest
  -> repository snapshot at exact base SHA
  -> Sol PlanProposal (strict JSON schema)
  -> trusted TaskContract construction + validation
  -> feature branch from contract base
  -> Luna ImplementationProposal (unified diff)
  -> patch policy gate -> configured verification -> commit/push -> PR
  -> collect actual PR diff, head SHA, local results, and CI checks
  -> Sol ReviewResult (strict JSON schema)
       APPROVED -> deterministic evidence gate -> MERGE_READY -> stop for human
       CHANGES_REQUESTED -> Luna bounded fix -> re-verify -> re-review
       BLOCKED -> stop with evidence
  -> max_fix_cycles reached -> BLOCKED
```

## Determinism and Safety Boundary

"Deterministic" applies to routing, schemas, state transitions, policy gates, branch naming, fix
bounds, and terminal behavior. It does not claim byte-identical language-model output.

The MVP uses the following controls:

- strict Pydantic models and Responses API JSON Schema output;
- trusted identity fields (repository, branch, SHA, task ID) constructed outside the model;
- human scope preservation and configured-check allowlisting during contract validation;
- unified-diff validation before application;
- allowed/forbidden path policy, with deletions, binaries, and symlinks disabled by default;
- workflow definitions, repo-scoped skills, and `.codex-auto` policy files protected by the default
  forbidden-path set;
- verification commands supplied only by trusted configuration, never by model output;
- review identity and acceptance-criterion coverage checks;
- required local/CI evidence gate before `MERGE_READY`;
- an append-only, redacted JSONL audit trail;
- no merge method in the GitHub adapter and a required human merge policy.

## Components

| Component | Responsibility |
|---|---|
| `config.py` | Provider/model routes, GitHub policy, fix bound, audit, pricing hooks |
| `models.py` | Strict contracts for every model and adapter boundary |
| `state.py` | Allowed workflow transitions |
| `responses.py` | OpenAI Responses API adapter with strict structured outputs and usage capture |
| `github.py` | Local Git + `gh` adapter for snapshot, branch, patch, commit, PR, and evidence |
| `contract.py` | Trusted Task Contract construction and deterministic evidence/review gates |
| `orchestrator.py` | End-to-end control loop and human stop gate |
| `audit.py` / `cost.py` | Redacted events, token totals, and optional cost estimates |
| `cli.py` | `validate` and single-task `run` entry points |

Both external systems are ports. Tests inject mock Responses clients and a mock GitHub adapter, so
integration tests neither call OpenAI nor touch a real repository.

## Configuration

Copy `config/orchestrator.example.yml` outside source control if it contains environment-specific
values. Model IDs, reasoning effort, provider base URL, verification commands, required CI checks,
path policy, and pricing are configurable. API keys are read only from the configured environment
variable. The example contains no credential.

Set `required_ci_checks` to the exact GitHub check names used by the target repository. The example
uses this repository's `quality` job; a missing, pending, skipped, or failed required check blocks
`MERGE_READY`.

Only verification commands present in `github.verification_commands` may enter a generated Task
Contract. Each command is an argument vector and is executed without a shell.

## CLI

```bash
uv sync --extra api --extra dev
uv run codex-auto init-project --help
uv run codex-auto validate \
  --config config/orchestrator.example.yml \
  --task examples/task.example.yml

OPENAI_API_KEY=... uv run codex-auto run \
  --config /path/to/project-orchestrator.yml \
  --task /path/to/task.yml \
  --repo-path /path/to/target-checkout
```

The checkout must be clean and its configured remote must match `github.repository`. The command
returns exit code `0` only at `MERGE_READY`; bounded or unexpected failures return a structured
`BLOCKED` result and exit code `2`.

For repository-local installation and automatic discovery inside one ChatGPT/Codex local project,
see [`PROJECT_LOCAL_INSTALLATION.md`](PROJECT_LOCAL_INSTALLATION.md).

## Real MVP Limitations

- It runs one task synchronously in one local checkout; there is no queue, database, leasing, resume,
  cancellation, or multi-worker concurrency control.
- Patch generation sends selected repository text to the model and is bounded by
  `context_max_bytes`; large repositories need retrieval/context-selection extensions.
- The GitHub adapter requires installed/authenticated `git` and `gh`; GitHub App authentication and
  direct REST/webhook adapters are not included.
- It applies text unified diffs only. Binary files, symlinks, and deletions are rejected by default.
- Model/API retries and idempotency keys are not yet implemented. A rerun may require operator
  cleanup or deliberate reuse of the existing feature branch/PR.
- Cost output is an estimate only when the operator supplies current per-model rates. The service
  always records API-reported token usage.
- CI collection is a point-in-time snapshot; the MVP does not wait or poll for pending checks.
- This is an orchestration engine, not a sandbox. It should run in an isolated checkout with least-
  privilege credentials and trusted verification configuration.
