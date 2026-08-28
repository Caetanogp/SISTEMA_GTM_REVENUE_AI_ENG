from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from revops.application.use_cases.prioritize_accounts import PrioritizeAccounts
from revops.domain.entities.account import Account
from revops.domain.entities.interaction import Interaction
from revops.domain.entities.opportunity import Opportunity, OpportunityStage
from revops.domain.values.company_domain import CompanyDomain

_NOW = datetime(2026, 1, 31, tzinfo=UTC)
_ORG_ID = uuid4()


def _account(company_name: str) -> Account:
    slug = company_name.lower().replace(" ", "")
    return Account(
        id=uuid4(),
        organization_id=_ORG_ID,
        company_name=company_name,
        domain=CompanyDomain(f"{slug}.com"),
        created_at=_NOW - timedelta(days=365),
    )


class _FakeClock:
    def now(self) -> datetime:
        return _NOW


class _FakeAccountRepository:
    def __init__(
        self,
        accounts: list[Account],
        interactions: dict[UUID, list[Interaction]],
        opportunities: dict[UUID, list[Opportunity]],
    ) -> None:
        self._accounts = accounts
        self._interactions = interactions
        self._opportunities = opportunities

    async def get(self, organization_id: UUID, account_id: UUID) -> Account:
        raise NotImplementedError

    async def list_for_organization(self, organization_id: UUID) -> Sequence[Account]:
        return [a for a in self._accounts if a.organization_id == organization_id]

    async def list_interactions(
        self, organization_id: UUID, account_id: UUID
    ) -> Sequence[Interaction]:
        return self._interactions.get(account_id, [])

    async def list_open_opportunities(
        self, organization_id: UUID, account_id: UUID
    ) -> Sequence[Opportunity]:
        return self._opportunities.get(account_id, [])


async def test_ranks_the_account_with_stronger_signals_first() -> None:
    hot = _account("Hot Co")
    cold = _account("Cold Co")

    interactions = {
        hot.id: [
            Interaction(
                id=uuid4(),
                organization_id=_ORG_ID,
                account_id=hot.id,
                channel="email",
                occurred_at=_NOW - timedelta(days=1),
            )
        ],
        cold.id: [],
    }
    opportunities = {
        hot.id: [
            Opportunity(
                id=uuid4(),
                organization_id=_ORG_ID,
                account_id=hot.id,
                stage=OpportunityStage.NEGOTIATION,
                value=Decimal(150_000),
            )
        ],
        cold.id: [],
    }

    use_case = PrioritizeAccounts(
        accounts=_FakeAccountRepository([hot, cold], interactions, opportunities),
        clock=_FakeClock(),
    )

    ranked = await use_case.execute(_ORG_ID)

    assert [s.account_id for s in ranked] == [hot.id, cold.id]
    assert ranked[0].score > ranked[1].score


async def test_only_returns_accounts_for_the_requesting_organization() -> None:
    mine = _account("Mine Co")
    other_org_account = Account(
        id=uuid4(),
        organization_id=uuid4(),
        company_name="Other Org Co",
        domain=CompanyDomain("otherorg.com"),
        created_at=_NOW,
    )

    use_case = PrioritizeAccounts(
        accounts=_FakeAccountRepository([mine, other_org_account], {}, {}),
        clock=_FakeClock(),
    )

    ranked = await use_case.execute(_ORG_ID)

    assert [s.account_id for s in ranked] == [mine.id]


async def test_every_ranked_account_carries_at_least_one_evidence_item() -> None:
    account = _account("Some Co")

    use_case = PrioritizeAccounts(
        accounts=_FakeAccountRepository([account], {}, {}),
        clock=_FakeClock(),
    )

    ranked = await use_case.execute(_ORG_ID)

    assert len(ranked) == 1
    assert len(ranked[0].evidence) > 0
