import json

from codex_auto.audit import JsonlAuditLog
from codex_auto.cost import CostLedger
from codex_auto.models import TaskState, UsageRecord

from .helpers import make_config


def test_audit_log_is_structured_and_redacts_secrets(tmp_path):
    path = tmp_path / "events.jsonl"
    audit = JsonlAuditLog(path, "TASK-001")

    audit.append(
        "example",
        TaskState.REQUESTED,
        {"api_key": "secret-value", "header": "Bearer secret-token", "safe": "visible"},
    )

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["sequence"] == 1
    assert data["payload"]["api_key"] == "[REDACTED]"
    assert data["payload"]["header"] == "Bearer [REDACTED]"
    assert data["payload"]["safe"] == "visible"


def test_cost_ledger_separates_cached_input_tokens():
    ledger = CostLedger(make_config().cost)
    usage = UsageRecord(
        phase="planning",
        provider="openai",
        model="sol-model",
        response_id="response-1",
        input_tokens=1_000_000,
        cached_input_tokens=250_000,
        output_tokens=100_000,
        total_tokens=1_100_000,
    )

    recorded = ledger.record(usage)

    assert recorded.estimated_cost_usd == "0.975"
    assert ledger.total_usd == "0.975"
