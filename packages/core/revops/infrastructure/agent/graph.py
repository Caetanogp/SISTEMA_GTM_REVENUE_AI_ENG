"""LangGraph composition for the SPEC-001 agent runtime."""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph

from revops.infrastructure.agent.nodes import (
    AgentGraphDependencies,
    complete_runtime,
    execute_action,
    execute_runtime,
    load_context,
    propose_action,
    reserve_runtime,
    route_runtime,
    score_accounts,
    select_runtime,
)
from revops.infrastructure.agent.state import AgentGraphState


def build_agent_graph(deps: AgentGraphDependencies, checkpointer: AsyncPostgresSaver) -> Any:
    builder = StateGraph(AgentGraphState)

    if deps.tool_runtime is not None and deps.checkpointed_runtime:

        async def _select_runtime(state: AgentGraphState) -> dict[str, object]:
            return await select_runtime(state, deps)

        def _reserve_runtime(state: AgentGraphState) -> dict[str, object]:
            return reserve_runtime(state, deps)

        async def _execute_runtime(state: AgentGraphState) -> dict[str, object]:
            return await execute_runtime(state, deps)

        def _complete_runtime(state: AgentGraphState) -> dict[str, object]:
            return complete_runtime(state, deps)

        async def _execute_runtime_action(state: AgentGraphState) -> dict[str, object]:
            return await execute_action(state, deps)

        def _after_select(state: AgentGraphState) -> str:
            return "reserve_runtime" if state.get("runtime_lifecycle_step") == "selected" else END

        def _after_reserve(state: AgentGraphState) -> str:
            return "execute_runtime" if state.get("runtime_lifecycle_step") == "reserved" else END

        def _after_execute(state: AgentGraphState) -> str:
            return "complete_runtime" if state.get("runtime_lifecycle_step") == "executed" else END

        def _after_complete(state: AgentGraphState) -> str:
            if "pending_approval" in state:
                return "execute_action"
            if (
                state.get("runtime_selected_continue_after", False)
                and state.get("runtime_call_count", 0) < 5
            ):
                return "select_runtime"
            return END

        builder.add_node("select_runtime", _select_runtime)
        builder.add_node("reserve_runtime", _reserve_runtime)
        builder.add_node("execute_runtime", _execute_runtime)
        builder.add_node("complete_runtime", _complete_runtime)
        builder.add_node("execute_action", _execute_runtime_action)
        builder.add_edge(START, "select_runtime")
        builder.add_conditional_edges(
            "select_runtime",
            _after_select,
            {"reserve_runtime": "reserve_runtime", END: END},
        )
        builder.add_conditional_edges(
            "reserve_runtime",
            _after_reserve,
            {"execute_runtime": "execute_runtime", END: END},
        )
        builder.add_conditional_edges(
            "execute_runtime",
            _after_execute,
            {"complete_runtime": "complete_runtime", END: END},
        )
        builder.add_conditional_edges(
            "complete_runtime",
            _after_complete,
            {
                "select_runtime": "select_runtime",
                "execute_action": "execute_action",
                END: END,
            },
        )
        builder.add_edge("execute_action", END)
        return builder.compile(checkpointer=checkpointer, name=deps.graph_version)

    if deps.tool_runtime is not None:

        async def _route_runtime(state: AgentGraphState) -> dict[str, object]:
            return await route_runtime(state, deps)

        async def _execute_runtime_action(state: AgentGraphState) -> dict[str, object]:
            return await execute_action(state, deps)

        def _after_runtime(state: AgentGraphState) -> str:
            return "execute_action" if "pending_approval" in state else END

        builder.add_node("route_runtime", _route_runtime)
        builder.add_node("execute_action", _execute_runtime_action)
        builder.add_edge(START, "route_runtime")
        builder.add_conditional_edges(
            "route_runtime",
            _after_runtime,
            {"execute_action": "execute_action", END: END},
        )
        builder.add_edge("execute_action", END)
        return builder.compile(checkpointer=checkpointer, name=deps.graph_version)

    async def _load_context(state: AgentGraphState) -> dict[str, object]:
        return await load_context(state, deps)

    async def _score_accounts(state: AgentGraphState) -> dict[str, object]:
        return await score_accounts(state, deps)

    async def _propose_action(state: AgentGraphState) -> dict[str, object]:
        return await propose_action(state, deps)

    async def _execute_legacy_action(state: AgentGraphState) -> dict[str, object]:
        return await execute_action(state, deps)

    builder.add_node("load_context", _load_context)
    builder.add_node("score_accounts", _score_accounts)
    builder.add_node("propose_action", _propose_action)
    builder.add_node("execute_action", _execute_legacy_action)
    builder.add_edge(START, "load_context")
    builder.add_edge("load_context", "score_accounts")
    builder.add_edge("score_accounts", "propose_action")
    builder.add_edge("propose_action", "execute_action")
    builder.add_edge("execute_action", END)
    return builder.compile(checkpointer=checkpointer, name=deps.graph_version)
