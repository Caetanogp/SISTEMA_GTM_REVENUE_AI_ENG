"""Process 2b of the graph restart proof: repeated resume calls do not duplicate the task."""

from __future__ import annotations

import asyncio
import sys
from contextlib import suppress
from datetime import timedelta
from pathlib import Path
from typing import cast
from uuid import UUID

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[3]))
    from tests.integration._checkpoint_restart_fixtures._graph_runtime_common import (
        _NOW,
        load_runtime_inputs,
        make_dependencies,
        make_session_factory,
    )
else:
    from ._graph_runtime_common import (
        _NOW,
        load_runtime_inputs,
        make_dependencies,
        make_session_factory,
    )
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from revops.application.dto import ApprovalDecisionInput, ApprovalDecisionType, CreateTaskDraft
from revops.infrastructure.agent.checkpointer import open_checkpointer
from revops.infrastructure.agent.graph import build_agent_graph
from revops.infrastructure.persistence.models import Task as TaskModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def _task_count(
    session_factory: async_sessionmaker[AsyncSession],
    organization_id: UUID,
) -> int | None:
    async with session_factory() as session:
        return cast(
            int | None,
            await session.scalar(
                select(func.count())
                .select_from(TaskModel)
                .where(TaskModel.organization_id == organization_id),
            ),
        )


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

        first_decision = ApprovalDecisionInput(
            decision=ApprovalDecisionType.APPROVE,
            organization_id=inputs.organization_id,
            decided_by=inputs.actor_id,
        )
        first = await graph.ainvoke(Command(resume=first_decision.model_dump(mode="json")), config)
        second = await graph.ainvoke(Command(resume=first_decision.model_dump(mode="json")), config)

        conflicting_decision = ApprovalDecisionInput(
            decision=ApprovalDecisionType.EDIT,
            organization_id=inputs.organization_id,
            decided_by=inputs.actor_id,
            edited=CreateTaskDraft(
                account_id=inputs.prioritization.task.account_id,
                title="Edited title",
                due_at=_NOW + timedelta(days=7),
            ),
        )
        with suppress(Exception):
            await graph.ainvoke(
                Command(resume=conflicting_decision.model_dump(mode="json")),
                config,
            )

        after = await graph.aget_state(config)
        if after.interrupts:
            print(f"GRAPH DID NOT COMPLETE: interrupts={after.interrupts}")
            sys.exit(1)
        if "task" not in first or "task" not in second:
            print(f"NO TASK IN RESULT: first={first} second={second}")
            sys.exit(1)
        if first["task"] != second["task"]:
            print(f"REPEATED RESUME CHANGED TASK: first={first['task']} second={second['task']}")
            sys.exit(1)

    task_count = await _task_count(session_factory, inputs.organization_id)
    if task_count != 1:
        print(f"UNEXPECTED TASK COUNT AFTER REPEATED RESUME: {task_count}")
        sys.exit(1)

    print("REPEATED_RESUME_IDEMPOTENT")


if __name__ == "__main__":
    thread_id_arg, dsn_arg = sys.argv[1], sys.argv[2]
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(_main(thread_id_arg, dsn_arg))
