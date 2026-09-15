"""Provider-neutral routing, retry and health policy for structured LLM calls."""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, TypeVar, cast

import httpx
from pydantic import BaseModel, ValidationError

from revops.application.dto import (
    LLMFailureKind,
    LLMGatewayHealth,
    LLMHealthStatus,
    LLMProviderHealth,
    LLMResult,
    LLMUsage,
)
from revops.application.ports import LLMGateway, LLMGatewayError

from .pricing import PRICING_CATALOG_VERSION, calculate_cost, get_model_price
from .providers import (
    AnthropicMessagesAdapter,
    OpenAIResponsesAdapter,
    ProviderAdapter,
    ProviderResponseError,
)

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class GatewayProviderConfig:
    provider: str
    model: str
    api_key: str


class RoutedLLMGateway(LLMGateway):
    """Ordered provider router with bounded, safety-preserving fallback."""

    def __init__(
        self,
        *,
        providers: tuple[ProviderAdapter, ...],
        provider_configs: tuple[GatewayProviderConfig, ...],
        mode: str,
        max_retries: int,
        timeout_seconds: float,
        deadline_seconds: float,
        backoff_base_seconds: float,
        backoff_max_seconds: float,
        temperature: float,
        max_output_tokens: int,
        client: httpx.AsyncClient,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        random_value: Callable[[], float] = random.random,
    ) -> None:
        self._providers = providers
        self._provider_configs = provider_configs
        self._mode = mode
        self._max_retries = max_retries
        self._timeout_seconds = timeout_seconds
        self._deadline_seconds = deadline_seconds
        self._backoff_base_seconds = backoff_base_seconds
        self._backoff_max_seconds = backoff_max_seconds
        self._temperature = temperature
        self._max_output_tokens = max_output_tokens
        self._client = client
        self._sleep = sleep
        self._monotonic = monotonic
        self._random_value = random_value
        self._health: dict[str, LLMHealthStatus] = {
            config.provider: LLMHealthStatus.UNKNOWN for config in provider_configs
        }

    def configuration_snapshot(self) -> Mapping[str, object]:
        return {
            "gateway_version": "multi_provider.v1",
            "route_policy_version": "ordered_transient_fallback.v1",
            "pricing_catalog_version": PRICING_CATALOG_VERSION,
            "mode": self._mode,
            "providers": tuple(
                {"provider": config.provider, "model": config.model}
                for config in self._provider_configs
            ),
            "temperature": self._temperature,
            "max_output_tokens": self._max_output_tokens,
            "timeout_seconds": self._timeout_seconds,
            "deadline_seconds": self._deadline_seconds,
            "max_retries": self._max_retries,
            "store": False,
        }

    def health_snapshot(self) -> LLMGatewayHealth:
        statuses = tuple(
            LLMProviderHealth(provider=provider, status=status)
            for provider, status in self._health.items()
        )
        if self._mode == "disabled":
            status = LLMHealthStatus.DISABLED
        elif not statuses or all(item.status is LLMHealthStatus.UNAVAILABLE for item in statuses):
            status = LLMHealthStatus.UNAVAILABLE
        elif any(item.status is LLMHealthStatus.HEALTHY for item in statuses):
            status = (
                LLMHealthStatus.HEALTHY
                if all(item.status is LLMHealthStatus.HEALTHY for item in statuses)
                else LLMHealthStatus.DEGRADED
            )
        else:
            status = LLMHealthStatus.UNKNOWN
        return LLMGatewayHealth(mode=self._mode, status=status, providers=statuses)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def complete(self, *, prompt: str, response_model: type[T]) -> LLMResult[T]:
        started = self._monotonic()
        attempts: list[dict[str, object]] = []
        last_error: LLMGatewayError | None = None
        last_transient_kind = LLMFailureKind.SERVER
        model_type = cast(type[BaseModel], response_model)
        for provider_index, provider in enumerate(self._providers):
            provider_failed_transiently = False
            for retry_index in range(self._max_retries + 1):
                if self._monotonic() - started >= self._deadline_seconds:
                    break
                try:
                    response = await provider.complete(
                        prompt=prompt,
                        response_model=model_type,
                    )
                    output = cast(T, model_type.model_validate(response.payload))
                except ValidationError:
                    self._health[provider.provider] = LLMHealthStatus.DEGRADED
                    raise
                except ProviderResponseError as exc:
                    provider_failed_transiently = exc.retryable
                    if exc.retryable:
                        last_transient_kind = exc.kind
                    attempts.append(
                        {
                            "provider": provider.provider,
                            "model": provider.model,
                            "attempt": retry_index + 1,
                            "outcome": exc.kind.value,
                        }
                    )
                    if not exc.retryable:
                        self._health[provider.provider] = LLMHealthStatus.UNAVAILABLE
                        raise LLMGatewayError(
                            provider=provider.provider,
                            kind=exc.kind,
                            attempts=retry_index + 1,
                            retryable=False,
                            request_id=exc.request_id,
                        ) from exc
                    if retry_index < self._max_retries:
                        await self._backoff(retry_index, started, exc.retry_after_seconds)
                        continue
                    break
                except httpx.TimeoutException:
                    provider_failed_transiently = True
                    last_transient_kind = LLMFailureKind.TIMEOUT
                    attempts.append(
                        {
                            "provider": provider.provider,
                            "model": provider.model,
                            "attempt": retry_index + 1,
                            "outcome": LLMFailureKind.TIMEOUT.value,
                        }
                    )
                    if retry_index < self._max_retries:
                        await self._backoff(retry_index, started)
                        continue
                    break
                except httpx.HTTPError:
                    provider_failed_transiently = True
                    last_transient_kind = LLMFailureKind.NETWORK
                    attempts.append(
                        {
                            "provider": provider.provider,
                            "model": provider.model,
                            "attempt": retry_index + 1,
                            "outcome": LLMFailureKind.NETWORK.value,
                        }
                    )
                    if retry_index < self._max_retries:
                        await self._backoff(retry_index, started)
                        continue
                    break
                else:
                    self._health[provider.provider] = LLMHealthStatus.HEALTHY
                    config = self._provider_configs[provider_index]
                    price = get_model_price(provider.provider, response.model)
                    cost = calculate_cost(
                        price,
                        input_tokens=response.input_tokens,
                        cached_input_tokens=response.cached_input_tokens,
                        output_tokens=response.output_tokens,
                        cache_write_tokens=response.cache_write_tokens,
                    )
                    elapsed_ms = max(int((self._monotonic() - started) * 1000), 0)
                    attempts.append(
                        {
                            "provider": provider.provider,
                            "model": response.model,
                            "attempt": retry_index + 1,
                            "outcome": "success",
                        }
                    )
                    config_snapshot = dict(self.configuration_snapshot())
                    config_snapshot.update(
                        {
                            "requested_provider": config.provider,
                            "requested_model": config.model,
                            "resolved_model": response.model,
                            "fallback_used": provider_index > 0,
                            "attempts": tuple(attempts),
                            "token_breakdown": {
                                "input": response.input_tokens,
                                "cached_input": response.cached_input_tokens,
                                "cache_write": response.cache_write_tokens,
                                "output": response.output_tokens,
                            },
                        }
                    )
                    return LLMResult(
                        output=output,
                        usage=LLMUsage(
                            provider=provider.provider,
                            model=response.model,
                            model_config_json=config_snapshot,
                            input_tokens=response.input_tokens,
                            output_tokens=response.output_tokens,
                            token_cost_usd=cost,
                            latency_ms=elapsed_ms,
                        ),
                    )
            if provider_failed_transiently:
                self._health[provider.provider] = LLMHealthStatus.UNAVAILABLE
                last_error = LLMGatewayError(
                    provider=provider.provider,
                    kind=last_transient_kind,
                    attempts=self._max_retries + 1,
                    retryable=True,
                )
                continue
            break
        if last_error is not None:
            raise last_error
        raise LLMGatewayError(
            provider="route",
            kind=LLMFailureKind.TIMEOUT,
            attempts=len(attempts),
            retryable=True,
        )

    async def _backoff(
        self, retry_index: int, started: float, retry_after_seconds: float | None = None
    ) -> None:
        exponential = min(self._backoff_base_seconds * (2**retry_index), self._backoff_max_seconds)
        requested = retry_after_seconds if retry_after_seconds is not None else exponential
        delay = min(requested, self._backoff_max_seconds)
        if retry_after_seconds is None:
            delay *= 0.5 + self._random_value() / 2
        remaining = self._deadline_seconds - (self._monotonic() - started)
        if remaining > 0:
            await self._sleep(min(delay, remaining))


def build_live_gateway(settings: Any) -> RoutedLLMGateway:
    if settings.llm_gateway_mode != "live":
        raise ValueError("live gateway requires LLM_GATEWAY_MODE=live")
    configs: list[GatewayProviderConfig] = []
    for provider in (settings.llm_primary_provider, settings.llm_fallback_provider):
        if provider == "none":
            continue
        if provider not in {"openai", "anthropic"}:
            raise ValueError(f"unsupported LLM provider: {provider}")
        key = getattr(settings, f"{provider}_api_key")
        if key is None or not key.get_secret_value():
            raise ValueError(f"missing API key for configured provider: {provider}")
        model = getattr(settings, f"{provider}_model")
        get_model_price(provider, model)
        configs.append(
            GatewayProviderConfig(provider=provider, model=model, api_key=key.get_secret_value())
        )
    if not configs:
        raise ValueError("at least one LLM provider must be configured in live mode")
    if len({config.provider for config in configs}) != len(configs):
        raise ValueError("LLM primary and fallback providers must be different")
    timeout = httpx.Timeout(settings.llm_request_timeout_seconds)
    client = httpx.AsyncClient(timeout=timeout)
    adapters: list[ProviderAdapter] = []
    for config in configs:
        if config.provider == "openai":
            adapters.append(
                OpenAIResponsesAdapter(
                    client=client,
                    api_key=config.api_key,
                    model=config.model,
                    max_output_tokens=settings.llm_max_output_tokens,
                    temperature=settings.llm_temperature,
                )
            )
        else:
            adapters.append(
                AnthropicMessagesAdapter(
                    client=client,
                    api_key=config.api_key,
                    model=config.model,
                    max_output_tokens=settings.llm_max_output_tokens,
                    temperature=settings.llm_temperature,
                )
            )
    return RoutedLLMGateway(
        providers=tuple(adapters),
        provider_configs=tuple(configs),
        mode="live",
        max_retries=settings.llm_max_retries,
        timeout_seconds=settings.llm_request_timeout_seconds,
        deadline_seconds=settings.llm_call_deadline_seconds,
        backoff_base_seconds=settings.llm_backoff_base_seconds,
        backoff_max_seconds=settings.llm_backoff_max_seconds,
        temperature=settings.llm_temperature,
        max_output_tokens=settings.llm_max_output_tokens,
        client=client,
    )
