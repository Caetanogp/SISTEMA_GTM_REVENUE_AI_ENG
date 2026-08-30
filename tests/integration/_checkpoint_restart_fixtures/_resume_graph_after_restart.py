"""Process 2 of the graph restart proof: recover the interrupt from Postgres and resume it."""

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
    )
else:
    from ._graph_runtime_common import (
        load_runtime_inputs,
        make_dependencies,
        make_session_factory,
    )
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from revops.application.dto import ApprovalDecisionInput, ApprovalDecisionType
from revops.infrastructure.agent.checkpointer import open_checkpointer
from revops.infrastructure.agent.graph import build_agent_graph
from revops.infrastructure.persistence.models import Task as TaskModel
from sqlalchemy import func, select


async def _main(thread_id: str, dsn: str) -> None:
    session_factory = make_session_factory(dsn)
    async with session_factory() as session:
        inputs = await load_runtime_inputs(session, thread_id)

    deps = make_dependencies(
        session_factory=session_factory,
        prioritization=inputs.prioritization,
    )
    async with open_checkpointer(dsn) as checkpointer:
        graph = build_agent_graph(deps, checkpointer)
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}

        before = await graph.aget_state(config)
        if before.next != ("execute_action",) or len(before.interrupts) != 1:
            print(f"NO PENDING INTERRUPT FOUND: next={before.next} interrupts={before.interrupts}")
            sys.exit(1)

        decision = ApprovalDecisionInput(
            decision=ApprovalDecisionType.APPROVE,
            organization_id=inputs.organization_id,
            decided_by=inputs.actor_id,
        )
        result = await graph.ainvoke(Command(resume=decision.model_dump(mode="json")), config)
        after = await graph.aget_state(config)
        if after.interrupts:
            print(f"GRAPH DID NOT COMPLETE: interrupts={after.interrupts}")
            sys.exit(1)
        if "task" not in result:
            print(f"NO TASK IN RESULT: {result}")
            sys.exit(1)

    async with session_factory() as session:
        task_count = await session.scalar(
            select(func.count())
            .select_from(TaskModel)
            .where(TaskModel.organization_id == inputs.organization_id)
        )
    if task_count != 1:
        print(f"UNEXPECTED TASK COUNT AFTER RESUME: {task_count}")
        sys.exit(1)

    print("RESUMED_CORRECTLY")


if __name__ == "__main__":
    thread_id_arg, dsn_arg = sys.argv[1], sys.argv[2]
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(_main(thread_id_arg, dsn_arg))
