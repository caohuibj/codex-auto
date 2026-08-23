from types import SimpleNamespace

from codex_auto.config import ModelRoute
from codex_auto.models import PlanProposal, ReviewResult
from codex_auto.responses import OpenAIResponsesClient

from .helpers import make_plan


class FakeResponses:
    def __init__(self) -> None:
        self.request = None

    def create(self, **request):
        self.request = request
        return SimpleNamespace(
            id="response-123",
            output_text=make_plan().model_dump_json(),
            usage=SimpleNamespace(
                input_tokens=100,
                output_tokens=25,
                total_tokens=125,
                input_tokens_details=SimpleNamespace(cached_tokens=40),
                output_tokens_details=SimpleNamespace(reasoning_tokens=5),
            ),
        )


def test_openai_adapter_requests_strict_schema_and_captures_usage():
    adapter = object.__new__(OpenAIResponsesClient)
    fake_responses = FakeResponses()
    adapter._client = SimpleNamespace(responses=fake_responses)
    adapter.provider_name = "openai"
    adapter.store = False

    output, usage = adapter.complete(
        phase="planning",
        route=ModelRoute(model="sol-model", reasoning_effort="high"),
        instructions="Plan",
        input_data={"task": "bounded"},
        output_type=PlanProposal,
        metadata={"task_id": "TASK-001"},
    )

    assert output == make_plan()
    assert fake_responses.request["parallel_tool_calls"] is False
    assert fake_responses.request["store"] is False
    assert fake_responses.request["text"]["format"]["type"] == "json_schema"
    assert fake_responses.request["text"]["format"]["strict"] is True
    assert set(fake_responses.request["text"]["format"]["schema"]["required"]) == {
        "objective",
        "in_scope",
        "out_of_scope",
        "architecture_constraints",
        "implementation_requirements",
        "acceptance_criteria",
        "verification",
        "expected_deliverables",
        "escalation_conditions",
    }
    assert usage.input_tokens == 100
    assert usage.cached_input_tokens == 40
    assert usage.reasoning_tokens == 5


def test_model_output_schemas_require_nullable_finding_fields():
    schema = ReviewResult.model_json_schema()
    finding = schema["$defs"]["ReviewFinding"]

    assert set(finding["required"]) == {
        "id",
        "severity",
        "criterion_id",
        "location",
        "issue",
        "evidence",
        "required_change",
        "acceptance_condition",
    }
    assert finding["additionalProperties"] is False
