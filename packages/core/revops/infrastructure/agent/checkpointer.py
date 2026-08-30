"""LangGraph Postgres checkpointer helpers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer


@asynccontextmanager
async def open_checkpointer(dsn: str) -> AsyncIterator[AsyncPostgresSaver]:
    serializer = JsonPlusSerializer(
        pickle_fallback=False,
        allowed_json_modules=True,
        allowed_msgpack_modules=True,
    )
    async with AsyncPostgresSaver.from_conn_string(dsn, serde=serializer) as checkpointer:
        await checkpointer.setup()
        yield checkpointer
