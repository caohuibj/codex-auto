---
name: codex-auto
description: Use for implementation, bug fixes, or refactors in this repository through the project-local Sol/Luna codex-auto workflow. Do not use for review-only or explanation-only questions, or when the user explicitly asks for direct manual editing.
---

# Project-local codex-auto workflow

Operate only in `__REPOSITORY__`. Read `.codex-auto/project.yml` and
`.codex-auto/orchestrator.yml` before acting. Never copy ChatGPT OAuth tokens, request an OpenAI API
key in `chatgpt-app` mode, install a global runtime, publish unless configured, or integrate code.

## ChatGPT App mode (default)

The current ChatGPT desktop App task is the orchestration runtime. Planning and review stay in the
primary Sol task. Implementation and fixes must be delegated through the App's native subagent tool
to one Luna agent using the exact configured model and effort. Do not invoke Codex CLI, Responses
API, or an SDK as a model backend. The project-local `codex-auto` executable below is only a
deterministic validator/state recorder; it performs no model call.

Before starting, confirm that the primary task model matches the configured planning/review route
and that native delegation can create the project agent named `luna_implementer` with the exact
configured Luna implementation/fix model and effort. Check `.codex/config.toml`,
`.codex/agents/luna-implementer.toml`, and `.codex-auto/orchestrator.yml`; the first checkpoint will
also reject any mismatch. If the selected primary model cannot be confirmed, the named agent is
missing, its configured model is unavailable, or either exact route differs, stop with a precise
blocker. Never silently substitute a model, use the inherited Sol model for the worker, or implement
inside the Sol task.

1. Convert the request into one bounded TaskRequest YAML under `.codex-auto/tasks/<task-id>.yml`.
   Include exact scope, exclusions, context paths, constraints, and configured verification names.
2. Start the durable session and write a packet:

   ```text
   ./.codex-auto/bin/codex-auto app-start --config .codex-auto/orchestrator.yml --task <task-file> --repo-path . --session .codex-auto/results/<task-id>/session.json --packet .codex-auto/results/<task-id>/packet.json
   ```

3. As Sol, inspect the packet and repository, write a PlanProposal YAML matching
   `references/app-workflow.md`, then validate it with `app-accept-plan`.
4. Run `app-begin-implementation`. Delegate the validated contract and feature branch to exactly one
   `luna_implementer` subagent. Luna may edit only contract scope, run named checks, and commit the
   local change. Push/PR work is allowed only when the optional GitHub extension is configured.
   Confirm that the App shows the expected named agent and Luna route before
   accepting its work. Wait for it to finish; do not implement in the Sol task.
5. Record the committed branch with `app-record-change`, then run `app-begin-review`. As Sol, review
   the actual packet diff, local verification, optional remote checks, and contract; submit a
   ReviewResult YAML with
   `app-submit-review`.
6. On `CHANGES_REQUESTED`, run `app-begin-fix`. If it returns `FIXING`, delegate only the blocking
   findings to Luna, then run `app-record-fix` and repeat Sol review. Never exceed
   `max_fix_cycles`; a `BLOCKED` result is terminal.
7. On `INTEGRATION_READY`, report the branch, base/head SHAs, local evidence, and optional remote
   URL, then stop for human integration. Never merge, rebase, cherry-pick, or push implicitly.

Pass `--packet .codex-auto/results/<task-id>/packet.json` on any checkpoint when a refreshed handoff
packet is needed. Treat a failed checkpoint, contract, local verification, optional remote check,
state transition, or human integration gate as authoritative. A required suite that is skipped or
cannot start must be represented by a command that exits non-zero; an exit-zero summary alone cannot
prove that an integration environment existed.

Read `references/app-workflow.md` for every checkpoint command and the exact PlanProposal and
ReviewResult shapes before starting the first App-native workflow.

## Responses API mode (explicit opt-in)

Only when `.codex-auto/project.yml` says `execution_mode: responses-api`, validate the task and use
the `run` command. That mode requires its configured API credential and is billed separately from
ChatGPT. Never infer API access from a ChatGPT subscription.
