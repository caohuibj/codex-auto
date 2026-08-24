from codex_auto.models import ReviewDecision, TaskState, VerificationStatus
from codex_auto.orchestrator import Orchestrator

from .helpers import (
    HEAD_ONE,
    HEAD_TWO,
    MockRepositoryAdapter,
    MockResponsesClient,
    make_audit,
    make_config,
    make_implementation,
    make_plan,
    make_request,
    make_review,
)


def test_happy_path_stops_at_human_merge_gate(tmp_path):
    client = MockResponsesClient(
        [make_plan(), make_implementation(), make_review(ReviewDecision.APPROVED, HEAD_ONE)]
    )
    repository = MockRepositoryAdapter()

    result = Orchestrator(make_config(), {"openai": client}, repository, make_audit(tmp_path)).run(
        make_request()
    )

    assert result.state == TaskState.INTEGRATION_READY
    assert result.change_url is None
    assert result.human_action_required is not None
    assert result.fix_cycles == 0
    assert client.phases == ["planning", "implementation", "review"]
    assert "merge" not in repository.calls
    assert result.estimated_cost_usd != "0"


def test_one_bounded_fix_cycle_then_approval(tmp_path):
    client = MockResponsesClient(
        [
            make_plan(),
            make_implementation(),
            make_review(ReviewDecision.CHANGES_REQUESTED, HEAD_ONE),
            make_implementation("fix: handle edge case"),
            make_review(ReviewDecision.APPROVED, HEAD_TWO),
        ]
    )
    github = MockRepositoryAdapter()

    result = Orchestrator(make_config(), {"openai": client}, github, make_audit(tmp_path)).run(
        make_request()
    )

    assert result.state == TaskState.INTEGRATION_READY
    assert result.fix_cycles == 1
    assert github.commit_count == 2
    assert client.phases == ["planning", "implementation", "review", "fix", "review"]


def test_max_fix_cycles_blocks_without_unbounded_retry(tmp_path):
    client = MockResponsesClient(
        [
            make_plan(),
            make_implementation(),
            make_review(ReviewDecision.CHANGES_REQUESTED, HEAD_ONE),
        ]
    )

    result = Orchestrator(
        make_config(max_fix_cycles=0),
        {"openai": client},
        MockRepositoryAdapter(),
        make_audit(tmp_path),
    ).run(make_request())

    assert result.state == TaskState.BLOCKED
    assert result.fix_cycles == 0
    assert result.blocked_reason == "maximum fix cycles reached (0)"
    assert client.phases == ["planning", "implementation", "review"]


def test_approval_cannot_bypass_failed_evidence(tmp_path):
    client = MockResponsesClient(
        [make_plan(), make_implementation(), make_review(ReviewDecision.APPROVED, HEAD_ONE)]
    )

    result = Orchestrator(
        make_config(),
        {"openai": client},
        MockRepositoryAdapter(VerificationStatus.FAIL),
        make_audit(tmp_path),
    ).run(make_request())

    assert result.state == TaskState.BLOCKED
    assert "required verification 'unit' is FAIL" in (result.blocked_reason or "")
