"""Strict domain models shared across orchestration boundaries."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TaskState(StrEnum):
    REQUESTED = "REQUESTED"
    PLANNING = "PLANNING"
    PLANNED = "PLANNED"
    IMPLEMENTING = "IMPLEMENTING"
    PR_OPEN = "PR_OPEN"
    REVIEWING = "REVIEWING"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    FIXING = "FIXING"
    MERGE_READY = "MERGE_READY"
    BLOCKED = "BLOCKED"


class ReviewDecision(StrEnum):
    APPROVED = "APPROVED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    BLOCKED = "BLOCKED"


class VerificationStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_RUN = "NOT_RUN"
    NOT_APPLICABLE = "N/A"


class TaskRequest(StrictModel):
    task_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")
    title: str = Field(min_length=3, max_length=120)
    objective: str = Field(min_length=10)
    in_scope: list[str] = Field(min_length=1)
    out_of_scope: list[str] = Field(min_length=1)
    context_paths: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    required_verification: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)


class AcceptanceCriterion(StrictModel):
    id: str = Field(pattern=r"^AC-[0-9]{2,}$")
    condition: str = Field(min_length=5)
    evidence_required: str = Field(min_length=3)


class PlanProposal(StrictModel):
    objective: str = Field(min_length=10)
    in_scope: list[str] = Field(min_length=1)
    out_of_scope: list[str] = Field(min_length=1)
    architecture_constraints: list[str] = Field(min_length=1)
    implementation_requirements: list[str] = Field(min_length=1)
    acceptance_criteria: list[AcceptanceCriterion] = Field(min_length=1)
    verification: list[str] = Field(min_length=1)
    expected_deliverables: list[str] = Field(min_length=1)
    escalation_conditions: list[str] = Field(min_length=1)

    @field_validator("acceptance_criteria")
    @classmethod
    def acceptance_ids_are_unique(
        cls, criteria: list[AcceptanceCriterion]
    ) -> list[AcceptanceCriterion]:
        ids = [criterion.id for criterion in criteria]
        if len(ids) != len(set(ids)):
            raise ValueError("acceptance criterion IDs must be unique")
        return criteria


class TaskContract(PlanProposal):
    task_id: str
    title: str
    target_repository: str
    base_branch: str
    base_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    protocol_version: str
    project_profile: str | None = None


class FileSnapshot(StrictModel):
    path: str
    content: str
    truncated: bool = False


class RepositorySnapshot(StrictModel):
    repository: str
    base_branch: str
    base_sha: str
    files: list[FileSnapshot]
    tree_paths: list[str]


class ImplementationProposal(StrictModel):
    summary: str = Field(min_length=3)
    unified_diff: str = Field(min_length=10)
    commit_message: str = Field(min_length=3, max_length=120)
    verification_notes: list[str]


class VerificationResult(StrictModel):
    name: str
    command: str
    status: VerificationStatus
    exit_code: int | None = None
    output: str = ""


class CheckEvidence(StrictModel):
    name: str
    status: str
    conclusion: str | None = None
    url: str | None = None


class PullRequestEvidence(StrictModel):
    number: int = Field(ge=1)
    url: str
    base_branch: str
    base_sha: str
    head_branch: str
    head_sha: str
    diff: str
    checks: list[CheckEvidence] = Field(default_factory=list)
    local_verification: list[VerificationResult] = Field(default_factory=list)


class CriterionAssessment(StrictModel):
    criterion_id: str
    status: Literal["PASS", "FAIL", "UNVERIFIED"]
    evidence: str


class ReviewFinding(StrictModel):
    id: str
    severity: Literal["blocking", "non_blocking"]
    criterion_id: str | None
    location: str
    issue: str
    evidence: str
    required_change: str | None
    acceptance_condition: str | None


class ReviewResult(StrictModel):
    decision: ReviewDecision
    task_id: str
    base_sha: str
    head_sha: str
    criteria: list[CriterionAssessment]
    findings: list[ReviewFinding]
    merge_recommendation: str

    @model_validator(mode="after")
    def decision_matches_findings(self) -> ReviewResult:
        blocking = [finding for finding in self.findings if finding.severity == "blocking"]
        if self.decision == ReviewDecision.APPROVED and blocking:
            raise ValueError("APPROVED review cannot contain blocking findings")
        if self.decision == ReviewDecision.CHANGES_REQUESTED and not blocking:
            raise ValueError("CHANGES_REQUESTED review requires a blocking finding")
        return self


class UsageRecord(StrictModel):
    phase: str
    provider: str
    model: str
    response_id: str
    input_tokens: int = 0
    cached_input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: str | None = None


class OrchestrationResult(StrictModel):
    task_id: str
    state: TaskState
    contract: TaskContract | None = None
    pull_request_url: str | None = None
    pull_request_number: int | None = None
    review: ReviewResult | None = None
    fix_cycles: int = 0
    usage: list[UsageRecord] = Field(default_factory=list)
    estimated_cost_usd: str | None = None
    human_action_required: str | None = None
    blocked_reason: str | None = None


class AppSession(StrictModel):
    """Durable state for a workflow whose model runtime is the ChatGPT desktop app."""

    task_id: str
    state: TaskState = TaskState.REQUESTED
    request: TaskRequest
    repository: RepositorySnapshot
    contract: TaskContract | None = None
    pull_request_evidence: PullRequestEvidence | None = None
    review: ReviewResult | None = None
    feature_branch: str | None = None
    fix_cycles: int = 0
    blocked_reason: str | None = None
    accounting_note: str = (
        "ChatGPT App usage is charged to the signed-in plan allowance; exact per-phase tokens "
        "and cost are not exposed to this repository-local workflow."
    )


class AuditEvent(StrictModel):
    sequence: int = Field(ge=1)
    timestamp: datetime
    task_id: str
    event_type: str
    state: TaskState
    payload: dict[str, Any] = Field(default_factory=dict)
