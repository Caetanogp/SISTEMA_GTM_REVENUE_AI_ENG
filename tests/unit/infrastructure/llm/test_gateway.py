from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx
import pytest
from pydantic import BaseModel, SecretStr
from revops.application.dto import LLMFailureKind, LLMHealthStatus
from revops.application.ports import LLMGatewayError
from revops.infrastructure.llm.gateway import (
    GatewayProviderConfig,
    RoutedLLMGateway,
    build_live_gateway,
)
from revops.infrastructure.llm.pricing import (
    PRICING_CATALOG_VERSION,
    calculate_cost,
    get_model_price,
)
from revops.infrastructure.llm.providers import (
    AnthropicMessagesAdapter,
    OpenAIResponsesAdapter,
    ProviderResponse,
    ProviderResponseError,
)

from apps.api.settings import ApiSettings


class Answer(BaseModel):
    value: str


def _openai_payload() -> dict[str, Any]:
    return {
        "id": "resp_test",
        "model": "gpt-5.6-terra",
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": '{"value":"ok"}'}],
            }
        ],
        "usage": {
            "input_tokens": 100,
            "output_tokens": 20,
            "input_tokens_details": {"cached_tokens": 10},
        },
    }


def _anthropic_payload() -> dict[str, Any]:
    return {
        "id": "msg_test",
        "model": "claude-sonnet-5",
        "content": [{"type": "text", "text": '{"value":"ok"}'}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 100, "output_tokens": 20},
    }


@pytest.mark.parametrize(
    ("adapter_type", "payload", "url", "provider"),
    [
        (
            OpenAIResponsesAdapter,
            _openai_payload(),
            "https://api.openai.com/v1/responses",
            "openai",
        ),
        (
            AnthropicMessagesAdapter,
            _anthropic_payload(),
            "https://api.anthropic.com/v1/messages",
            "anthropic",
        ),
    ],
)
async def test_provider_adapters_send_strict_structured_requests(
    adapter_type: type[OpenAIResponsesAdapter | AnthropicMessagesAdapter],
    payload: dict[str, Any],
    url: str,
    provider: str,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=payload, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = adapter_type(
            client=client,
            api_key="secret-test-key",
            model="gpt-5.6-terra" if provider == "openai" else "claude-sonnet-5",
            max_output_tokens=2048,
            temperature=0,
        )
        result = await adapter.complete(
            prompt="Prioritize contas / prioritize accounts", response_model=Answer
        )

    assert result.payload == {"value": "ok"}
    assert result.input_tokens == 100
    assert result.output_tokens == 20
    assert requests[0].url == url
    body = requests[0].content.decode("utf-8")
    assert "secret-test-key" not in body
    if provider == "openai":
        assert '"store":false' in body
        assert '"json_schema"' in body
    else:
        assert "output_config" in body
        assert "anthropic-version" in requests[0].headers


async def test_provider_adapter_parses_bounded_retry_after() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            headers={"retry-after": "3.5", "x-request-id": "rate-limit-test"},
            json={"error": {"type": "rate_limit_error"}},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = OpenAIResponsesAdapter(
            client=client,
            api_key="secret-test-key",
            model="gpt-5.6-terra",
            max_output_tokens=2048,
            temperature=0,
        )
        with pytest.raises(ProviderResponseError) as raised:
            await adapter.complete(prompt="prompt", response_model=Answer)

    assert raised.value.retryable is True
    assert raised.value.retry_after_seconds == 3.5
    assert raised.value.request_id == "rate-limit-test"


@dataclass
class ScriptedAdapter:
    provider: str
    model: str
    responses: list[ProviderResponse | Exception]

    async def complete(self, *, prompt: str, response_model: type[BaseModel]) -> ProviderResponse:
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _response(provider: str, model: str) -> ProviderResponse:
    return ProviderResponse(
        payload={"value": "ok"},
        model=model,
        input_tokens=100,
        output_tokens=20,
        cached_input_tokens=0,
        cache_write_tokens=0,
        request_id="request-test",
    )


async def _no_sleep(_: float) -> None:
    return None


def _gateway(adapters: tuple[ScriptedAdapter, ...], client: httpx.AsyncClient) -> RoutedLLMGateway:
    return RoutedLLMGateway(
        providers=adapters,
        provider_configs=tuple(
            GatewayProviderConfig(provider=adapter.provider, model=adapter.model, api_key="secret")
            for adapter in adapters
        ),
        mode="live",
        max_retries=1,
        timeout_seconds=30,
        deadline_seconds=90,
        backoff_base_seconds=0.01,
        backoff_max_seconds=0.01,
        temperature=0,
        max_output_tokens=2048,
        client=client,
        sleep=_no_sleep,
        random_value=lambda: 0,
    )


async def test_transient_primary_failure_falls_back_and_records_health() -> None:
    primary = ScriptedAdapter(
        "openai",
        "gpt-5.6-terra",
        [ProviderResponseError(kind=LLMFailureKind.SERVER, retryable=True, request_id="r1")] * 2,
    )
    fallback = ScriptedAdapter(
        "anthropic",
        "claude-sonnet-5",
        [_response("anthropic", "claude-sonnet-5")],
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200)))
    gateway = _gateway((primary, fallback), client)

    result = await gateway.complete(prompt="prompt", response_model=Answer)

    assert result.output.value == "ok"
    assert result.usage.provider == "anthropic"
    assert result.usage.model_config_json["fallback_used"] is True
    assert gateway.health_snapshot().status is LLMHealthStatus.DEGRADED
    await client.aclose()


async def test_authentication_failure_does_not_fall_back() -> None:
    primary = ScriptedAdapter(
        "openai",
        "gpt-5.6-terra",
        [
            ProviderResponseError(
                kind=LLMFailureKind.AUTHENTICATION, retryable=False, request_id="r1"
            )
        ],
    )
    fallback = ScriptedAdapter(
        "anthropic", "claude-sonnet-5", [_response("anthropic", "claude-sonnet-5")]
    )
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200)))
    gateway = _gateway((primary, fallback), client)

    with pytest.raises(LLMGatewayError) as raised:
        await gateway.complete(prompt="prompt", response_model=Answer)

    assert raised.value.kind is LLMFailureKind.AUTHENTICATION
    assert fallback.responses
    await client.aclose()


def test_pricing_catalog_is_versioned_and_decimal() -> None:
    price = get_model_price("openai", "gpt-5.6-terra")
    assert PRICING_CATALOG_VERSION == "2026-09-13.v1"
    assert calculate_cost(
        price, input_tokens=100, cached_input_tokens=10, output_tokens=20
    ) == Decimal("0.0004")


def test_live_route_requires_every_configured_provider() -> None:
    settings = ApiSettings(
        LLM_GATEWAY_MODE="live",
        LLM_PRIMARY_PROVIDER="openai",
        LLM_FALLBACK_PROVIDER="anthropic",
        OPENAI_API_KEY=SecretStr("openai-test-key"),
        ANTHROPIC_API_KEY=None,
    )

    with pytest.raises(ValueError, match="missing API key"):
        build_live_gateway(settings)
