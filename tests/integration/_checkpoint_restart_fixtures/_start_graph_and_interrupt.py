"""Process 1 of the graph restart proof: run the real agent graph until the interrupt, then exit.

Invoked as: python _start_graph_and_interrupt.py <thread_id> <postgres_dsn>

Prints "INTERRUPTED" on success. The process exits normally; the next process must recover
exclusively from the checkpoint state persisted in Postgres.
"""

from __future__ import annotations

import asyncio
import sys

if __package__ in (None, ""):
    from pathlib import Path

    sys.path.append(str(Path(__file__).resolve().parents[3]))
    from tests.integration._checkpoint_restart_fixtures._graph_runtime_common import (
        load_runtime_inputs,
        make_dependencies,
        make_session_factory,
        seed_reference_data,
    )
else:
    from ._graph_runtime_common import (
        load_runtime_inputs,
        make_dependencies,
        make_session_factory,
        seed_reference_data,
    )
from langchain_core.runnables import RunnableConfig
from revops.infrastructure.agent.checkpointer import open_checkpointer
from revops.infrastructure.agent.graph import build_agent_graph
from revops.infrastructure.agent.state import AgentGraphState
from revops.infrastructure.persistence.models import Task as TaskModel
from sqlalchemy import func, select


async def _main(thread_id: str, dsn: str) -> None:
    session_factory = make_session_factory(dsn)
    async with session_factory() as session:
        await seed_reference_data(session, thread_id)
        inputs = await load_runtime_inputs(session, thread_id)

    deps = make_dependencies(
        session_factory=session_factory,
        prioritization=inputs.prioritization,
    )
    async with open_checkpointer(dsn) as checkpointer:
        graph = build_agent_graph(deps, checkpointer)
        state: AgentGraphState = {
            "organization_id": str(inputs.organization_id),
            "actor_id": str(inputs.actor_id),
            "request_text": inputs.request_text,
            "run_id": thread_id,
            "thread_id": thread_id,
            "graph_version": deps.graph_version,
            "prompt_version": deps.prompt_version,
            "model_config_json": {},
            "token_budget": 4096,
        }
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        await graph.ainvoke(state, config)
        snapshot = await graph.aget_state(config)
        if snapshot.next != ("execute_action",) or len(snapshot.interrupts) != 1:
            print(f"UNEXPECTED STATE: next={snapshot.next} interrupts={snapshot.interrupts}")
            sys.exit(1)
        if snapshot.interrupts[0].value["question"] != "approve_edit_reject":
            print(f"UNEXPECTED INTERRUPT: {snapshot.interrupts[0].value}")
            sys.exit(1)

    async with session_factory() as session:
        task_count = await session.scalar(
            select(func.count())
            .select_from(TaskModel)
            .where(TaskModel.organization_id == inputs.organization_id)
        )
    if task_count != 0:
        print(f"UNEXPECTED TASK COUNT BEFORE RESUME: {task_count}")
        sys.exit(1)

    print("INTERRUPTED")


if __name__ == "__main__":
    thread_id_arg, dsn_arg = sys.argv[1], sys.argv[2]
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(_main(thread_id_arg, dsn_arg))
