"""Dedicated, bounded runtime for one persisted inbound reply.

This module intentionally does not share the mutable SPEC-009/010 graph composition.  The
only graph operation is analysis, and every checkpoint value is a sanitized typed artifact.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from typing import Any, Protocol, TypedDict, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from psycopg import AsyncConnection
from psycopg.rows import dict_row

from revops.application.dto import ReplyRunConfig
from revops.application.ports import (
    AgentRunEventRecord,
    AgentRunJournal,
    Clock,
    ReplyUnitOfWorkFactory,
)
from revops.application.use_cases.reply import (
    ClassifiedReply,
    ClassifyReply,
    ReserveReplyClassification,
)

_ANALYSIS_TIMEOUT_SECONDS = 30
_ARTIFACT_LIMIT_BYTES = 128 * 1024
_GRAPH_VERSION = "reply-intelligence.v1"
_PROMPT_VERSION = "classify_reply.v1"


class ReplyGraphState(TypedDict, total=False):
    organization_id: str
    actor_id: str
    reply_id: str
    run_id: str
    thread_id: str
    graph_version: str
    prompt_version: str
    model_config_json: dict[str, object]
    lifecycle_step: str
    artifact_json: str
    failure_code: str
    usage: dict[str, object]


class ReplyGraphRuntime(Protocol):
    async def ainvoke(self, input: object, config: RunnableConfig, **kwargs: object) -> Any: ...

    async def aget_state(self, config: RunnableConfig) -> Any: ...


def _artifact_json(classified: ClassifiedReply) -> str:
    """Encode only the validated result and provider usage in a canonical bounded envelope."""
    usage = classified.usage
    usage_payload = usage.model_dump(mode="json") if hasattr(usage, "model_dump") else {}
    payload = {
        "result": classified.result.model_dump(mode="json"),
        "usage": usage_payload,
    }
    artifact = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    if len(artifact.encode("utf-8")) > _ARTIFACT_LIMIT_BYTES:
        raise ValueError("artifact_too_large")
    return artifact


@dataclass(frozen=True, slots=True)
class ReplyGraphDependencies:
    uow_factory: ReplyUnitOfWorkFactory
    classifier: object


def build_reply_graph(deps: ReplyGraphDependencies, checkpointer: AsyncPostgresSaver) -> Any:
    """Build the fixed select/reserve/execute/complete lifecycle with no LLM routing."""
    builder = StateGraph(ReplyGraphState)

    def select(state: ReplyGraphState) -> dict[str, object]:
        if (
            state.get("graph_version") != _GRAPH_VERSION
            or state.get("prompt_version") != _PROMPT_VERSION
        ):
            return {"lifecycle_step": "failed", "failure_code": "binding_mismatch"}
        return {"lifecycle_step": "selected"}

    def reserve(state: ReplyGraphState) -> dict[str, object]:
        # The transactional reservation precedes graph construction so its generated run id is
        # also the checkpoint thread id.  This node makes that binding durable in the artifact.
        if state.get("thread_id") != state.get("run_id"):
            return {"lifecycle_step": "failed", "failure_code": "binding_mismatch"}
        return {"lifecycle_step": "reserved"}

    async def execute(state: ReplyGraphState) -> dict[str, object]:
        try:
            classified = await ClassifyReply(deps.uow_factory, cast(Any, deps.classifier)).execute(
                organization_id=UUID(state["organization_id"]), reply_id=UUID(state["reply_id"])
            )
            artifact = _artifact_json(classified)
        except TimeoutError:
            return {"lifecycle_step": "failed", "failure_code": "timeout"}
        except ValueError as exc:
            return {"lifecycle_step": "refused", "failure_code": str(exc)}
        return {"lifecycle_step": "executed", "artifact_json": artifact}

    def complete(state: ReplyGraphState) -> dict[str, object]:
        artifact = state.get("artifact_json")
        if not isinstance(artifact, str) or len(artifact.encode("utf-8")) > _ARTIFACT_LIMIT_BYTES:
            return {"lifecycle_step": "failed", "failure_code": "artifact_too_large"}
        return {"lifecycle_step": "completed"}

    builder.add_node("select", select)
    builder.add_node("reserve", reserve)
    builder.add_node("execute", execute)
    builder.add_node("complete", complete)
    builder.add_edge(START, "select")
    builder.add_conditional_edges(
        "select",
        lambda state: "reserve" if state.get("lifecycle_step") == "selected" else END,
        {"reserve": "reserve", END: END},
    )
    builder.add_conditional_edges(
        "reserve",
        lambda state: "execute" if state.get("lifecycle_step") == "reserved" else END,
        {"execute": "execute", END: END},
    )
    builder.add_conditional_edges(
        "execute",
        lambda state: "complete" if state.get("lifecycle_step") == "executed" else END,
        {"complete": "complete", END: END},
    )
    builder.add_edge("complete", END)
    return builder.compile(checkpointer=checkpointer, name=_GRAPH_VERSION)


def _lock_key(organization_id: UUID, run_id: UUID) -> int:
    digest = sha256(f"{organization_id}:{run_id}".encode()).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


@asynccontextmanager
async def locked_reply_checkpointer(
    dsn: str, *, organization_id: UUID, run_id: UUID
) -> AsyncIterator[AsyncPostgresSaver | None]:
    """Hold one non-blocking PostgreSQL lock and checkpoint saver on one connection."""
    serializer = JsonPlusSerializer(
        pickle_fallback=False, allowed_json_modules=True, allowed_msgpack_modules=True
    )
    async with await AsyncConnection.connect(
        dsn, autocommit=True, row_factory=dict_row
    ) as connection:
        key = _lock_key(organization_id, run_id)
        acquired = await connection.execute("SELECT pg_try_advisory_lock(%s)", (key,))
        row = await acquired.fetchone()
        if row is None or not bool(row["pg_try_advisory_lock"]):
            yield None
            return
        try:
            checkpointer = AsyncPostgresSaver(connection, serde=serializer)
            await checkpointer.setup()
            yield checkpointer
        finally:
            await connection.execute("SELECT pg_advisory_unlock(%s)", (key,))


@dataclass(frozen=True, slots=True)
class ReplyRunResult:
    run_id: UUID
    thread_id: str
    outcome: str
    artifact: Mapping[str, object] | None = None
    failure_code: str | None = None


@dataclass(frozen=True, slots=True)
class ReplyGraphRunner:
    """Reserve once, then execute/reconcile one reply under an organization/run fence."""

    dsn: str
    dependencies: ReplyGraphDependencies
    journal: AgentRunJournal
    clock: Clock
    model_config_json: Mapping[str, object]

    async def classify(
        self, *, organization_id: UUID, actor_id: UUID, reply_id: UUID
    ) -> ReplyRunResult:
        reservation = await ReserveReplyClassification(
            self.dependencies.uow_factory, self.clock
        ).execute(
            organization_id=organization_id,
            actor_id=actor_id,
            reply_id=reply_id,
            run_config=ReplyRunConfig(
                graph_version=_GRAPH_VERSION,
                prompt_version=_PROMPT_VERSION,
                model_config_json=dict(self.model_config_json),
            ),
        )
        run_id = reservation.request.run_id
        async with asyncio.timeout(_ANALYSIS_TIMEOUT_SECONDS):
            async with locked_reply_checkpointer(
                self.dsn, organization_id=organization_id, run_id=run_id
            ) as checkpointer:
                if checkpointer is None:
                    return ReplyRunResult(run_id, str(run_id), "in_progress")
                graph = cast(ReplyGraphRuntime, build_reply_graph(self.dependencies, checkpointer))
                config: RunnableConfig = {"configurable": {"thread_id": str(run_id)}}
                snapshot = await graph.aget_state(config)
                values = dict(snapshot.values)
                existing_step = values.get("lifecycle_step")
                if existing_step == "reserved":
                    return ReplyRunResult(
                        run_id, str(run_id), "checkpoint_recovery_required", failure_code="reserved"
                    )
                if existing_step in {"completed", "failed", "refused"}:
                    result = self._result(run_id, values)
                else:
                    state: ReplyGraphState = {
                        "organization_id": str(organization_id),
                        "actor_id": str(actor_id),
                        "reply_id": str(reply_id),
                        "run_id": str(run_id),
                        "thread_id": str(run_id),
                        "graph_version": _GRAPH_VERSION,
                        "prompt_version": _PROMPT_VERSION,
                        "model_config_json": dict(self.model_config_json),
                    }
                    await graph.ainvoke(state, config, durability="sync")
                    result = self._result(run_id, dict((await graph.aget_state(config)).values))
                await self._append_terminal(organization_id, result)
                return result

    @staticmethod
    def _result(run_id: UUID, values: Mapping[str, object]) -> ReplyRunResult:
        step = str(values.get("lifecycle_step", "failed"))
        if step == "completed":
            artifact_json = values.get("artifact_json")
            if isinstance(artifact_json, str):
                return ReplyRunResult(run_id, str(run_id), "completed", json.loads(artifact_json))
        return ReplyRunResult(
            run_id,
            str(run_id),
            step,
            failure_code=str(values.get("failure_code", "invalid_artifact")),
        )

    async def _append_terminal(self, organization_id: UUID, result: ReplyRunResult) -> None:
        if result.outcome not in {"completed", "failed", "refused"}:
            return
        event_type = "completed" if result.outcome == "completed" else result.outcome
        metadata: dict[str, object] = {"outcome": result.outcome}
        if result.failure_code is not None:
            metadata["failure_code"] = result.failure_code
        usage = result.artifact.get("usage") if result.artifact is not None else None
        usage_mapping = usage if isinstance(usage, Mapping) else {}
        if usage_mapping:
            metadata["usage"] = dict(usage_mapping)
        usage_config = usage_mapping.get("model_config_json")
        event_config = (
            dict(usage_config) if isinstance(usage_config, Mapping) else self.model_config_json
        )
        await self.journal.append(
            AgentRunEventRecord(
                id=uuid5(NAMESPACE_URL, f"reply-terminal:{result.run_id}:{event_type}"),
                run_id=result.run_id,
                organization_id=organization_id,
                event_type=event_type,
                occurred_at=self.clock.now(),
                graph_version=_GRAPH_VERSION,
                prompt_version=_PROMPT_VERSION,
                model_config_json=event_config,
                latency_ms=_optional_int(usage_mapping.get("latency_ms")),
                input_tokens=_optional_int(usage_mapping.get("input_tokens")),
                output_tokens=_optional_int(usage_mapping.get("output_tokens")),
                token_cost_usd=_optional_decimal(usage_mapping.get("token_cost_usd")),
                metadata=metadata,
            )
        )


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _optional_decimal(value: object) -> Decimal | None:
    if isinstance(value, (str, int, float, Decimal)) and not isinstance(value, bool):
        return Decimal(str(value))
    return None
