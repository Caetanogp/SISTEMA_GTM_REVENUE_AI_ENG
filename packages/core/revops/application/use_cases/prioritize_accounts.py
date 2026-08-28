"""`PrioritizeAccounts`: rank an organization's accounts using the deterministic domain policy.

No LLM call here - `domain.policies.prioritization` supplies the arithmetic and the evidence
trail; this use case only assembles context from the repository ports and shapes the result as
DTOs. Explanation/ranking-by-LLM is infrastructure/graph territory (plan.md).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from revops.application.dto import AccountScore
from revops.application.ports import AccountRepository, Clock
from revops.domain.policies.prioritization import prioritize_account


@dataclass(frozen=True, slots=True)
class PrioritizeAccounts:
    """Assemble context per account, score it, and return the accounts ranked highest first."""

    accounts: AccountRepository
    clock: Clock

    async def execute(self, organization_id: UUID) -> list[AccountScore]:
        accounts = await self.accounts.list_for_organization(organization_id)
        now = self.clock.now()

        scores = []
        for account in accounts:
            interactions = await self.accounts.list_interactions(organization_id, account.id)
            opportunities = await self.accounts.list_open_opportunities(organization_id, account.id)
            score, evidence = prioritize_account(list(interactions), list(opportunities), now)
            scores.append(
                AccountScore(
                    account_id=account.id,
                    score=score.value,
                    tier=score.tier,
                    evidence=evidence,
                )
            )

        scores.sort(key=lambda s: s.score, reverse=True)
        return scores
