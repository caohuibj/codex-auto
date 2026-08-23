from __future__ import annotations

import json

from codex_auto.app_workflow import AppSessionStore, ChatGPTAppWorkflow, write_session_packet
from codex_auto.audit import JsonlAuditLog
from codex_auto.models import ReviewDecision, TaskState

from .helpers import (
    HEAD_ONE,
    HEAD_TWO,
    MockGitHubAdapter,
    make_app_config,
    make_plan,
    make_request,
    make_review,
)


def make_workflow(tmp_path, *, max_fix_cycles: int = 2):
    github = MockGitHubAdapter()
    store = AppSessionStore(tmp_path / "session.json")
    audit = JsonlAuditLog(tmp_path / "audit.jsonl", "TASK-001")
    workflow = ChatGPTAppWorkflow(make_app_config(max_fix_cycles), github, store, audit)
    return workflow, github, store


def test_app_native_happy_path_uses_no_model_client_and_stops_for_human(tmp_path):
    workflow, github, store = make_workflow(tmp_path)

    assert workflow.start(make_request()).state == TaskState.PLANNING
    assert workflow.accept_plan(make_plan()).state == TaskState.PLANNED
    implementation = workflow.begin_implementation()
    assert implementation.state == TaskState.IMPLEMENTING
    assert implementation.feature_branch == "codex-auto/task-001"
    assert workflow.record_pull_request(7).state == TaskState.PR_OPEN
    assert workflow.begin_review().state == TaskState.REVIEWING
    session = workflow.submit_review(make_review(ReviewDecision.APPROVED, HEAD_ONE))
    result = workflow.result(session)

    assert result.state == TaskState.MERGE_READY
    assert result.human_action_required is not None
    assert result.usage == []
    assert result.estimated_cost_usd is None
    assert "merge" not in github.calls
    assert store.load().state == TaskState.MERGE_READY
    events = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert "accounting.unavailable" in events
    assert "human_merge_gate.reached" in events


def test_app_native_bounded_fix_then_review(tmp_path):
    workflow, github, _ = make_workflow(tmp_path, max_fix_cycles=1)
    workflow.start(make_request())
    workflow.accept_plan(make_plan())
    workflow.begin_implementation()
    workflow.record_pull_request(7)
    workflow.begin_review()
    changed = workflow.submit_review(make_review(ReviewDecision.CHANGES_REQUESTED, HEAD_ONE))
    assert changed.state == TaskState.CHANGES_REQUESTED
    assert workflow.begin_fix().state == TaskState.FIXING
    github.commit_count = 2
    assert workflow.record_fix(7).state == TaskState.REVIEWING
    approved = workflow.submit_review(make_review(ReviewDecision.APPROVED, HEAD_TWO))

    assert approved.state == TaskState.MERGE_READY
    assert approved.fix_cycles == 1


def test_app_native_fix_limit_is_terminal(tmp_path):
    workflow, _, _ = make_workflow(tmp_path, max_fix_cycles=0)
    workflow.start(make_request())
    workflow.accept_plan(make_plan())
    workflow.begin_implementation()
    workflow.record_pull_request(7)
    workflow.begin_review()
    workflow.submit_review(make_review(ReviewDecision.CHANGES_REQUESTED, HEAD_ONE))

    session = workflow.begin_fix()

    assert session.state == TaskState.BLOCKED
    assert session.fix_cycles == 0
    assert workflow.result(session).blocked_reason == "maximum fix cycles reached (0)"


def test_app_packet_contains_durable_handoff_without_credentials(tmp_path):
    workflow, _, _ = make_workflow(tmp_path)
    session = workflow.start(make_request())
    packet = tmp_path / "packet.json"

    write_session_packet(session, packet)

    data = json.loads(packet.read_text(encoding="utf-8"))
    assert data["state"] == "PLANNING"
    assert data["repository"]["base_sha"]
    assert "api_key" not in packet.read_text(encoding="utf-8").lower()
