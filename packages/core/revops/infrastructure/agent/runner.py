"""Lifecycle facade for the SPEC-001 agent graph."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from revops.application.ports import (
    AgentRunEventRecord,
    AgentRunJournal,
    AgentRunRecord,
    Clock,
    LLMGatewayError,
)
from revops.infrastructure.agent.state import AgentGraphState


class AgentGraphRuntime(Protocol):
    async def ainvoke(self, input: object, config: RunnableConfig) -> Any: ...

    async def aget_state(self, config: RunnableConfig) -> Any: ...


@dataclass(frozen=True, slots=True)
class AgentRunResult:
    run_id: UUID
    thread_id: str
    state: dict[str, object]


@dataclass(frozen=True, slots=True)
class AgentGraphRunner:
    graph: AgentGraphRuntime
    runs: AgentRunJournal
    clock: Clock
    graph_version: str
    prompt_version: str
    model_config_json: Mapping[str, object]

    @staticmethod
    def _elapsed_ms(started_at: datetime, ended_at: datetime) -> int:
        return max(int((ended_at - started_at).total_seconds() * 1000), 0)

    def _event_record(
        self,
        *,
        run_id: UUID,
        organization_id: UUID,
        event_type: str,
        occurred_at: datetime,
        metadata: Mapping[str, object] | None = None,
        error: str | None = None,
        latency_ms: int | None = None,
    ) -> AgentRunEventRecord:
        usage = metadata.get("llm_usage", {}) if metadata is not None else {}
        usage_config = usage.get("model_config_json") if isinstance(usage, Mapping) else None
        event_config = (
            dict(usage_config)
            if isinstance(usage_config, Mapping)
            else dict(self.model_config_json)
        )
        return AgentRunEventRecord(
            id=uuid4(),
            run_id=run_id,
            organization_id=organization_id,
            event_type=event_type,
            occurred_at=occurred_at,
            graph_version=self.graph_version,
            prompt_version=self.prompt_version,
            model_config_json=event_config,
            latency_ms=(
                latency_ms
                if latency_ms is not None
                else usage.get("latency_ms")
                if isinstance(usage, Mapping)
                else None
            ),
            input_tokens=usage.get("input_tokens") if isinstance(usage, Mapping) else None,
            output_tokens=usage.get("output_tokens") if isinstance(usage, Mapping) else None,
            token_cost_usd=usage.get("token_cost_usd") if isinstance(usage, Mapping) else None,
            error=error,
            metadata=metadata,
        )

    async def _record_event(
        self,
        *,
        run_id: UUID,
        organization_id: UUID,
        event_type: str,
        occurred_at: datetime,
        metadata: Mapping[str, object] | None = None,
        error: str | None = None,
        latency_ms: int | None = None,
    ) -> None:
        await self.runs.append(
            self._event_record(
                run_id=run_id,
                organization_id=organization_id,
                event_type=event_type,
                occurred_at=occurred_at,
                metadata=metadata,
                error=error,
                latency_ms=latency_ms,
            )
        )

    async def start(
        self,
        *,
        organization_id: UUID,
        actor_id: UUID,
        request_text: str,
        token_budget: int = 4096,
    ) -> AgentRunResult:
        run_id = uuid4()
        started_at = self.clock.now()
        run = AgentRunRecord(
            id=run_id,
            thread_id=str(run_id),
            organization_id=organization_id,
            requested_by=actor_id,
            request_text=request_text,
            graph_version=self.graph_version,
            prompt_version=self.prompt_version,
            model_config_json=dict(self.model_config_json),
            started_at=started_at,
        )
        state: AgentGraphState = {
            "organization_id": str(organization_id),
            "actor_id": str(actor_id),
            "request_text": request_text,
            "run_id": str(run_id),
            "thread_id": str(run_id),
            "graph_version": self.graph_version,
            "prompt_version": self.prompt_version,
            "model_config_json": dict(self.model_config_json),
            "token_budget": token_budget,
        }
        config: RunnableConfig = {"configurable": {"thread_id": str(run_id)}}
        started_event = self._event_record(
            run_id=run_id,
            organization_id=organization_id,
            event_type="started",
            occurred_at=started_at,
            metadata={"request_text": request_text},
        )
        await self.runs.start(run, started_event)
        try:
            await self.graph.ainvoke(state, config)
        except Exception as exc:
            ended_at = self.clock.now()
            failure_metadata: dict[str, object] = {
                "failure_kind": (
                    exc.kind.value if isinstance(exc, LLMGatewayError) else "runtime_error"
                ),
            }
            if isinstance(exc, LLMGatewayError):
                failure_metadata["provider"] = exc.provider
                failure_metadata["attempts"] = exc.attempts
            await self._record_event(
                run_id=run_id,
                organization_id=organization_id,
                event_type="failed",
                occurred_at=ended_at,
                metadata=failure_metadata,
                error=str(failure_metadata["failure_kind"]),
                latency_ms=self._elapsed_ms(started_at, ended_at),
            )
            raise
        snapshot = await self.graph.aget_state(config)
        ended_at = self.clock.now()
        if snapshot.interrupts:
            await self._record_event(
                run_id=run_id,
                organization_id=organization_id,
                event_type="interrupted",
                occurred_at=ended_at,
                metadata={"interrupt": snapshot.interrupts[0].value},
            )
        else:
            await self._record_event(
                run_id=run_id,
                organization_id=organization_id,
                event_type="completed",
                occurred_at=ended_at,
                metadata=dict(snapshot.values),
            )
        return AgentRunResult(run_id=run_id, thread_id=str(run_id), state=dict(snapshot.values))

    async def resume(self, *, thread_id: str, decision: dict[str, object]) -> AgentRunResult:
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        await self.graph.ainvoke(Command(resume=decision), config)
        snapshot = await self.graph.aget_state(config)
        ended_at = self.clock.now()
        if snapshot.interrupts:
            await self._record_event(
                run_id=UUID(thread_id),
                organization_id=UUID(str(snapshot.values.get("organization_id", thread_id))),
                event_type="interrupted",
                occurred_at=ended_at,
                metadata={"interrupt": snapshot.interrupts[0].value, **dict(snapshot.values)},
            )
        else:
            await self._record_event(
                run_id=UUID(thread_id),
                organization_id=UUID(str(snapshot.values.get("organization_id", thread_id))),
                event_type="completed",
                occurred_at=ended_at,
                metadata=dict(snapshot.values),
            )
        return AgentRunResult(
            run_id=UUID(thread_id),
            thread_id=thread_id,
            state=dict(snapshot.values),
        )
