"""Versioned provider pricing used to calculate auditable LLM usage costs."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final

PRICING_CATALOG_VERSION: Final = "2026-09-13.v1"
_PER_MILLION: Final = Decimal("1000000")


@dataclass(frozen=True, slots=True)
class ModelPrice:
    provider: str
    model: str
    input_per_million: Decimal
    cached_input_per_million: Decimal
    output_per_million: Decimal
    cache_write_per_million: Decimal = Decimal("0")


CATALOG: Final[dict[tuple[str, str], ModelPrice]] = {
    ("openai", "gpt-5.6-terra"): ModelPrice(
        provider="openai",
        model="gpt-5.6-terra",
        input_per_million=Decimal("2"),
        cached_input_per_million=Decimal("0.20"),
        output_per_million=Decimal("12"),
    ),
    ("anthropic", "claude-sonnet-5"): ModelPrice(
        provider="anthropic",
        model="claude-sonnet-5",
        input_per_million=Decimal("2"),
        cached_input_per_million=Decimal("0.20"),
        output_per_million=Decimal("10"),
        cache_write_per_million=Decimal("2.50"),
    ),
}


class UnknownModelPriceError(ValueError):
    """Raised when a live model has no reviewed price entry."""


def get_model_price(provider: str, model: str) -> ModelPrice:
    try:
        return CATALOG[(provider, model)]
    except KeyError as exc:
        raise UnknownModelPriceError(f"no price catalog entry for {provider}/{model}") from exc


def calculate_cost(
    price: ModelPrice,
    *,
    input_tokens: int,
    cached_input_tokens: int = 0,
    output_tokens: int,
    cache_write_tokens: int = 0,
) -> Decimal:
    uncached_input = max(input_tokens - cached_input_tokens, 0)
    return (
        Decimal(uncached_input) * price.input_per_million / _PER_MILLION
        + Decimal(cached_input_tokens) * price.cached_input_per_million / _PER_MILLION
        + Decimal(cache_write_tokens) * price.cache_write_per_million / _PER_MILLION
        + Decimal(output_tokens) * price.output_per_million / _PER_MILLION
    ).quantize(Decimal("0.0001"))
