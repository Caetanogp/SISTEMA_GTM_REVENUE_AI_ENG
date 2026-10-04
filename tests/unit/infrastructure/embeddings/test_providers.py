"""Unit tests for bounded offline and live embedding providers."""

from __future__ import annotations

import asyncio
import json
import math

import httpx
import pytest
from revops.infrastructure.embeddings.providers import (
    DEFAULT_DIMENSION,
    DeterministicFakeEmbeddingProvider,
    EmbeddingProviderError,
    OpenAIEmbeddingProvider,
)


@pytest.fixture
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
        return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.get_event_loop_policy()


@pytest.mark.asyncio
async def test_fake_embeddings_are_deterministic_normalized_and_ordered() -> None:
    provider = DeterministicFakeEmbeddingProvider()

    first = await provider.embed(("alpha", "beta"))
    second = await provider.embed(("alpha", "beta"))

    assert first == second
    assert first.model == "offline-fake-v1"
    assert first.dimension == DEFAULT_DIMENSION
    assert len(first.vectors) == 2
    assert all(
        math.isclose(math.sqrt(sum(value * value for value in vector)), 1.0)
        for vector in first.vectors
    )
    assert first.vectors[0] != first.vectors[1]


@pytest.mark.asyncio
async def test_fake_provider_rejects_batches_over_64() -> None:
    provider = DeterministicFakeEmbeddingProvider(dimension=8)

    with pytest.raises(ValueError, match="64"):
        await provider.embed(tuple(str(index) for index in range(65)))


@pytest.mark.asyncio
async def test_openai_provider_preserves_indexes_and_bounds_request() -> None:
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = json.loads(request.content)
        assert body == {"model": "test-model", "input": ["alpha", "beta"], "dimensions": 2}
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0]},
                    {"index": 0, "embedding": [1.0, 0.0]},
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAIEmbeddingProvider(
            client=client, api_key="test-key", model="test-model", dimension=2
        )
        result = await provider.embed(("alpha", "beta"))

    assert len(seen) == 1
    assert seen[0].headers["authorization"] == "Bearer test-key"
    assert result.vectors == ((1.0, 0.0), (0.0, 1.0))


@pytest.mark.asyncio
async def test_openai_provider_retries_transient_failure_but_never_falls_back() -> None:
    attempts = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(503, json={"error": "unavailable"})
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0, 0.0]}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAIEmbeddingProvider(
            client=client, api_key="test-key", dimension=2, max_retries=2
        )
        result = await provider.embed(("alpha",))

    assert attempts == 3
    assert result.vectors == ((1.0, 0.0),)

    async def failing_handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "unavailable"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(failing_handler)) as client:
        provider = OpenAIEmbeddingProvider(
            client=client, api_key="test-key", dimension=2, max_retries=0
        )
        with pytest.raises(EmbeddingProviderError, match="embedding_unavailable"):
            await provider.embed(("alpha",))


@pytest.mark.asyncio
async def test_openai_provider_rejects_malformed_dimensions_and_large_batches() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0]}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAIEmbeddingProvider(client=client, api_key="test-key", dimension=2)
        with pytest.raises(EmbeddingProviderError, match="embedding_invalid_response"):
            await provider.embed(("alpha",))
        with pytest.raises(ValueError, match="64"):
            await provider.embed(tuple(str(index) for index in range(65)))
