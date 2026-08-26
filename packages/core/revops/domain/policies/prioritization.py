"""Deterministic account-prioritization signals.

The LLM explains and ranks (infrastructure/agent layer); it does not invent the arithmetic. Each
signal returns a 0-100 sub-score plus a human-readable evidence string that names the CRM data
behind it - SPEC-001's acceptance criteria require at least one such evidence item per account.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from revops.domain.entities.interaction import Interaction
from revops.domain.entities.opportunity import Opportunity, OpportunityStage
from revops.domain.values.score import Score

_RECENCY_WEIGHT = 0.35
_OPPORTUNITY_VALUE_WEIGHT = 0.30
_STAGE_WEIGHT = 0.20
_ENGAGEMENT_WEIGHT = 0.15

_STAGE_SCORE: dict[OpportunityStage, int] = {
    OpportunityStage.PROSPECTING: 20,
    OpportunityStage.QUALIFICATION: 45,
    OpportunityStage.PROPOSAL: 70,
    OpportunityStage.NEGOTIATION: 90,
    OpportunityStage.CLOSED_WON: 0,
    OpportunityStage.CLOSED_LOST: 0,
}

# An open-pipeline value at or above this is treated as maximally significant.
_HIGH_VALUE_THRESHOLD = Decimal(100_000)

# A last touch this many days ago or older scores zero recency; a fresher touch scores higher.
_STALE_AFTER_DAYS = 30


@dataclass(frozen=True, slots=True)
class SignalResult:
    """One prioritization signal: its 0-100 sub-score and the evidence behind it."""

    sub_score: int
    evidence: str


def recency_signal(interactions: list[Interaction], now: datetime) -> SignalResult:
    """More recent last touch -> higher urgency. No interactions at all -> maximum urgency."""
    if not interactions:
        return SignalResult(100, "no recorded interactions - never touched")
    last = max(interactions, key=lambda i: i.occurred_at)
    days_since = max((now - last.occurred_at).days, 0)
    sub_score = max(0, round(100 * (1 - days_since / _STALE_AFTER_DAYS)))
    return SignalResult(
        sub_score,
        f"last touch {days_since} day(s) ago via {last.channel} ({last.occurred_at.date()})",
    )


def opportunity_value_signal(opportunities: list[Opportunity]) -> SignalResult:
    """Larger open pipeline -> higher priority."""
    open_value = sum((o.value for o in opportunities if o.stage.is_open), start=Decimal(0))
    ratio = min(open_value / _HIGH_VALUE_THRESHOLD, Decimal(1)) if open_value else Decimal(0)
    sub_score = round(float(ratio) * 100)
    return SignalResult(sub_score, f"${open_value:,.0f} in open pipeline")


def stage_signal(opportunities: list[Opportunity]) -> SignalResult:
    """Further-along deals -> higher priority. Uses the single most advanced open opportunity."""
    open_opportunities = [o for o in opportunities if o.stage.is_open]
    if not open_opportunities:
        return SignalResult(0, "no open opportunities")
    best = max(open_opportunities, key=lambda o: _STAGE_SCORE[o.stage])
    return SignalResult(_STAGE_SCORE[best.stage], f"most advanced open stage: {best.stage.value}")


def engagement_signal(interactions: list[Interaction], now: datetime) -> SignalResult:
    """More engagement recently -> higher priority."""
    recent = [i for i in interactions if (now - i.occurred_at).days <= _STALE_AFTER_DAYS]
    sub_score = min(len(recent) * 10, 100)
    return SignalResult(
        sub_score, f"{len(recent)} interaction(s) in the last {_STALE_AFTER_DAYS} days"
    )


def prioritize_account(
    interactions: list[Interaction],
    opportunities: list[Opportunity],
    now: datetime,
) -> tuple[Score, list[str]]:
    """Combine the four signals into one Score, with the evidence trail behind it."""
    recency = recency_signal(interactions, now)
    value = opportunity_value_signal(opportunities)
    stage = stage_signal(opportunities)
    engagement = engagement_signal(interactions, now)

    combined = round(
        recency.sub_score * _RECENCY_WEIGHT
        + value.sub_score * _OPPORTUNITY_VALUE_WEIGHT
        + stage.sub_score * _STAGE_WEIGHT
        + engagement.sub_score * _ENGAGEMENT_WEIGHT
    )
    combined = max(0, min(100, combined))

    evidence = [recency.evidence, value.evidence, stage.evidence, engagement.evidence]
    return Score(combined), evidence
