# codex-auto

Reusable AI-assisted software engineering governance and orchestration protocol.

`codex-auto` defines a project-agnostic workflow in which a lead/reviewer agent plans and verifies work, an implementation agent executes bounded tasks, GitHub records the durable shared state, CI provides machine-verifiable evidence, and a human retains merge authority.

## Default Roles

```text
Human Product Owner
        |
        v
Sol High — Lead / Architect
        |
        | Task Contract
        v
Luna Max — Implementer
        |
        | feature branch + tests + PR
        v
Sol High — Independent Reviewer
        |
        +--> APPROVED ----------> Human Merge
        |
        +--> CHANGES_REQUESTED -> Luna -> Sol Review
        |
        +--> BLOCKED -----------> Escalation
```

The model names are defaults, not hard dependencies. The protocol is based on role separation: expensive judgment for planning/review, bounded execution for implementation, and repository evidence for coordination.

## Executable API Orchestrator

The repository now includes a minimal Python service that executes this protocol with configurable
Sol/Luna routes over the OpenAI Responses API. It validates a model-generated Task Contract, applies
bounded implementation/fix patches on a feature branch, opens a GitHub PR, collects actual diff/CI
evidence, independently reviews it, and stops at a human merge gate.

```bash
uv sync --extra dev
uv run codex-auto validate \
  --config config/orchestrator.example.yml \
  --task examples/task.example.yml
```

See [`docs/API_ORCHESTRATOR.md`](docs/API_ORCHESTRATOR.md) for architecture, runtime use, safety
boundaries, and honest MVP limitations.

To install codex-auto into one ChatGPT/Codex local project without changing global Python, skills,
plugins, or Codex configuration, follow
[`docs/PROJECT_LOCAL_INSTALLATION.md`](docs/PROJECT_LOCAL_INSTALLATION.md). The `init-project`
command creates a repo-scoped `.agents/skills/codex-auto` entry and project-local runtime launcher.

## Core Files

- [`docs/AI_DEVELOPMENT_PROTOCOL.md`](docs/AI_DEVELOPMENT_PROTOCOL.md) — governance, state machine, evidence and escalation rules.
- [`docs/TASK_CONTRACT_TEMPLATE.md`](docs/TASK_CONTRACT_TEMPLATE.md) — Lead-to-Implementer handoff contract.
- [`docs/PR_REVIEW_PROTOCOL.md`](docs/PR_REVIEW_PROTOCOL.md) — independent five-level review and decision states.
- [`docs/PROJECT_PROFILE_TEMPLATE.md`](docs/PROJECT_PROFILE_TEMPLATE.md) — project-specific constraints without forking the protocol.
- [`docs/ADOPTION.md`](docs/ADOPTION.md) — how other repositories consume `codex-auto`.
- [`agents/SOL_LEAD_REVIEWER.md`](agents/SOL_LEAD_REVIEWER.md) — Sol lead/reviewer role instructions.
- [`agents/LUNA_IMPLEMENTER.md`](agents/LUNA_IMPLEMENTER.md) — Luna implementation role instructions.
- [`docs/API_ORCHESTRATOR.md`](docs/API_ORCHESTRATOR.md) — executable service architecture and use.
- [`docs/PROJECT_LOCAL_INSTALLATION.md`](docs/PROJECT_LOCAL_INSTALLATION.md) — isolated per-project installation and direct ChatGPT/Codex use.
- [`config/orchestrator.example.yml`](config/orchestrator.example.yml) — provider/model routing and policy example.
- [`.github/ISSUE_TEMPLATE/implementation-task.md`](.github/ISSUE_TEMPLATE/implementation-task.md) — canonical bounded-task issue format.
- [`.github/pull_request_template.md`](.github/pull_request_template.md) — canonical implementation evidence format.

## Consumer Projects

Recommended target-repository integration is intentionally small:

```text
.agents/skills/codex-auto/   # repo-scoped discovery
.codex-auto/                 # project profile, routing, launcher, local runtime
```

`init-project` creates these entries. The project profile pins the protocol version and adds
project-specific branch, architecture, verification, runtime, and escalation constraints. Generic
Sol/Luna behavior remains centralized here.

See [`docs/ADOPTION.md`](docs/ADOPTION.md).

## Principles

- GitHub is the durable source of truth; model memory is not.
- Planning and review are independent from implementation.
- Every implementation starts from a bounded, testable Task Contract.
- The reviewer reads the actual diff and evidence rather than trusting completion summaries.
- Unsupported `PASS` claims are prohibited; `NOT_RUN` is explicit and acceptable when evidence is unavailable.
- Avoid unrelated refactors and unnecessary defensive engineering.
- AI agents do not merge under the default policy.

## Versioning

Once the initial protocol is merged, protocol releases should be tagged (`v1.x`, etc.). Consumer projects should pin a released version so protocol upgrades are deliberate and do not silently change in-progress tasks.
