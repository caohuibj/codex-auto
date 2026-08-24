import pytest

from codex_auto.contract import (
    ContractViolation,
    EvidenceGateViolation,
    build_contract,
    validate_change_identity,
    validate_evidence,
    validate_review,
)
from codex_auto.models import ReviewDecision, VerificationStatus

from .helpers import (
    BASE_SHA,
    HEAD_ONE,
    MockRepositoryAdapter,
    make_config,
    make_contract,
    make_plan,
    make_request,
    make_review,
)


def test_contract_identity_comes_from_trusted_repository_data():
    contract = build_contract(
        make_request(),
        make_plan(),
        repository="owner/repo",
        base_branch="main",
        base_sha=BASE_SHA,
        config=make_config(),
    )

    assert contract.task_id == "TASK-001"
    assert contract.target_repository == "owner/repo"
    assert contract.base_sha == BASE_SHA


def test_contract_rejects_unknown_model_selected_verification():
    plan = make_plan().model_copy(update={"verification": ["unit", "deploy-production"]})

    with pytest.raises(ContractViolation, match="unconfigured verification"):
        build_contract(
            make_request(),
            plan,
            repository="owner/repo",
            base_branch="main",
            base_sha=BASE_SHA,
            config=make_config(),
        )


def test_contract_rejects_dropped_human_scope():
    plan = make_plan().model_copy(update={"out_of_scope": ["Something else"]})

    with pytest.raises(ContractViolation, match="dropped human out-of-scope"):
        build_contract(
            make_request(),
            plan,
            repository="owner/repo",
            base_branch="main",
            base_sha=BASE_SHA,
            config=make_config(),
        )


def test_review_must_cover_current_head_and_all_criteria():
    adapter = MockRepositoryAdapter()
    adapter.commit_count = 1
    evidence = adapter.collect_change_evidence(
        "codex-auto/task-001", make_contract(), adapter.run_verification(["unit"])
    )
    wrong_head_review = make_review(ReviewDecision.APPROVED, "d" * 40)

    with pytest.raises(EvidenceGateViolation, match="head SHA"):
        validate_review(
            build_contract(
                make_request(),
                make_plan(),
                repository="owner/repo",
                base_branch="main",
                base_sha=BASE_SHA,
                config=make_config(),
            ),
            evidence,
            wrong_head_review,
        )


def test_evidence_gate_requires_passing_contract_verification():
    adapter = MockRepositoryAdapter(VerificationStatus.NOT_RUN)
    adapter.commit_count = 1
    evidence = adapter.collect_change_evidence(
        "codex-auto/task-001", make_contract(), adapter.run_verification(["unit"])
    )
    contract = build_contract(
        make_request(),
        make_plan(),
        repository="owner/repo",
        base_branch="main",
        base_sha=BASE_SHA,
        config=make_config(),
    )

    with pytest.raises(EvidenceGateViolation, match="NOT_RUN"):
        validate_evidence(contract, evidence, make_config(), "codex-auto/task-001")

    assert evidence.head_sha == HEAD_ONE


def test_change_identity_requires_the_task_feature_branch():
    adapter = MockRepositoryAdapter()
    adapter.commit_count = 1
    evidence = adapter.collect_change_evidence(
        "codex-auto/task-001", make_contract(), adapter.run_verification(["unit"])
    )
    contract = build_contract(
        make_request(),
        make_plan(),
        repository="owner/repo",
        base_branch="main",
        base_sha=BASE_SHA,
        config=make_config(),
    )

    with pytest.raises(EvidenceGateViolation, match="head branch"):
        validate_change_identity(contract, evidence, "codex-auto/other-task")
