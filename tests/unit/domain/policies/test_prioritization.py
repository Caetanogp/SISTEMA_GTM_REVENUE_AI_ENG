from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from revops.domain.entities.interaction import Interaction
from revops.domain.entities.opportunity import Opportunity, OpportunityStage
from revops.domain.policies.prioritization import (
    engagement_signal,
    opportunity_value_signal,
    prioritize_account,
    recency_signal,
    stage_signal,
)

NOW = datetime(2026, 1, 31, tzinfo=UTC)


def _interaction(days_ago: int, channel: str = "email") -> Interaction:
    return Interaction(
        id=uuid4(),
        organization_id=uuid4(),
        account_id=uuid4(),
        channel=channel,
        occurred_at=NOW - timedelta(days=days_ago),
    )


def _opportunity(stage: OpportunityStage, value: int) -> Opportunity:
    return Opportunity(
        id=uuid4(), organization_id=uuid4(), account_id=uuid4(), stage=stage, value=Decimal(value)
    )


# --- recency_signal ---------------------------------------------------------


def test_recency_no_interactions_scores_maximum_urgency() -> None:
    result = recency_signal([], NOW)
    assert result.sub_score == 100
    assert "never touched" in result.evidence


def test_recency_touched_today_scores_maximum() -> None:
    assert recency_signal([_interaction(0)], NOW).sub_score == 100


def test_recency_touched_halfway_to_stale_scores_midpoint() -> None:
    assert recency_signal([_interaction(15)], NOW).sub_score == 50


def test_recency_touched_at_stale_boundary_scores_zero() -> None:
    assert recency_signal([_interaction(30)], NOW).sub_score == 0


def test_recency_touched_long_ago_still_floors_at_zero() -> None:
    assert recency_signal([_interaction(365)], NOW).sub_score == 0


def test_recency_uses_the_most_recent_interaction() -> None:
    result = recency_signal([_interaction(200), _interaction(0), _interaction(50)], NOW)
    assert result.sub_score == 100


# --- opportunity_value_signal ------------------------------------------------


def test_value_no_opportunities_scores_zero() -> None:
    assert opportunity_value_signal([]).sub_score == 0


def test_value_half_the_threshold_scores_fifty() -> None:
    opp = _opportunity(OpportunityStage.PROSPECTING, 50_000)
    assert opportunity_value_signal([opp]).sub_score == 50


def test_value_at_threshold_scores_full() -> None:
    opp = _opportunity(OpportunityStage.PROSPECTING, 100_000)
    assert opportunity_value_signal([opp]).sub_score == 100


def test_value_above_threshold_is_capped_at_full() -> None:
    opp = _opportunity(OpportunityStage.PROSPECTING, 500_000)
    assert opportunity_value_signal([opp]).sub_score == 100


def test_value_ignores_closed_opportunities() -> None:
    closed = _opportunity(OpportunityStage.CLOSED_WON, 900_000)
    assert opportunity_value_signal([closed]).sub_score == 0


def test_value_sums_across_open_opportunities() -> None:
    opps = [
        _opportunity(OpportunityStage.PROSPECTING, 30_000),
        _opportunity(OpportunityStage.NEGOTIATION, 20_000),
    ]
    assert opportunity_value_signal(opps).sub_score == 50


# --- stage_signal -------------------------------------------------------------


def test_stage_no_opportunities_scores_zero() -> None:
    result = stage_signal([])
    assert result.sub_score == 0
    assert "no open opportunities" in result.evidence


def test_stage_uses_the_most_advanced_open_opportunity() -> None:
    opps = [
        _opportunity(OpportunityStage.PROSPECTING, 1),
        _opportunity(OpportunityStage.NEGOTIATION, 1),
    ]
    assert stage_signal(opps).sub_score == 90


def test_stage_ignores_closed_opportunities() -> None:
    opps = [
        _opportunity(OpportunityStage.CLOSED_WON, 1),
        _opportunity(OpportunityStage.PROPOSAL, 1),
    ]
    assert stage_signal(opps).sub_score == 70


# --- engagement_signal ---------------------------------------------------------


def test_engagement_no_interactions_scores_zero() -> None:
    assert engagement_signal([], NOW).sub_score == 0


def test_engagement_scales_with_recent_count() -> None:
    interactions = [_interaction(1), _interaction(2), _interaction(3)]
    assert engagement_signal(interactions, NOW).sub_score == 30


def test_engagement_caps_at_one_hundred() -> None:
    interactions = [_interaction(day) for day in range(15)]
    assert engagement_signal(interactions, NOW).sub_score == 100


def test_engagement_ignores_stale_interactions() -> None:
    interactions = [_interaction(200), _interaction(200)]
    assert engagement_signal(interactions, NOW).sub_score == 0


# --- prioritize_account (combined) --------------------------------------------


def test_combined_untouched_account_with_no_pipeline_scores_only_from_recency() -> None:
    # recency=100 (never touched), value=0, stage=0, engagement=0
    score, evidence = prioritize_account([], [], NOW)
    assert score.value == round(100 * 0.35)
    assert len(evidence) == 4


def test_combined_hot_account_scores_in_the_hot_tier() -> None:
    interactions = [_interaction(0), _interaction(1), _interaction(2)]
    opportunities = [_opportunity(OpportunityStage.NEGOTIATION, 150_000)]
    score, _ = prioritize_account(interactions, opportunities, NOW)
    assert score.tier.value == "hot"


def test_combined_score_never_exceeds_one_hundred() -> None:
    interactions = [_interaction(0) for _ in range(10)]
    opportunities = [_opportunity(OpportunityStage.NEGOTIATION, 1_000_000)]
    score, _ = prioritize_account(interactions, opportunities, NOW)
    assert score.value <= 100


def test_combined_always_returns_four_non_empty_evidence_items() -> None:
    _, evidence = prioritize_account([], [], NOW)
    assert len(evidence) == 4
    assert all(isinstance(item, str) and item for item in evidence)
