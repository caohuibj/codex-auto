"""Trusted Task Contract construction and deterministic gates."""

from __future__ import annotations

from codex_auto.config import AppConfig
from codex_auto.models import (
    ChangeEvidence,
    PlanProposal,
    ReviewDecision,
    ReviewResult,
    TaskContract,
    TaskRequest,
    VerificationStatus,
)


class ContractViolation(ValueError):
    pass


class EvidenceGateViolation(ValueError):
    pass


def validate_change_identity(
    contract: TaskContract,
    evidence: ChangeEvidence,
    expected_head_branch: str,
) -> None:
    errors: list[str] = []
    if evidence.base_branch != contract.base_branch:
        errors.append(
            f"change base branch {evidence.base_branch!r} != contract {contract.base_branch!r}"
        )
    if evidence.base_sha != contract.base_sha:
        errors.append(f"change merge base {evidence.base_sha} != contract base {contract.base_sha}")
    if evidence.head_branch != expected_head_branch:
        errors.append(
            f"change head branch {evidence.head_branch!r} != task branch {expected_head_branch!r}"
        )
    if errors:
        raise EvidenceGateViolation("; ".join(errors))


def build_contract(
    request: TaskRequest,
    plan: PlanProposal,
    *,
    repository: str,
    base_branch: str,
    base_sha: str,
    config: AppConfig,
    project_profile: str | None = None,
) -> TaskContract:
    missing_in_scope = sorted(set(request.in_scope) - set(plan.in_scope))
    missing_out_scope = sorted(set(request.out_of_scope) - set(plan.out_of_scope))
    if missing_in_scope:
        raise ContractViolation(f"plan dropped human in-scope items: {missing_in_scope}")
    if missing_out_scope:
        raise ContractViolation(f"plan dropped human out-of-scope items: {missing_out_scope}")

    known_verification = set(config.repository.verification_commands)
    unknown = sorted(set(plan.verification) - known_verification)
    if unknown:
        raise ContractViolation(f"plan requested unconfigured verification checks: {unknown}")
    missing_required = sorted(set(request.required_verification) - set(plan.verification))
    if missing_required:
        raise ContractViolation(f"plan omitted required verification checks: {missing_required}")

    return TaskContract(
        task_id=request.task_id,
        title=request.title,
        target_repository=repository,
        base_branch=base_branch,
        base_sha=base_sha,
        protocol_version=config.policy.protocol_version,
        project_profile=project_profile,
        **plan.model_dump(),
    )


def validate_evidence(
    contract: TaskContract,
    evidence: ChangeEvidence,
    config: AppConfig,
    expected_head_branch: str,
) -> None:
    validate_change_identity(contract, evidence, expected_head_branch)
    errors: list[str] = []
    if not evidence.diff.strip():
        errors.append("change diff is empty")

    verification_by_name = {result.name: result for result in evidence.local_verification}
    for name in contract.verification:
        result = verification_by_name.get(name)
        if result is None:
            errors.append(f"required verification {name!r} has no result")
        elif result.status != VerificationStatus.PASS:
            errors.append(f"required verification {name!r} is {result.status.value}")

    checks_by_name = {
        check.name: check for check in ([] if evidence.remote is None else evidence.remote.checks)
    }
    successful = {"success", "successful"}
    required_checks = [] if config.github is None else config.github.required_checks
    for name in required_checks:
        check = checks_by_name.get(name)
        if check is None:
            errors.append(f"required CI check {name!r} is missing")
            continue
        conclusion = (check.conclusion or check.status).lower()
        if conclusion not in successful:
            errors.append(f"required CI check {name!r} is {conclusion!r}")

    if errors:
        raise EvidenceGateViolation("; ".join(errors))


def validate_review(contract: TaskContract, evidence: ChangeEvidence, review: ReviewResult) -> None:
    errors: list[str] = []
    if review.task_id != contract.task_id:
        errors.append("review task ID does not match contract")
    if review.base_sha != contract.base_sha:
        errors.append("review base SHA does not match contract")
    if review.head_sha != evidence.head_sha:
        errors.append("review head SHA does not match current change evidence")

    expected_ids = {criterion.id for criterion in contract.acceptance_criteria}
    actual_ids = {assessment.criterion_id for assessment in review.criteria}
    if actual_ids != expected_ids:
        errors.append(
            f"review criterion coverage mismatch: expected={sorted(expected_ids)}, "
            f"actual={sorted(actual_ids)}"
        )
    if review.decision == ReviewDecision.APPROVED:
        failed = [item.criterion_id for item in review.criteria if item.status != "PASS"]
        if failed:
            errors.append(f"APPROVED review contains non-PASS criteria: {failed}")

    if errors:
        raise EvidenceGateViolation("; ".join(errors))
