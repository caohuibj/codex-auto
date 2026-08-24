# Local Git-first Architecture

## Decision

`codex-auto` v2 treats a local Git worktree as the required repository/evidence boundary. GitHub is
an optional publication extension, not part of the orchestration core. This is the default because
all supported projects can provide a local branch, commits, a base/head identity, a diff, and local
verification, while some projects have no GitHub repository or cannot run GitHub Actions.

The core completion state is `INTEGRATION_READY`. It means the exact recorded commit passed the
configured evidence gate and independent review. It never means that a merge, rebase, cherry-pick,
push, deployment, or release has happened.

## Trust boundaries

| Layer | Responsibility | Enforcement strength |
|---|---|---|
| `AGENTS.md` | Route change work into the project workflow and state human-facing rules | Instructional |
| Repo skill and agent TOML | Select the workflow and exact Sol/Luna role configuration | App discovery plus fail-closed route validation |
| Task Contract | Freeze scope, base SHA, acceptance criteria, and named checks | Deterministic schema and policy validation |
| Local Git adapter | Own branch creation, patch policy, commit identity, diff, and clean-worktree checks | Deterministic local enforcement |
| Verification commands | Execute project-owned lint/type/test/build/integration gates | Exit-code evidence bound to a recorded head SHA |
| Sol review | Judge the actual contract, diff, and verification evidence | Structured independent judgment |
| State machine | Bound retries and stop before integration | Deterministic transition enforcement |
| Optional GitHub adapter | Publish the same branch and add PR/check evidence | Additional remote evidence only |

Documentation and `AGENTS.md` cannot prove that tests ran or prevent a user from manually changing
Git history. Hard gates therefore remain in the repository-local checkpoint. Conversely, the
checkpoint does not claim cryptographic attestation: a person with filesystem access can edit local
runtime files and history. Git SHAs and stored records detect drift and bind evidence consistently;
they are not a substitute for an externally trusted signer.

## Neutral domain model

The core uses `RepositoryAdapter` and `ChangeEvidence`, not `GitHubAdapter` or
`PullRequestEvidence`.

```text
TaskRequest
  -> RepositorySnapshot(base branch + immutable base SHA)
  -> TaskContract
  -> local feature branch
  -> committed implementation
  -> ChangeEvidence(base/head SHA + diff + local verification + optional remote evidence)
  -> independent review with an integration recommendation
  -> INTEGRATION_READY
  -> stop for a human
```

`RemoteChangeEvidence` is optional. When GitHub publication is configured, it adds a PR reference,
URL, and named check results to the same local evidence object. Required remote checks are illegal
without an explicit GitHub configuration.

## State machine

```text
REQUESTED -> PLANNING -> PLANNED -> IMPLEMENTING -> CHANGE_READY -> REVIEWING
                                                               |          |
                                                               |          +-> INTEGRATION_READY
                                                               |          +-> CHANGES_REQUESTED
                                                               |                    |
                                                               |                    v
                                                               +-------------- FIXING

Any active state -> BLOCKED on an invalid contract, missing evidence, failed check, route mismatch,
unsafe repository operation, review blocker, or exhausted fix bound.
```

`max_fix_cycles` is counted before every fix. `BLOCKED` and `INTEGRATION_READY` are terminal. There
is deliberately no integration/merge method on the adapter interface.

## Local-only operating sequence

1. A human opens the repository as the ChatGPT/Codex App primary folder and selects the configured
   Sol model.
2. Route validation confirms the exact Sol planning/review route and exact named Luna
   implementation/fix route. Missing or unavailable routes stop the flow; no model substitution is
   allowed.
3. Sol creates and validates a bounded Task Contract against the current local base-branch SHA.
4. The checkpoint creates `codex-auto/<task-id>` from that SHA.
5. Exactly one Luna worker implements, runs the named checks, and commits locally. It must not push
   when no publication extension is configured.
6. `app-record-change` reruns the configured verification commands, requires a clean worktree, and
   records base/head SHAs plus the actual Git diff.
7. Sol reviews that recorded evidence. Fixes use the same branch and repeat verification/evidence
   collection; the latest review must match the latest head SHA.
8. Approval plus passing evidence reaches `INTEGRATION_READY`. The App reports the evidence and
   stops. A human decides how to integrate the branch.

Session state and handoff packets live under `.codex-auto/results/<task-id>/`; structured audit
events live under `.codex-auto/audit/`. Both locations are ignored runtime data. Durable product
history remains the local commits themselves.

## Verification rules

Verification commands are trusted project configuration and execute as argument arrays without a
shell. Models may select only configured names and cannot invent commands. Every required Task
Contract check must return `PASS`; `NOT_RUN`, `N/A`, missing, or failed results block approval.

An exit code of zero is the evidence boundary. Projects whose test runner exits zero after skipping
a required database/browser/service suite must provide a wrapper command that fails when the
required environment is unavailable or when required tests are skipped. `codex-auto` cannot infer
that policy reliably from arbitrary human-readable test output.

Verification should run after the implementation commit so its evidence is associated with the
current head. Commands that mutate tracked or untracked files cause subsequent evidence collection
to fail the clean-worktree gate.

## Optional GitHub publication

Adding a `github` section changes only publication and remote evidence:

```yaml
repository:
  identifier: eduk12-local
  base_branch: dev
  verification_commands:
    lint: [npm, run, lint]
    unit: [npm, run, test]

github:
  repository: caohuibj/eduK12-new-version
  remote: origin
  required_checks: [quality]
```

Without that section no remote command is executed and `gh` is not required. With it, the adapter
validates the remote identity, pushes the branch, opens/updates a PR, confirms that the PR head is
the exact local commit, and adds required check evidence. GitHub failure blocks only workflows that
explicitly opted into GitHub publication.

## Consumer repository files

`init-project` creates or updates:

```text
AGENTS.md                              # small managed routing block; existing content is preserved
.agents/skills/codex-auto/             # workflow skill and reference
.codex/config.toml                     # exact Sol default and subagent policy
.codex/agents/luna-implementer.toml    # exact Luna worker
.codex-auto/project.yml                # project profile
.codex-auto/orchestrator.yml           # routes, repository policy, verification, optional GitHub
.codex-auto/bin/codex-auto             # deterministic local checkpoint launcher
```

The runtime, task sessions, packets, audit log, and secrets remain ignored. Orchestration policy
files and `AGENTS.md` are forbidden implementation paths so a delegated task cannot rewrite its own
guardrails.

## Real limitations

- App plan allowances and API usage are separate; local Git mode removes GitHub dependency but does
  not create unlimited ChatGPT/Codex capacity.
- Local evidence is trustworthy for cooperative workflow consistency, not hostile-user
  attestation.
- The generic runner trusts process exit codes and cannot understand every test framework's skip
  semantics.
- Concurrent tasks in one worktree still conflict; use separate worktrees for parallel work.
- A human can manually bypass the process. Enforced organizational merge rules still require a
  remote server or another external policy system.
- Existing v1 session JSON/state names are not resumed in v2. Finish or archive active v1 tasks
  before upgrading; v1 configuration files can still be loaded through the compatibility mapper.
