"""Opt-in live smoke test for configured LLM providers.

This command sends one minimal structured request per selected provider. It never prints the
prompt, completion, credentials or raw provider errors.
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Literal, cast

from pydantic import BaseModel
from revops.infrastructure.llm.gateway import build_live_gateway

from apps.api.settings import ApiSettings


class SmokeOutput(BaseModel):
    ok: bool


async def _check_provider(provider: Literal["openai", "anthropic"]) -> None:
    base = ApiSettings()
    settings = base.model_copy(
        update={
            "llm_gateway_mode": "live",
            "llm_primary_provider": provider,
            "llm_fallback_provider": "none",
        }
    )
    gateway = build_live_gateway(settings)
    try:
        await gateway.complete(
            prompt='Return the JSON object {"ok": true}.', response_model=SmokeOutput
        )
    finally:
        await gateway.aclose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=("openai", "anthropic", "all"), default="all")
    parser.add_argument(
        "--confirm-cost",
        action="store_true",
        help="Acknowledge that provider charges may apply.",
    )
    args = parser.parse_args()
    if not args.confirm_cost:
        parser.error("refusing live calls without --confirm-cost")
    providers: tuple[Literal["openai", "anthropic"], ...]
    if args.provider == "all":
        providers = ("openai", "anthropic")
    else:
        providers = (cast(Literal["openai", "anthropic"], args.provider),)

    async def run() -> None:
        await asyncio.gather(*(_check_provider(provider) for provider in providers))

    asyncio.run(run())
    print("LLM live smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
