"""Opt-in live smoke test for one configured retrieval query embedding.

This checks provider configuration and response shape only. It does not query a tenant corpus,
write to the database, or measure semantic quality.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import httpx
from revops.infrastructure.embeddings.providers import OpenAIEmbeddingProvider

from apps.worker.settings import WorkerSettings


async def _run() -> None:
    settings = WorkerSettings()
    if settings.knowledge_embedding_provider != "openai" or settings.openai_api_key is None:
        raise ValueError("live_embedding_configuration_missing")
    async with httpx.AsyncClient() as client:
        provider = OpenAIEmbeddingProvider(
            client=client,
            api_key=settings.openai_api_key.get_secret_value(),
            model=settings.knowledge_embedding_model,
            dimension=settings.knowledge_embedding_dimension,
        )
        result = await provider.embed(("Synthetic retrieval smoke query.",))
    if len(result.vectors) != 1 or result.dimension != len(result.vectors[0]):
        raise ValueError("live_embedding_response_invalid")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-cost", action="store_true", help="Acknowledge provider charges.")
    args = parser.parse_args()
    if not args.confirm_cost:
        parser.error("refusing live calls without --confirm-cost")
    try:
        asyncio.run(_run())
    except Exception:
        print("Knowledge retrieval live smoke failed", file=sys.stderr)
        return 1
    print("Knowledge retrieval live smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
