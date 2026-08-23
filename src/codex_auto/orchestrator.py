"""Deterministic orchestration of planning, implementation, review, and bounded fixes."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, TypeVar

from pydantic import BaseModel

from codex_auto.audit import JsonlAuditLog, redact
from codex_auto.config import AppConfig, ModelRoute
from codex_auto.contract import build_contract, validate_evidence, validate_review
from codex_auto.cost import CostLedger
from codex_auto.models import (
    ImplementationProposal,
    OrchestrationResult,
    PlanProposal,
    PullRequestEvidence,
    ReviewDecision,
    ReviewResult,
    TaskContract,
    TaskRequest,
    TaskState,
)
from codex_auto.ports import GitHubAdapter, ResponsesClient
from codex_auto.prompts import (
    FIX_INSTRUCTIONS,
    IMPLEMENTATION_INSTRUCTIONS,
    PLANNING_INSTRUCTIONS,
    REVIEW_INSTRUCTIONS,
)
from codex_auto.state import TaskStateMachine

OutputT = TypeVar("OutputT", bound=BaseModel)


class Orchestrator:
    def __init__(
        self,
        config: AppConfig,
        clients: Mapping[str, ResponsesClient],
        github: GitHubAdapter,
        audit: JsonlAuditLog,
    ) -> None:
        self.config = config
        self.clients = clients
        self.github = github
        self.audit = audit
        self.state = TaskStateMachine()
        self.cost = CostLedger(config.cost)

    def _transition(self, target: TaskState, **payload: Any) -> None:
        source, destination = self.state.transition(target)
        self.audit.append(
            "state.transition",
            destination,
            {"from": source.value, "to": destination.value, **payload},
        )

    def _complete(
        self,
        *,
        phase: str,
        route: ModelRoute,
        instructions: str,
        input_data: dict[str, Any],
        output_type: type[OutputT],
        task_id: str,
    ) -> OutputT:
        client = self.clients.get(route.provider)
        if client is None:
            raise ValueError(f"no Responses client registered for provider {route.provider!r}")
        output, raw_usage = client.complete(
            phase=phase,
            route=route,
            instructions=instructions,
            input_data=redact(input_data),
            output_type=output_type,
            metadata={"task_id": task_id, "phase": phase},
        )
        usage = self.cost.record(raw_usage)
        self.audit.append(
            "model.completed",
            self.state.state,
            {
                "phase": phase,
                "provider": usage.provider,
                "model": usage.model,
                "response_id": usage.response_id,
                "input_tokens": usage.input_tokens,
                "cached_input_tokens": usage.cached_input_tokens,
                "output_tokens": usage.output_tokens,
                "reasoning_tokens": usage.reasoning_tokens,
                "estimated_cost_usd": usage.estimated_cost_usd,
            },
        )
        return output

    @staticmethod
    def _branch_name(prefix: str, task_id: str) -> str:
        slug = re.sub(r"[^a-z0-9._-]+", "-", task_id.lower()).strip("-.")
        if not slug:
            raise ValueError("task ID cannot produce an empty branch slug")
        return f"{prefix}{slug}"[:240]

    def _result(
        self,
        request: TaskRequest,
        *,
        contract: TaskContract | None,
        evidence: PullRequestEvidence | None,
        review: ReviewResult | None,
        fix_cycles: int,
        blocked_reason: str | None = None,
    ) -> OrchestrationResult:
        return OrchestrationResult(
            task_id=request.task_id,
            state=self.state.state,
            contract=contract,
            pull_request_url=None if evidence is None else evidence.url,
            pull_request_number=None if evidence is None else evidence.number,
            review=review,
            fix_cycles=fix_cycles,
            usage=self.cost.records,
            estimated_cost_usd=self.cost.total_usd,
            human_action_required=(
                "Review repository gates and merge the pull request manually."
                if self.state.state == TaskState.MERGE_READY
                else None
            ),
            blocked_reason=blocked_reason,
        )

    def run(self, request: TaskRequest) -> OrchestrationResult:
        contract: TaskContract | None = None
        evidence: PullRequestEvidence | None = None
        review: ReviewResult | None = None
        fix_cycles = 0
        self.audit.append("task.requested", self.state.state, request.model_dump(mode="json"))

        try:
            self._transition(TaskState.PLANNING)
            snapshot = self.github.snapshot(request.context_paths)
            self.audit.append(
                "repository.snapshot",
                self.state.state,
                {
                    "repository": snapshot.repository,
                    "base_branch": snapshot.base_branch,
                    "base_sha": snapshot.base_sha,
                    "file_count": len(snapshot.files),
                    "tree_path_count": len(snapshot.tree_paths),
                },
            )
            plan = self._complete(
                phase="planning",
                route=self.config.routing.planning,
                instructions=PLANNING_INSTRUCTIONS,
                input_data={
                    "request": request.model_dump(mode="json"),
                    "repository": snapshot.model_dump(mode="json"),
                    "configured_verification": sorted(
                        self.config.github.verification_commands.keys()
                    ),
                },
                output_type=PlanProposal,
                task_id=request.task_id,
            )
            contract = build_contract(
                request,
                plan,
                repository=snapshot.repository,
                base_branch=snapshot.base_branch,
                base_sha=snapshot.base_sha,
                config=self.config,
                project_profile=(
                    ".codex-auto/project.yml"
                    if ".codex-auto/project.yml" in snapshot.tree_paths
                    else None
                ),
            )
            self._transition(TaskState.PLANNED, base_sha=contract.base_sha)
            self.audit.append(
                "contract.validated",
                self.state.state,
                {
                    "acceptance_criteria": [item.id for item in contract.acceptance_criteria],
                    "verification": contract.verification,
                },
            )

            branch = self._branch_name(self.config.github.feature_branch_prefix, request.task_id)
            self.github.create_feature_branch(branch, contract.base_sha)
            self._transition(TaskState.IMPLEMENTING, branch=branch)
            implementation = self._complete(
                phase="implementation",
                route=self.config.routing.implementation,
                instructions=IMPLEMENTATION_INSTRUCTIONS,
                input_data={
                    "contract": contract.model_dump(mode="json"),
                    "repository": snapshot.model_dump(mode="json"),
                },
                output_type=ImplementationProposal,
                task_id=request.task_id,
            )
            paths = self.github.apply_proposal(branch, implementation)
            verification = self.github.run_verification(contract.verification)
            head_sha = self.github.commit_and_push(branch, implementation.commit_message, paths)
            number, url = self.github.open_or_update_pull_request(branch, contract, verification)
            self.audit.append(
                "github.pull_request_opened",
                self.state.state,
                {"number": number, "url": url, "head_sha": head_sha, "paths": paths},
            )
            self._transition(TaskState.PR_OPEN, number=number, url=url)
            evidence = self.github.collect_pull_request_evidence(number, verification)

            while True:
                self._transition(TaskState.REVIEWING, head_sha=evidence.head_sha)
                review = self._complete(
                    phase="review",
                    route=self.config.routing.review,
                    instructions=REVIEW_INSTRUCTIONS,
                    input_data={
                        "contract": contract.model_dump(mode="json"),
                        "pull_request_evidence": evidence.model_dump(mode="json"),
                    },
                    output_type=ReviewResult,
                    task_id=request.task_id,
                )
                validate_review(contract, evidence, review)
                self.audit.append(
                    "review.completed",
                    self.state.state,
                    {
                        "decision": review.decision.value,
                        "head_sha": review.head_sha,
                        "blocking_findings": len(
                            [item for item in review.findings if item.severity == "blocking"]
                        ),
                    },
                )

                if review.decision == ReviewDecision.APPROVED:
                    validate_evidence(contract, evidence, self.config)
                    self._transition(
                        TaskState.MERGE_READY,
                        human_merge_required=self.config.policy.human_merge_required,
                    )
                    self.audit.append(
                        "human_merge_gate.reached",
                        self.state.state,
                        {"pull_request_url": evidence.url},
                    )
                    return self._result(
                        request,
                        contract=contract,
                        evidence=evidence,
                        review=review,
                        fix_cycles=fix_cycles,
                    )

                if review.decision == ReviewDecision.BLOCKED:
                    self._transition(TaskState.BLOCKED, reason=review.merge_recommendation)
                    return self._result(
                        request,
                        contract=contract,
                        evidence=evidence,
                        review=review,
                        fix_cycles=fix_cycles,
                        blocked_reason=review.merge_recommendation,
                    )

                self._transition(TaskState.CHANGES_REQUESTED)
                if fix_cycles >= self.config.policy.max_fix_cycles:
                    reason = f"maximum fix cycles reached ({self.config.policy.max_fix_cycles})"
                    self._transition(TaskState.BLOCKED, reason=reason)
                    return self._result(
                        request,
                        contract=contract,
                        evidence=evidence,
                        review=review,
                        fix_cycles=fix_cycles,
                        blocked_reason=reason,
                    )

                fix_cycles += 1
                self._transition(TaskState.FIXING, cycle=fix_cycles)
                fix = self._complete(
                    phase="fix",
                    route=self.config.routing.fix,
                    instructions=FIX_INSTRUCTIONS,
                    input_data={
                        "contract": contract.model_dump(mode="json"),
                        "pull_request_evidence": evidence.model_dump(mode="json"),
                        "review": review.model_dump(mode="json"),
                        "fix_cycle": fix_cycles,
                    },
                    output_type=ImplementationProposal,
                    task_id=request.task_id,
                )
                paths = self.github.apply_proposal(branch, fix)
                verification = self.github.run_verification(contract.verification)
                self.github.commit_and_push(branch, fix.commit_message, paths)
                evidence = self.github.collect_pull_request_evidence(number, verification)
                self.audit.append(
                    "fix.completed",
                    self.state.state,
                    {"cycle": fix_cycles, "head_sha": evidence.head_sha, "paths": paths},
                )

        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
            if self.state.state not in {TaskState.BLOCKED, TaskState.MERGE_READY}:
                self._transition(TaskState.BLOCKED, reason=reason)
            self.audit.append("task.blocked", self.state.state, {"reason": reason})
            return self._result(
                request,
                contract=contract,
                evidence=evidence,
                review=review,
                fix_cycles=fix_cycles,
                blocked_reason=reason,
            )
