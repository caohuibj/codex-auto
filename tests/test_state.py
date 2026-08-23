import pytest

from codex_auto.models import TaskState
from codex_auto.state import InvalidTransition, TaskStateMachine, allowed_transitions


def test_state_machine_accepts_defined_path():
    state = TaskStateMachine()

    for target in (
        TaskState.PLANNING,
        TaskState.PLANNED,
        TaskState.IMPLEMENTING,
        TaskState.PR_OPEN,
        TaskState.REVIEWING,
        TaskState.MERGE_READY,
    ):
        state.transition(target)

    assert state.state == TaskState.MERGE_READY
    assert allowed_transitions(TaskState.MERGE_READY) == frozenset()


def test_state_machine_rejects_skipped_gate():
    state = TaskStateMachine()

    with pytest.raises(InvalidTransition, match="REQUESTED -> IMPLEMENTING"):
        state.transition(TaskState.IMPLEMENTING)
