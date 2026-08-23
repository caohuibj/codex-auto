from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from codex_auto.audit import JsonlAuditLog
from codex_auto.config import AppConfig
from codex_auto.models import (
    AcceptanceCriterion,
    CheckEvidence,
    CriterionAssessment,
    FileSnapshot,
    ImplementationProposal,
    PlanProposal,
    PullRequestEvidence,
    RepositorySnapshot,
    ReviewDecision,
    ReviewFinding,
    ReviewResult,
    TaskContract,
    TaskRequest,
    UsageRecord,
    VerificationResult,
    VerificationStatus,
)

BASE_SHA = "a" * 40
HEAD_ONE = "b" * 40
HEAD_TWO = "c" * 40


def make_config(max_fix_cycles: int = 2) -> AppConfig:
    return AppConfig.model_validate(
        {
            "providers": {"openai": {"type": "openai", "api_key_env": "OPENAI_API_KEY"}},
            "routing": {
                "planning": {"model": "sol-model"},
                "implementation": {"model": "luna-model"},
                "review": {"model": "sol-model"},
                "fix": {"model": "luna-model"},
            },
            "github": {
                "repository": "owner/repo",
                "base_branch": "main",
                "verification_commands": {"unit": ["pytest", "-q"]},
            },
            "policy": {"max_fix_cycles": max_fix_cycles, "human_merge_required": True},
            "cost": {
                "models": {
                    "sol-model": {
                        "input_per_million": "1",
                        "cached_input_per_million": "0.1",
                        "output_per_million": "2",
                    },
                    "luna-model": {
                        "input_per_million": "0.2",
                        "cached_input_per_million": "0.02",
                        "output_per_million": "0.4",
                    },
                }
            },
        }
    )


def make_app_config(max_fix_cycles: int = 2) -> AppConfig:
    raw = make_config(max_fix_cycles).model_dump(mode="json")
    raw["providers"] = {"chatgpt_app": {"type": "chatgpt_app", "api_key_env": None, "store": False}}
    for route in raw["routing"].values():
        route["provider"] = "chatgpt_app"
    return AppConfig.model_validate(raw)


def make_request() -> TaskRequest:
    return TaskRequest(
        task_id="TASK-001",
        title="Implement requested feature",
        objective="Implement one bounded feature with tests.",
        in_scope=["Add the feature"],
        out_of_scope=["Do not change deployment"],
        context_paths=["src/**/*.py"],
        required_verification=["unit"],
    )


def make_plan() -> PlanProposal:
    return PlanProposal(
        objective="Implement one bounded feature with tests.",
        in_scope=["Add the feature"],
        out_of_scope=["Do not change deployment"],
        architecture_constraints=["Preserve public interfaces"],
        implementation_requirements=["Add a tested implementation"],
        acceptance_criteria=[
            AcceptanceCriterion(
                id="AC-01",
                condition="Feature returns the expected value",
                evidence_required="Passing unit test",
            )
        ],
        verification=["unit"],
        expected_deliverables=["Feature branch and pull request"],
        escalation_conditions=["Repository contradicts the contract"],
    )


def make_contract() -> TaskContract:
    return TaskContract(
        task_id="TASK-001",
        title="Implement requested feature",
        target_repository="owner/repo",
        base_branch="main",
        base_sha=BASE_SHA,
        protocol_version="v1",
        **make_plan().model_dump(),
    )


def make_implementation(message: str = "feat: implement feature") -> ImplementationProposal:
    return ImplementationProposal(
        summary="Implement the feature",
        unified_diff=(
            "diff --git a/src/feature.py b/src/feature.py\n"
            "--- a/src/feature.py\n"
            "+++ b/src/feature.py\n"
            "@@ -1 +1 @@\n"
            "-OLD = 1\n"
            "+NEW = 2\n"
        ),
        commit_message=message,
        verification_notes=[],
    )


def make_review(decision: ReviewDecision, head_sha: str) -> ReviewResult:
    if decision == ReviewDecision.APPROVED:
        findings: list[ReviewFinding] = []
        status = "PASS"
        recommendation = "Ready for human merge."
    elif decision == ReviewDecision.CHANGES_REQUESTED:
        findings = [
            ReviewFinding(
                id="BLOCKER-01",
                severity="blocking",
                criterion_id="AC-01",
                location="src/feature.py",
                issue="Expected edge case is missing",
                evidence="The PR diff has no edge-case branch",
                required_change="Handle the edge case",
                acceptance_condition="Unit test covers the edge case",
            )
        ]
        status = "FAIL"
        recommendation = "Fix BLOCKER-01."
    else:
        findings = []
        status = "UNVERIFIED"
        recommendation = "Required repository evidence is unavailable."
    return ReviewResult(
        decision=decision,
        task_id="TASK-001",
        base_sha=BASE_SHA,
        head_sha=head_sha,
        criteria=[
            CriterionAssessment(
                criterion_id="AC-01", status=status, evidence="Reviewed actual diff and tests"
            )
        ],
        findings=findings,
        merge_recommendation=recommendation,
    )


class MockResponsesClient:
    def __init__(self, outputs: Sequence[BaseModel]) -> None:
        self.outputs = list(outputs)
        self.phases: list[str] = []

    def complete(
        self,
        *,
        phase: str,
        route: Any,
        instructions: str,
        input_data: dict[str, Any],
        output_type: type[BaseModel],
        metadata: dict[str, str],
    ) -> tuple[Any, UsageRecord]:
        self.phases.append(phase)
        output = self.outputs.pop(0)
        assert isinstance(output, output_type)
        return output, UsageRecord(
            phase=phase,
            provider="openai",
            model=route.model,
            response_id=f"response-{len(self.phases)}",
            input_tokens=100,
            cached_input_tokens=20,
            output_tokens=10,
            total_tokens=110,
        )


class MockGitHubAdapter:
    def __init__(self, verification_status: VerificationStatus = VerificationStatus.PASS) -> None:
        self.verification_status = verification_status
        self.commit_count = 0
        self.branch: str | None = None
        self.calls: list[str] = []

    def snapshot(self, context_paths: list[str]) -> RepositorySnapshot:
        self.calls.append("snapshot")
        return RepositorySnapshot(
            repository="owner/repo",
            base_branch="main",
            base_sha=BASE_SHA,
            files=[FileSnapshot(path="src/feature.py", content="OLD = 1\n")],
            tree_paths=["src/feature.py", "tests/test_feature.py"],
        )

    def create_feature_branch(self, branch: str, base_sha: str) -> None:
        assert base_sha == BASE_SHA
        self.branch = branch
        self.calls.append("create_branch")

    def apply_proposal(self, branch: str, proposal: ImplementationProposal) -> list[str]:
        assert branch == self.branch
        assert proposal.unified_diff
        self.calls.append("apply")
        return ["src/feature.py"]

    def run_verification(self, names: list[str]) -> list[VerificationResult]:
        self.calls.append("verify")
        assert names == ["unit"]
        return [
            VerificationResult(
                name="unit",
                command="pytest -q",
                status=self.verification_status,
                exit_code=0 if self.verification_status == VerificationStatus.PASS else 1,
                output="mock output",
            )
        ]

    def commit_and_push(self, branch: str, message: str, paths: list[str]) -> str:
        self.calls.append("commit_push")
        self.commit_count += 1
        return HEAD_ONE if self.commit_count == 1 else HEAD_TWO

    def open_or_update_pull_request(
        self,
        branch: str,
        contract: TaskContract,
        verification: list[VerificationResult],
    ) -> tuple[int, str]:
        self.calls.append("open_pr")
        return 7, "https://github.com/owner/repo/pull/7"

    def collect_pull_request_evidence(
        self, number: int, verification: list[VerificationResult]
    ) -> PullRequestEvidence:
        self.calls.append("collect_evidence")
        return PullRequestEvidence(
            number=number,
            url="https://github.com/owner/repo/pull/7",
            base_branch="main",
            base_sha=BASE_SHA,
            head_branch=self.branch or "codex-auto/task-001",
            head_sha=HEAD_ONE if self.commit_count <= 1 else HEAD_TWO,
            diff="diff --git a/src/feature.py b/src/feature.py\n+NEW = 2\n",
            checks=[CheckEvidence(name="ci", status="completed", conclusion="success")],
            local_verification=verification,
        )


def make_audit(tmp_path: Path) -> JsonlAuditLog:
    return JsonlAuditLog(tmp_path / "audit.jsonl", "TASK-001")
