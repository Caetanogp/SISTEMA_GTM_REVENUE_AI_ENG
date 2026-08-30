"""LangGraph composition for the SPEC-001 agent runtime."""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph

from revops.infrastructure.agent.nodes import (
    AgentGraphDependencies,
    execute_action,
    load_context,
    propose_action,
    score_accounts,
)
from revops.infrastructure.agent.state import AgentGraphState


def build_agent_graph(deps: AgentGraphDependencies, checkpointer: AsyncPostgresSaver) -> Any:
    builder = StateGraph(AgentGraphState)

    async def _load_context(state: AgentGraphState) -> dict[str, object]:
        return await load_context(state, deps)

    async def _score_accounts(state: AgentGraphState) -> dict[str, object]:
        return await score_accounts(state, deps)

    async def _propose_action(state: AgentGraphState) -> dict[str, object]:
        return await propose_action(state, deps)

    async def _execute_action(state: AgentGraphState) -> dict[str, object]:
        return await execute_action(state, deps)

    builder.add_node("load_context", _load_context)
    builder.add_node("score_accounts", _score_accounts)
    builder.add_node("propose_action", _propose_action)
    builder.add_node("execute_action", _execute_action)
    builder.add_edge(START, "load_context")
    builder.add_edge("load_context", "score_accounts")
    builder.add_edge("score_accounts", "propose_action")
    builder.add_edge("propose_action", "execute_action")
    builder.add_edge("execute_action", END)
    return builder.compile(checkpointer=checkpointer, name=deps.graph_version)
