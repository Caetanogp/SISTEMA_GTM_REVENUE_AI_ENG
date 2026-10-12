"""Cross-platform event-loop policy helpers for PostgreSQL integration tests."""

from __future__ import annotations

import asyncio
from typing import cast

_WINDOWS_SELECTOR_POLICY = "WindowsSelectorEventLoopPolicy"


def windows_selector_event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    """Return psycopg's required Windows selector policy without assuming host stubs."""
    policy_factory = getattr(asyncio, _WINDOWS_SELECTOR_POLICY)
    return cast(asyncio.AbstractEventLoopPolicy, policy_factory())
