"""Deterministic fake LLM gateway for tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeVar, cast

from pydantic import BaseModel

from revops.application.dto import LLMResult, LLMUsage

T = TypeVar("T")


@dataclass(slots=True)
class FakeLLMGateway:
    responses: list[object] = field(default_factory=list)
    usage: LLMUsage = field(
        default_factory=lambda: LLMUsage(
            provider="fake",
            model="fake",
            model_config_json={},
            input_tokens=0,
            output_tokens=0,
            token_cost_usd=0,
            latency_ms=0,
        )
    )
    calls: list[str] = field(default_factory=list)

    async def complete(self, *, prompt: str, response_model: type[T]) -> LLMResult[T]:
        self.calls.append(prompt)
        if not self.responses:
            raise RuntimeError("FakeLLMGateway has no scripted responses left")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if isinstance(response, BaseModel):
            output = cast(
                type[BaseModel],
                response_model,
            ).model_validate(response.model_dump(mode="json"))
        elif isinstance(response, dict):
            output = cast(type[BaseModel], response_model).model_validate(response)
        else:
            output = cast(type[BaseModel], response_model).model_validate(response)
        return LLMResult(output=cast(T, output), usage=self.usage)
