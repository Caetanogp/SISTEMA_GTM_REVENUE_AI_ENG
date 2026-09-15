"""HTTPX adapters for provider-specific structured-output APIs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from pydantic import BaseModel

from revops.application.dto import LLMFailureKind


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    payload: object
    model: str
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    cache_write_tokens: int
    request_id: str | None


class ProviderResponseError(RuntimeError):
    """A sanitized provider response classification; raw bodies never cross this boundary."""

    def __init__(
        self,
        *,
        kind: LLMFailureKind,
        retryable: bool,
        request_id: str | None,
        retry_after_seconds: float | None = None,
    ) -> None:
        self.kind = kind
        self.retryable = retryable
        self.request_id = request_id
        self.retry_after_seconds = retry_after_seconds
        super().__init__(kind.value)


class ProviderAdapter(Protocol):
    provider: str
    model: str

    async def complete(
        self, *, prompt: str, response_model: type[BaseModel]
    ) -> ProviderResponse: ...


def _request_id(response: httpx.Response, payload: dict[str, Any]) -> str | None:
    value = response.headers.get("x-request-id") or payload.get("request_id") or payload.get("id")
    return str(value) if value is not None else None


def _retry_after_seconds(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None
    return seconds if seconds >= 0 else None


def _failure_kind(
    status_code: int, payload: dict[str, Any], *, retry_after: str | None
) -> tuple[LLMFailureKind, bool]:
    error = payload.get("error")
    error_code = error.get("code") if isinstance(error, dict) else None
    error_type = error.get("type") if isinstance(error, dict) else None
    if status_code == 401:
        return LLMFailureKind.AUTHENTICATION, False
    if status_code == 402:
        return LLMFailureKind.BILLING, False
    if status_code == 403:
        return LLMFailureKind.PERMISSION, False
    if status_code == 429:
        permanent_codes = {"insufficient_quota", "enforced_spend_limit_reached"}
        return (
            LLMFailureKind.RATE_LIMIT,
            error_code not in permanent_codes and retry_after is not None,
        )
    if status_code in (408, 409):
        return LLMFailureKind.TIMEOUT if status_code == 408 else LLMFailureKind.NETWORK, True
    if status_code >= 500:
        return LLMFailureKind.SERVER, True
    if error_type == "overloaded_error":
        return LLMFailureKind.SERVER, True
    return LLMFailureKind.INVALID_REQUEST, False


class OpenAIResponsesAdapter:
    provider = "openai"

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        api_key: str,
        model: str,
        max_output_tokens: int,
        temperature: float,
    ) -> None:
        self._client = client
        self._api_key = api_key
        self.model = model
        self._max_output_tokens = max_output_tokens
        self._temperature = temperature

    async def complete(self, *, prompt: str, response_model: type[BaseModel]) -> ProviderResponse:
        body = {
            "model": self.model,
            "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": response_model.__name__,
                    "schema": response_model.model_json_schema(),
                    "strict": True,
                }
            },
            "max_output_tokens": self._max_output_tokens,
            "temperature": self._temperature,
            "store": False,
        }
        response = await self._client.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json=body,
        )
        payload = _json_payload(response)
        if response.is_error:
            kind, retryable = _failure_kind(
                response.status_code,
                payload,
                retry_after=response.headers.get("retry-after"),
            )
            raise ProviderResponseError(
                kind=kind,
                retryable=retryable,
                request_id=_request_id(response, payload),
                retry_after_seconds=_retry_after_seconds(response),
            )
        text = payload.get("output_text")
        if _contains_type(payload, "refusal"):
            raise ProviderResponseError(
                kind=LLMFailureKind.SAFETY_REFUSAL,
                retryable=False,
                request_id=_request_id(response, payload),
            )
        if not isinstance(text, str):
            text = _nested_text(payload, output_type="output_text")
        if text is None:
            raise ProviderResponseError(
                kind=LLMFailureKind.INVALID_RESPONSE,
                retryable=False,
                request_id=_request_id(response, payload),
            )
        usage_value = payload.get("usage")
        usage: dict[str, Any] = usage_value if isinstance(usage_value, dict) else {}
        details = usage.get("input_tokens_details")
        cached = details.get("cached_tokens", 0) if isinstance(details, dict) else 0
        return ProviderResponse(
            payload=_decode_json(text),
            model=str(payload.get("model", self.model)),
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            cached_input_tokens=int(cached),
            cache_write_tokens=0,
            request_id=_request_id(response, payload),
        )


class AnthropicMessagesAdapter:
    provider = "anthropic"

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        api_key: str,
        model: str,
        max_output_tokens: int,
        temperature: float,
    ) -> None:
        self._client = client
        self._api_key = api_key
        self.model = model
        self._max_output_tokens = max_output_tokens
        self._temperature = temperature

    async def complete(self, *, prompt: str, response_model: type[BaseModel]) -> ProviderResponse:
        body = {
            "model": self.model,
            "max_tokens": self._max_output_tokens,
            "temperature": self._temperature,
            "messages": [{"role": "user", "content": prompt}],
            "output_config": {
                "format": {"type": "json_schema", "schema": response_model.model_json_schema()}
            },
        }
        response = await self._client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
            },
            json=body,
        )
        payload = _json_payload(response)
        if response.is_error:
            kind, retryable = _failure_kind(
                response.status_code,
                payload,
                retry_after=response.headers.get("retry-after"),
            )
            raise ProviderResponseError(
                kind=kind,
                retryable=retryable,
                request_id=_request_id(response, payload),
                retry_after_seconds=_retry_after_seconds(response),
            )
        if payload.get("stop_reason") == "refusal":
            raise ProviderResponseError(
                kind=LLMFailureKind.SAFETY_REFUSAL,
                retryable=False,
                request_id=_request_id(response, payload),
            )
        if payload.get("stop_reason") == "max_tokens":
            raise ProviderResponseError(
                kind=LLMFailureKind.INVALID_RESPONSE,
                retryable=False,
                request_id=_request_id(response, payload),
            )
        text = _nested_text(payload, output_type="text")
        if text is None:
            raise ProviderResponseError(
                kind=LLMFailureKind.INVALID_RESPONSE,
                retryable=False,
                request_id=_request_id(response, payload),
            )
        usage_value = payload.get("usage")
        usage: dict[str, Any] = usage_value if isinstance(usage_value, dict) else {}
        return ProviderResponse(
            payload=_decode_json(text),
            model=str(payload.get("model", self.model)),
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            cached_input_tokens=int(usage.get("cache_read_input_tokens", 0)),
            cache_write_tokens=int(usage.get("cache_creation_input_tokens", 0)),
            request_id=_request_id(response, payload),
        )


def _json_payload(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderResponseError(
            kind=LLMFailureKind.INVALID_RESPONSE,
            retryable=False,
            request_id=response.headers.get("x-request-id"),
        ) from exc
    return payload if isinstance(payload, dict) else {}


def _nested_text(payload: dict[str, Any], *, output_type: str) -> str | None:
    for item in payload.get("output", payload.get("content", [])):
        if not isinstance(item, dict):
            continue
        for block in item.get("content", [item]):
            if isinstance(block, dict) and block.get("type") == output_type:
                text = block.get("text")
                if isinstance(text, str):
                    return text
    return None


def _contains_type(payload: dict[str, Any], block_type: str) -> bool:
    for item in payload.get("output", payload.get("content", [])):
        if not isinstance(item, dict):
            continue
        blocks = item.get("content", [item])
        if any(isinstance(block, dict) and block.get("type") == block_type for block in blocks):
            return True
    return False


def _decode_json(text: str) -> object:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProviderResponseError(
            kind=LLMFailureKind.INVALID_RESPONSE,
            retryable=False,
            request_id=None,
        ) from exc
