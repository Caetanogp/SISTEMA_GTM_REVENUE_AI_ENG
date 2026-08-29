"""Process 2 of the checkpoint-restart proof: a genuinely separate process, no shared memory
with _start_and_interrupt.py at all - it only knows the thread_id and the database.

Invoked as: python _resume_after_restart.py <thread_id> <postgres_dsn>

Prints "RESUMED_CORRECTLY" on success.
"""

from __future__ import annotations

import asyncio
import sys
from typing import TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class _State(TypedDict):
    value: str


def _node_a(state: _State) -> dict[str, str]:
    result = interrupt({"question": "approve?", "proposed_action": "create_task"})
    return {"value": f"approved={result}"}


async def _main(thread_id: str, dsn: str) -> None:
    async with AsyncPostgresSaver.from_conn_string(dsn) as checkpointer:
        builder = StateGraph(_State)
        builder.add_node("node_a", _node_a)
        builder.add_edge(START, "node_a")
        builder.add_edge("node_a", END)
        graph = builder.compile(checkpointer=checkpointer)

        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}

        # Discover the pending interrupt purely from persisted state - this process has no
        # in-memory knowledge of what happened in _start_and_interrupt.py.
        before = await graph.aget_state(config)
        if before.next != ("node_a",) or len(before.interrupts) != 1:
            print(f"NO PENDING INTERRUPT FOUND: next={before.next} interrupts={before.interrupts}")
            sys.exit(1)
        if before.interrupts[0].value.get("proposed_action") != "create_task":
            print(f"UNEXPECTED INTERRUPT PAYLOAD: {before.interrupts[0].value}")
            sys.exit(1)

        result = await graph.ainvoke(Command(resume=True), config)
        if result != {"value": "approved=True"}:
            print(f"UNEXPECTED RESULT: {result}")
            sys.exit(1)

        after = await graph.aget_state(config)
        if after.next != ():
            print(f"GRAPH NOT FINISHED: next={after.next}")
            sys.exit(1)

    print("RESUMED_CORRECTLY")


if __name__ == "__main__":
    thread_id_arg, dsn_arg = sys.argv[1], sys.argv[2]
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(_main(thread_id_arg, dsn_arg))
