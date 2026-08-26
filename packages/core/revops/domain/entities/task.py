"""Task: a next action for a user, with a small explicit state machine.

This is the entity SPEC-001's `create_task` tool writes, and the one HITL approval acts on.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from revops.domain.errors import InvalidTransitionError


class TaskStatus(StrEnum):
    OPEN = "open"
    DONE = "done"
    CANCELLED = "cancelled"


_VALID_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.OPEN: frozenset({TaskStatus.DONE, TaskStatus.CANCELLED}),
    TaskStatus.DONE: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}


@dataclass(slots=True)
class Task:
    id: UUID
    organization_id: UUID
    owner_id: UUID
    account_id: UUID
    title: str
    due_at: datetime
    status: TaskStatus = TaskStatus.OPEN

    def mark_done(self) -> None:
        self._transition_to(TaskStatus.DONE)

    def cancel(self) -> None:
        self._transition_to(TaskStatus.CANCELLED)

    def _transition_to(self, target: TaskStatus) -> None:
        allowed = _VALID_TRANSITIONS[self.status]
        if target not in allowed:
            raise InvalidTransitionError(f"cannot move a task from {self.status} to {target}")
        self.status = target
