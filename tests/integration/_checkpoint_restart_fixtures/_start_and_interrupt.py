"""Process 1 of the checkpoint-restart proof: invoke a graph, hit interrupt, exit.

Invoked as: python _start_and_interrupt.py <thread_id> <postgres_dsn>

Prints "INTERRUPTED" on success. The process then exits normally - no state survives beyond
what AsyncPostgresSaver persisted to Postgres inside the `async with` block below.
"""

from __future__ import annotations

import asyncio
import sys
from typing import TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt


class _State(TypedDict):
    value: str


def _node_a(state: _State) -> dict[str, str]:
    result = interrupt({"question": "approve?", "proposed_action": "create_task"})
    return {"value": f"approved={result}"}


async def _main(thread_id: str, dsn: str) -> None:
    async with AsyncPostgresSaver.from_conn_string(dsn) as checkpointer:
        await checkpointer.setup()
        builder = StateGraph(_State)
        builder.add_node("node_a", _node_a)
        builder.add_edge(START, "node_a")
        builder.add_edge("node_a", END)
        graph = builder.compile(checkpointer=checkpointer)

        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        await graph.ainvoke({"value": "initial"}, config)

        state = await graph.aget_state(config)
        if state.next != ("node_a",) or len(state.interrupts) != 1:
            print(f"UNEXPECTED STATE: next={state.next} interrupts={state.interrupts}")
            sys.exit(1)

    print("INTERRUPTED")


if __name__ == "__main__":
    thread_id_arg, dsn_arg = sys.argv[1], sys.argv[2]
    if sys.platform == "win32":
        # psycopg async requires SelectorEventLoop; Windows defaults to ProactorEventLoop.
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(_main(thread_id_arg, dsn_arg))
