"""Deterministic offline and explicit OpenAI embedding providers."""

from __future__ import annotations

import asyncio
import hashlib
import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from revops.application.dto import EmbeddingBatch

MAX_BATCH_SIZE = 64
DEFAULT_DIMENSION = 1536
DEFAULT_MODEL = "text-embedding-3-small"
DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_RETRIES = 2


class EmbeddingProviderError(RuntimeError):
    """Sanitized provider failure; raw response bodies never cross this boundary."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


def _validate_batch(texts: Sequence[str]) -> None:
    if len(texts) > MAX_BATCH_SIZE:
        raise ValueError(f"embedding batch cannot exceed {MAX_BATCH_SIZE} inputs")


def _normalize(vector: list[float]) -> tuple[float, ...]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        raise ValueError("embedding vector must not be zero")
    return tuple(value / norm for value in vector)


class DeterministicFakeEmbeddingProvider:
    """Generate stable, normalized non-semantic vectors without credentials or I/O."""

    def __init__(self, *, dimension: int = DEFAULT_DIMENSION) -> None:
        if dimension <= 0:
            raise ValueError("embedding dimension must be positive")
        self.model = "offline-fake-v1"
        self.dimension = dimension

    def _vector(self, text: str) -> tuple[float, ...]:
        values: list[float] = []
        counter = 0
        while len(values) < self.dimension:
            digest = hashlib.sha256(
                f"revops-offline-fake-v1:{counter}:".encode() + text.encode("utf-8")
            ).digest()
            values.extend((byte / 127.5) - 1.0 for byte in digest)
            counter += 1
        return _normalize(values[: self.dimension])

    async def embed(self, texts: Sequence[str]) -> EmbeddingBatch:
        _validate_batch(texts)
        vectors = tuple(self._vector(text) for text in texts)
        return EmbeddingBatch(model=self.model, dimension=self.dimension, vectors=vectors)


@dataclass(frozen=True, slots=True)
class _OpenAIError:
    status_code: int | None
    retryable: bool


class OpenAIEmbeddingProvider:
    """Bounded OpenAI embeddings adapter with no implicit offline fallback."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        api_key: str,
        model: str = DEFAULT_MODEL,
        dimension: int = DEFAULT_DIMENSION,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = MAX_RETRIES,
    ) -> None:
        if not api_key.strip():
            raise ValueError("OpenAI API key is required for the live embedding provider")
        if dimension <= 0 or timeout_seconds <= 0 or not 0 <= max_retries <= MAX_RETRIES:
            raise ValueError("invalid embedding provider bounds")
        self._client = client
        self._api_key = api_key
        self.model = model
        self.dimension = dimension
        self._timeout = timeout_seconds
        self._max_retries = max_retries

    @staticmethod
    def _classify(response: httpx.Response) -> _OpenAIError:
        return _OpenAIError(
            status_code=response.status_code,
            retryable=response.status_code in {408, 409, 429} or response.status_code >= 500,
        )

    async def _request(self, texts: Sequence[str]) -> dict[str, Any]:
        body = {"model": self.model, "input": list(texts), "dimensions": self.dimension}
        headers = {"Authorization": f"Bearer {self._api_key}"}
        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.post(
                    "https://api.openai.com/v1/embeddings",
                    headers=headers,
                    json=body,
                    timeout=self._timeout,
                )
            except httpx.RequestError as exc:
                if attempt >= self._max_retries:
                    raise EmbeddingProviderError(
                        "OpenAI embedding request failed", retryable=True
                    ) from exc
                await asyncio.sleep(0.1 * (2**attempt))
                continue
            if not response.is_error:
                payload = response.json()
                if not isinstance(payload, dict):
                    raise EmbeddingProviderError(
                        "OpenAI returned an invalid embedding payload", retryable=False
                    )
                return payload
            failure = self._classify(response)
            if not failure.retryable or attempt >= self._max_retries:
                raise EmbeddingProviderError(
                    f"OpenAI embedding request failed with status {failure.status_code}",
                    retryable=failure.retryable,
                )
            await asyncio.sleep(0.1 * (2**attempt))
        raise AssertionError("unreachable retry loop")

    async def embed(self, texts: Sequence[str]) -> EmbeddingBatch:
        _validate_batch(texts)
        payload = await self._request(texts)
        raw_data = payload.get("data")
        if not isinstance(raw_data, list) or len(raw_data) != len(texts):
            raise EmbeddingProviderError(
                "OpenAI returned an invalid embedding count", retryable=False
            )
        ordered: list[tuple[float, ...] | None] = [None] * len(texts)
        for item in raw_data:
            if not isinstance(item, dict) or not isinstance(item.get("index"), int):
                raise EmbeddingProviderError(
                    "OpenAI returned an invalid embedding item", retryable=False
                )
            index = item["index"]
            vector = item.get("embedding")
            if index < 0 or index >= len(texts) or not isinstance(vector, list):
                raise EmbeddingProviderError(
                    "OpenAI returned an invalid embedding item", retryable=False
                )
            if len(vector) != self.dimension or not all(
                isinstance(value, int | float) for value in vector
            ):
                raise EmbeddingProviderError(
                    "OpenAI returned an invalid embedding dimension", retryable=False
                )
            if ordered[index] is not None:
                raise EmbeddingProviderError(
                    "OpenAI returned duplicate embedding indexes", retryable=False
                )
            ordered[index] = tuple(float(value) for value in vector)
        if any(vector is None for vector in ordered):
            raise EmbeddingProviderError(
                "OpenAI returned incomplete embedding indexes", retryable=False
            )
        return EmbeddingBatch(
            model=self.model,
            dimension=self.dimension,
            vectors=tuple(vector for vector in ordered if vector is not None),
        )
