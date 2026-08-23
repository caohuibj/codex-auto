---
name: codex-auto
description: Use for implementation, bug fixes, or refactors in this repository through the project-local Sol/Luna codex-auto workflow. Do not use for review-only or explanation-only questions, or when the user explicitly asks for direct manual editing.
---

# Project-local codex-auto workflow

Operate only in `__REPOSITORY__`. Use the repository-local runtime and configuration; never install
or modify a user-level or system-level codex-auto installation.

When this skill applies:

1. Read `.codex-auto/project.yml`, `.codex-auto/orchestrator.yml`, the current Git state, and the
   relevant repository files.
2. Convert the request into one bounded TaskRequest YAML file under `.codex-auto/tasks/`. Include a
   stable task ID, exact in-scope and out-of-scope boundaries, relevant context paths, constraints,
   and verification names that exist in `.codex-auto/orchestrator.yml`.
3. Validate the request before running:

   ```text
   ./.codex-auto/bin/codex-auto validate --config .codex-auto/orchestrator.yml --task <task-file>
   ```

4. For an authorized implementation request, run the project-local orchestrator:

   ```text
   ./.codex-auto/bin/codex-auto run --config .codex-auto/orchestrator.yml --task <task-file> --repo-path .
   ```

5. Report the final state, PR URL, verification evidence, fix-cycle count, token/cost accounting,
   and any genuine limitation. Never merge the PR.

Stop with a precise blocker if the local runtime, API key, GitHub authentication, clean worktree, or
required configuration is missing. Do not bypass a failed contract, patch, evidence, CI, or human
merge gate.
