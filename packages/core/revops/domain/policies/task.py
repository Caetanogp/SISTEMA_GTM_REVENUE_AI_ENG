"""Task proposal invariants that must hold before a write can be approved."""

from __future__ import annotations

from datetime import datetime, timedelta

from revops.domain.errors import PolicyViolationError

_MAX_DUE_HORIZON = timedelta(days=30)


def validate_due_at(due_at: datetime, now: datetime) -> None:
    if due_at <= now:
        raise PolicyViolationError("task due_at must be in the future")
    if due_at > now + _MAX_DUE_HORIZON:
        raise PolicyViolationError("task due_at must be no more than 30 days in the future")
