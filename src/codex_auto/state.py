"""Explicit, fail-closed task state machine."""

from __future__ import annotations

from codex_auto.models import TaskState


class InvalidTransition(ValueError):
    """Raised when orchestration attempts an undefined state transition."""


_ALLOWED: dict[TaskState, set[TaskState]] = {
    TaskState.REQUESTED: {TaskState.PLANNING, TaskState.BLOCKED},
    TaskState.PLANNING: {TaskState.PLANNED, TaskState.BLOCKED},
    TaskState.PLANNED: {TaskState.IMPLEMENTING, TaskState.BLOCKED},
    TaskState.IMPLEMENTING: {TaskState.PR_OPEN, TaskState.BLOCKED},
    TaskState.PR_OPEN: {TaskState.REVIEWING, TaskState.BLOCKED},
    TaskState.REVIEWING: {
        TaskState.MERGE_READY,
        TaskState.CHANGES_REQUESTED,
        TaskState.BLOCKED,
    },
    TaskState.CHANGES_REQUESTED: {TaskState.FIXING, TaskState.BLOCKED},
    TaskState.FIXING: {TaskState.REVIEWING, TaskState.BLOCKED},
    TaskState.MERGE_READY: set(),
    TaskState.BLOCKED: set(),
}


class TaskStateMachine:
    def __init__(self) -> None:
        self._state = TaskState.REQUESTED

    @property
    def state(self) -> TaskState:
        return self._state

    def transition(self, target: TaskState) -> tuple[TaskState, TaskState]:
        source = self._state
        if target not in _ALLOWED[source]:
            raise InvalidTransition(f"invalid task transition: {source.value} -> {target.value}")
        self._state = target
        return source, target


def allowed_transitions(state: TaskState) -> frozenset[TaskState]:
    return frozenset(_ALLOWED[state])
