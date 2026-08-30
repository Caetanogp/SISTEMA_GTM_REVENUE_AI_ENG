"""`PrioritizeAccounts`: rank an organization's accounts using the deterministic domain policy.

No LLM call here - `domain.policies.prioritization` supplies the arithmetic and the evidence
trail; this use case only assembles context from the repository ports and shapes the result as
DTOs. Explanation/ranking-by-LLM is infrastructure/graph territory (plan.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from revops.application.context.builder import ContextBuilder
from revops.application.dto import AccountCandidate, ContextSectionSnapshot
from revops.application.ports import AccountRepository, Clock
from revops.domain.entities.interaction import Interaction
from revops.domain.entities.opportunity import Opportunity
from revops.domain.policies.prioritization import prioritize_account
from revops.domain.values.score import ScoreTier


@dataclass(frozen=True, slots=True)
class PrioritizeAccounts:
    """Assemble context per account, score it, and return the accounts ranked highest first."""

    accounts: AccountRepository
    clock: Clock
    context_builder: ContextBuilder = field(default_factory=ContextBuilder)

    async def execute(
        self, organization_id: UUID, *, token_budget: int = 4096
    ) -> list[AccountCandidate]:
        accounts = await self.accounts.list_for_organization(organization_id)
        now = self.clock.now()
        accounts_by_id = {account.id: account for account in accounts}

        scored: list[
            tuple[int, UUID, str, list[Interaction], list[Opportunity], list[str], ScoreTier]
        ]
        scored = []
        for account in accounts:
            interactions = await self.accounts.list_interactions(organization_id, account.id)
            opportunities = await self.accounts.list_open_opportunities(organization_id, account.id)
            score, evidence = prioritize_account(list(interactions), list(opportunities), now)
            scored.append(
                (
                    score.value,
                    account.id,
                    account.company_name,
                    list(interactions),
                    list(opportunities),
                    evidence,
                    score.tier,
                )
            )

        scored.sort(key=lambda item: item[0], reverse=True)
        remaining = token_budget
        candidates: list[AccountCandidate] = []
        for (
            score_value,
            account_id,
            company_name,
            interactions,
            opportunities,
            evidence,
            tier,
        ) in scored:
            account = accounts_by_id[account_id]
            context = self.context_builder.build(
                account,
                interactions,
                opportunities,
                token_budget=max(remaining, 0),
            )
            remaining -= context.token_count
            candidates.append(
                AccountCandidate(
                    account_id=account_id,
                    company_name=company_name,
                    score=score_value,
                    tier=tier,
                    evidence=evidence,
                    context=[
                        ContextSectionSnapshot(label=section.label, text=section.text)
                        for section in context.sections
                    ],
                    dropped_context_labels=context.dropped_labels,
                    token_count=context.token_count,
                )
            )
        return candidates
