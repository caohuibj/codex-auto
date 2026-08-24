import pytest

from codex_auto.models import TaskState
from codex_auto.state import InvalidTransition, TaskStateMachine, allowed_transitions


def test_state_machine_accepts_defined_path():
    state = TaskStateMachine()

    for target in (
        TaskState.PLANNING,
        TaskState.PLANNED,
        TaskState.IMPLEMENTING,
        TaskState.CHANGE_READY,
        TaskState.REVIEWING,
        TaskState.INTEGRATION_READY,
    ):
        state.transition(target)

    assert state.state == TaskState.INTEGRATION_READY
    assert allowed_transitions(TaskState.INTEGRATION_READY) == frozenset()


def test_state_machine_rejects_skipped_gate():
    state = TaskStateMachine()

    with pytest.raises(InvalidTransition, match="REQUESTED -> IMPLEMENTING"):
        state.transition(TaskState.IMPLEMENTING)
