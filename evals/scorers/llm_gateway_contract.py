"""Deterministic contract eval for the multi-provider LLM gateway."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel
from revops.application.dto import LLMFailureKind
from revops.application.ports import LLMGatewayError
from revops.infrastructure.llm.gateway import GatewayProviderConfig, RoutedLLMGateway
from revops.infrastructure.llm.providers import ProviderResponse, ProviderResponseError

DATASET_PATH = Path(__file__).resolve().parents[1] / "datasets" / "llm_gateway_contract.jsonl"


class ContractOutput(BaseModel):
    value: str


@dataclass
class _ScriptedProvider:
    provider: str
    model: str
    response: ProviderResponse | Exception
    calls: list[str]

    async def complete(self, *, prompt: str, response_model: type[BaseModel]) -> ProviderResponse:
        self.calls.append(prompt)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


@dataclass(frozen=True, slots=True)
class ScoreResult:
    total: int
    correct: int
    failed_ids: list[str]

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0


def load_cases() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in DATASET_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _response(model: str) -> ProviderResponse:
    return ProviderResponse(
        payload={"value": "ok"},
        model=model,
        input_tokens=10,
        output_tokens=5,
        cached_input_tokens=0,
        cache_write_tokens=0,
        request_id="eval-request",
    )


async def _score_case(case: dict[str, Any]) -> bool:
    primary = _ScriptedProvider(
        "openai",
        "gpt-5.6-terra",
        _provider_outcome(case.get("primary_error"), "gpt-5.6-terra"),
        [],
    )
    fallback = _ScriptedProvider(
        "anthropic",
        "claude-sonnet-5",
        _response("claude-sonnet-5"),
        [],
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200)))
    gateway = RoutedLLMGateway(
        providers=(primary, fallback),
        provider_configs=(
            GatewayProviderConfig("openai", "gpt-5.6-terra", "eval-key"),
            GatewayProviderConfig("anthropic", "claude-sonnet-5", "eval-key"),
        ),
        mode="live",
        max_retries=0,
        timeout_seconds=1,
        deadline_seconds=10,
        backoff_base_seconds=0.01,
        backoff_max_seconds=0.01,
        temperature=0,
        max_output_tokens=128,
        client=client,
    )
    try:
        try:
            result = await gateway.complete(
                prompt=str(case["prompt"]), response_model=ContractOutput
            )
        except LLMGatewayError as exc:
            return (
                case.get("expected_error") is not None
                and exc.kind.value == case["expected_error"]
                and not fallback.calls
            )
        expected_provider = case.get("expected_provider")
        return (
            result.usage.provider == expected_provider
            and result.usage.model_config_json["fallback_used"] == case["expected_fallback"]
            and primary.calls == [case["prompt"]]
            and (
                fallback.calls == [case["prompt"]]
                if case["expected_fallback"]
                else not fallback.calls
            )
            and case["language"] in {"en", "pt"}
        )
    finally:
        await client.aclose()


def _provider_outcome(error: object, model: str) -> ProviderResponse | Exception:
    if error is None:
        return _response(model)
    kind = LLMFailureKind(str(error))
    return ProviderResponseError(
        kind=kind,
        retryable=kind in {LLMFailureKind.SERVER, LLMFailureKind.RATE_LIMIT},
        request_id="eval-error",
    )


def score_llm_gateway_contract_dataset() -> ScoreResult:
    cases = load_cases()
    failed_ids = [str(case["id"]) for case in cases if not asyncio.run(_score_case(case))]
    return ScoreResult(
        total=len(cases), correct=len(cases) - len(failed_ids), failed_ids=failed_ids
    )
