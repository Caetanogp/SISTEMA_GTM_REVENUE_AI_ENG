"""Domain errors. No dependency on any framework's exception hierarchy."""

from __future__ import annotations


class DomainError(Exception):
    """Base class for every domain-level error."""


class PolicyViolationError(DomainError):
    """Raised when a value or an action would break a deterministic business rule."""


class NotAuthorizedError(DomainError):
    """Raised when an actor lacks the scope or role required for an action."""


class InvalidTransitionError(DomainError):
    """Raised when an entity is asked to move into a state it cannot reach from its current one."""
