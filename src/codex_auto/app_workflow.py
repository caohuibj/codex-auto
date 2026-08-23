"""Deterministic checkpoints for ChatGPT desktop App-native orchestration."""

from __future__ import annotations

import json
import re
from pathlib import Path

from codex_auto.audit import JsonlAuditLog
from codex_auto.config import AppConfig
from codex_auto.contract import build_contract, validate_evidence, validate_review
from codex_auto.models import (
    AppSession,
    OrchestrationResult,
    PlanProposal,
    ReviewDecision,
    ReviewResult,
    TaskRequest,
    TaskState,
)
from codex_auto.ports import GitHubAdapter
from codex_auto.state import allowed_transitions


class AppWorkflowError(ValueError):
    pass


class AppSessionStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> AppSession:
        if not self.path.exists():
            raise AppWorkflowError(f"App workflow session does not exist: {self.path}")
        return AppSession.model_validate_json(self.path.read_text(encoding="utf-8"))

    def save(self, session: AppSession) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(session.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(self.path)


class ChatGPTAppWorkflow:
    """Advance one App-native task while keeping model calls outside Python."""

    def __init__(
        self,
        config: AppConfig,
        github: GitHubAdapter,
        store: AppSessionStore,
        audit: JsonlAuditLog,
    ) -> None:
        self.config = config
        self.github = github
        self.store = store
        self.audit = audit
        provider_types = {
            self.config.providers[route.provider].type
            for route in (
                self.config.routing.planning,
                self.config.routing.implementation,
                self.config.routing.review,
                self.config.routing.fix,
            )
        }
        if provider_types != {"chatgpt_app"}:
            raise AppWorkflowError("App workflow requires every route to use chatgpt_app")

    @staticmethod
    def _branch_name(prefix: str, task_id: str) -> str:
        slug = re.sub(r"[^a-z0-9._-]+", "-", task_id.lower()).strip("-.")
        if not slug:
            raise AppWorkflowError("task ID cannot produce an empty branch slug")
        return f"{prefix}{slug}"[:240]

    def _transition(self, session: AppSession, target: TaskState, **payload: object) -> None:
        source = session.state
        if target not in allowed_transitions(source):
            raise AppWorkflowError(f"invalid App workflow transition: {source} -> {target}")
        session.state = target
        self.audit.append(
            "state.transition",
            target,
            {"from": source.value, "to": target.value, **payload},
        )

    def start(self, request: TaskRequest) -> AppSession:
        if self.store.path.exists():
            raise AppWorkflowError(f"session already exists: {self.store.path}")
        repository = self.github.snapshot(request.context_paths)
        session = AppSession(task_id=request.task_id, request=request, repository=repository)
        self.audit.append("task.requested", session.state, request.model_dump(mode="json"))
        self._transition(session, TaskState.PLANNING, runtime="chatgpt_app")
        self.audit.append(
            "accounting.unavailable",
            session.state,
            {"reason": session.accounting_note},
        )
        self.store.save(session)
        return session

    def accept_plan(self, plan: PlanProposal) -> AppSession:
        session = self.store.load()
        if session.state != TaskState.PLANNING:
            raise AppWorkflowError("plan can only be accepted while PLANNING")
        session.contract = build_contract(
            session.request,
            plan,
            repository=session.repository.repository,
            base_branch=session.repository.base_branch,
            base_sha=session.repository.base_sha,
            config=self.config,
            project_profile=(
                ".codex-auto/project.yml"
                if ".codex-auto/project.yml" in session.repository.tree_paths
                else None
            ),
        )
        self._transition(session, TaskState.PLANNED, base_sha=session.contract.base_sha)
        self.audit.append(
            "contract.validated",
            session.state,
            session.contract.model_dump(mode="json"),
        )
        self.store.save(session)
        return session

    def begin_implementation(self) -> AppSession:
        session = self.store.load()
        if session.state != TaskState.PLANNED or session.contract is None:
            raise AppWorkflowError("implementation can only start after a validated plan")
        branch = self._branch_name(self.config.github.feature_branch_prefix, session.task_id)
        self.github.create_feature_branch(branch, session.contract.base_sha)
        session.feature_branch = branch
        self._transition(session, TaskState.IMPLEMENTING, branch=branch)
        self.store.save(session)
        return session

    def record_pull_request(self, number: int) -> AppSession:
        session = self.store.load()
        if session.state != TaskState.IMPLEMENTING or session.contract is None:
            raise AppWorkflowError("PR evidence can only be recorded after implementation starts")
        verification = self.github.run_verification(session.contract.verification)
        session.pull_request_evidence = self.github.collect_pull_request_evidence(
            number, verification
        )
        self._transition(
            session,
            TaskState.PR_OPEN,
            number=number,
            url=session.pull_request_evidence.url,
        )
        self.audit.append(
            "github.evidence.collected",
            session.state,
            session.pull_request_evidence.model_dump(mode="json"),
        )
        self.store.save(session)
        return session

    def begin_review(self) -> AppSession:
        session = self.store.load()
        if session.pull_request_evidence is None:
            raise AppWorkflowError("PR evidence is required before review")
        self._transition(
            session,
            TaskState.REVIEWING,
            head_sha=session.pull_request_evidence.head_sha,
        )
        self.store.save(session)
        return session

    def submit_review(self, review: ReviewResult) -> AppSession:
        session = self.store.load()
        if session.state != TaskState.REVIEWING:
            raise AppWorkflowError("review can only be submitted while REVIEWING")
        if session.contract is None or session.pull_request_evidence is None:
            raise AppWorkflowError("contract and PR evidence are required")
        validate_review(session.contract, session.pull_request_evidence, review)
        session.review = review
        self.audit.append(
            "review.completed",
            session.state,
            review.model_dump(mode="json"),
        )
        if review.decision == ReviewDecision.APPROVED:
            validate_evidence(session.contract, session.pull_request_evidence, self.config)
            self._transition(session, TaskState.MERGE_READY, human_merge_required=True)
            self.audit.append(
                "human_merge_gate.reached",
                session.state,
                {"pull_request_url": session.pull_request_evidence.url},
            )
        elif review.decision == ReviewDecision.CHANGES_REQUESTED:
            self._transition(session, TaskState.CHANGES_REQUESTED)
        else:
            session.blocked_reason = review.merge_recommendation
            self._transition(session, TaskState.BLOCKED, reason=review.merge_recommendation)
        self.store.save(session)
        return session

    def begin_fix(self) -> AppSession:
        session = self.store.load()
        if session.state != TaskState.CHANGES_REQUESTED:
            raise AppWorkflowError("fix can only start after CHANGES_REQUESTED")
        if session.fix_cycles >= self.config.policy.max_fix_cycles:
            reason = f"maximum fix cycles reached ({self.config.policy.max_fix_cycles})"
            session.blocked_reason = reason
            self._transition(session, TaskState.BLOCKED, reason=reason)
        else:
            session.fix_cycles += 1
            self._transition(session, TaskState.FIXING, cycle=session.fix_cycles)
        self.store.save(session)
        return session

    def record_fix(self, number: int) -> AppSession:
        session = self.store.load()
        if session.state != TaskState.FIXING or session.contract is None:
            raise AppWorkflowError("fix evidence can only be recorded while FIXING")
        verification = self.github.run_verification(session.contract.verification)
        session.pull_request_evidence = self.github.collect_pull_request_evidence(
            number, verification
        )
        self._transition(
            session,
            TaskState.REVIEWING,
            cycle=session.fix_cycles,
            head_sha=session.pull_request_evidence.head_sha,
        )
        self.audit.append(
            "fix.evidence.collected",
            session.state,
            session.pull_request_evidence.model_dump(mode="json"),
        )
        self.store.save(session)
        return session

    @staticmethod
    def result(session: AppSession) -> OrchestrationResult:
        return OrchestrationResult(
            task_id=session.task_id,
            state=session.state,
            contract=session.contract,
            pull_request_url=(
                None if session.pull_request_evidence is None else session.pull_request_evidence.url
            ),
            pull_request_number=(
                None
                if session.pull_request_evidence is None
                else session.pull_request_evidence.number
            ),
            review=session.review,
            fix_cycles=session.fix_cycles,
            usage=[],
            estimated_cost_usd="0",
            human_action_required=(
                "Review repository gates and merge the pull request manually."
                if session.state == TaskState.MERGE_READY
                else None
            ),
            blocked_reason=session.blocked_reason,
        )


def write_session_packet(session: AppSession, destination: str | Path) -> None:
    """Write the current App handoff packet without any hidden model call."""

    packet = {
        "task_id": session.task_id,
        "state": session.state.value,
        "request": session.request.model_dump(mode="json"),
        "repository": session.repository.model_dump(mode="json"),
        "contract": None if session.contract is None else session.contract.model_dump(mode="json"),
        "pull_request_evidence": (
            None
            if session.pull_request_evidence is None
            else session.pull_request_evidence.model_dump(mode="json")
        ),
        "review": None if session.review is None else session.review.model_dump(mode="json"),
        "feature_branch": session.feature_branch,
        "fix_cycles": session.fix_cycles,
        "blocked_reason": session.blocked_reason,
        "accounting_note": session.accounting_note,
    }
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(packet, indent=2, ensure_ascii=False), encoding="utf-8")
