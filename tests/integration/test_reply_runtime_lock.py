"""PostgreSQL evidence for the reply runtime's same-connection execution fence."""

from __future__ import annotations

import asyncio
from typing import cast
from uuid import uuid4

import pytest
from revops.infrastructure.agent.reply_runtime import locked_reply_checkpointer


@pytest.fixture(scope="session")
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    selector_policy = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if selector_policy is not None:
        return cast(asyncio.AbstractEventLoopPolicy, selector_policy())
    return asyncio.get_event_loop_policy()


async def test_reply_checkpoint_lock_is_nonblocking_and_uses_its_saver_connection(
    postgres_dsn: str,
) -> None:
    organization_id = uuid4()
    run_id = uuid4()

    async with locked_reply_checkpointer(
        postgres_dsn, organization_id=organization_id, run_id=run_id
    ) as first:
        assert first is not None
        assert first.conn is not None
        async with locked_reply_checkpointer(
            postgres_dsn, organization_id=organization_id, run_id=run_id
        ) as second:
            assert second is None

    async with locked_reply_checkpointer(
        postgres_dsn, organization_id=organization_id, run_id=run_id
    ) as released:
        assert released is not None
