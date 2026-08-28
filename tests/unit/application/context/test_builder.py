from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from revops.application.context.builder import ContextBuilder
from revops.domain.entities.account import Account
from revops.domain.entities.interaction import Interaction
from revops.domain.entities.opportunity import Opportunity, OpportunityStage
from revops.domain.values.company_domain import CompanyDomain

_NOW = datetime(2026, 1, 31, tzinfo=UTC)
_ORG_ID = uuid4()


def _account() -> Account:
    return Account(
        id=uuid4(),
        organization_id=_ORG_ID,
        company_name="Acme Corp",
        domain=CompanyDomain("acme.com"),
        created_at=_NOW - timedelta(days=400),
    )


def _opportunities(count: int = 1) -> list[Opportunity]:
    return [
        Opportunity(
            id=uuid4(),
            organization_id=_ORG_ID,
            account_id=uuid4(),
            stage=OpportunityStage.NEGOTIATION,
            value=Decimal(50_000),
        )
        for _ in range(count)
    ]


def _interactions(count: int = 1) -> list[Interaction]:
    return [
        Interaction(
            id=uuid4(),
            organization_id=_ORG_ID,
            account_id=uuid4(),
            channel="email",
            occurred_at=_NOW - timedelta(days=i),
            summary=f"Interaction number {i} with a reasonably long summary to consume budget.",
        )
        for i in range(count)
    ]


def test_everything_fits_within_a_generous_budget() -> None:
    context = ContextBuilder().build(
        _account(), _interactions(), _opportunities(), token_budget=10_000
    )

    labels = [s.label for s in context.sections]
    assert labels == ["account", "opportunities", "interactions"]
    assert context.dropped_labels == []
    assert context.token_count > 0


def test_a_budget_too_small_for_even_the_first_section_truncates_everything() -> None:
    """Proves truncation, not silent overflow: nothing is included past what fits."""
    context = ContextBuilder().build(
        _account(), _interactions(count=20), _opportunities(count=20), token_budget=1
    )

    assert context.sections == []
    assert context.dropped_labels == ["account", "opportunities", "interactions"]
    assert context.token_count == 0
    assert context.token_count <= 1


def test_truncation_drops_lowest_priority_sections_first_in_documented_order() -> None:
    """Priority order is account > opportunities > interactions - interactions drop first."""
    account = _account()
    opportunities = _opportunities(count=1)

    account_and_opportunities = ContextBuilder().build(
        account, [], opportunities, token_budget=10_000
    )
    budget_for_two_sections = account_and_opportunities.token_count

    context = ContextBuilder().build(
        account, _interactions(count=20), opportunities, token_budget=budget_for_two_sections
    )

    assert [s.label for s in context.sections] == ["account", "opportunities"]
    assert context.dropped_labels == ["interactions"]
    assert context.token_count <= budget_for_two_sections


def test_empty_interactions_and_opportunities_still_produce_a_placeholder_section() -> None:
    context = ContextBuilder().build(_account(), [], [], token_budget=10_000)

    labels = [s.label for s in context.sections]
    assert labels == ["account", "opportunities", "interactions"]
    assert context.dropped_labels == []
