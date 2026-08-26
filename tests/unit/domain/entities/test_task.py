from datetime import UTC, datetime
from uuid import uuid4

import pytest
from revops.domain.entities.task import Task, TaskStatus
from revops.domain.errors import InvalidTransitionError


def _make_task() -> Task:
    return Task(
        id=uuid4(),
        organization_id=uuid4(),
        owner_id=uuid4(),
        account_id=uuid4(),
        title="Follow up",
        due_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_starts_open() -> None:
    assert _make_task().status is TaskStatus.OPEN


def test_mark_done_from_open() -> None:
    task = _make_task()
    task.mark_done()
    assert task.status is TaskStatus.DONE


def test_cancel_from_open() -> None:
    task = _make_task()
    task.cancel()
    assert task.status is TaskStatus.CANCELLED


@pytest.mark.parametrize("transition", ["mark_done", "cancel"])
def test_terminal_states_reject_further_transitions(transition: str) -> None:
    task = _make_task()
    task.mark_done()
    with pytest.raises(InvalidTransitionError):
        getattr(task, transition)()


def test_cancelled_task_cannot_be_marked_done() -> None:
    task = _make_task()
    task.cancel()
    with pytest.raises(InvalidTransitionError):
        task.mark_done()
