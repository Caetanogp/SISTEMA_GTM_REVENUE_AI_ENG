"""Per-task context assembly under an explicit token budget.

AGENTS.md: "Build context per task with a token budget. Never dump the whole CRM into a prompt."
Sections are assembled in a fixed priority order - account, then opportunities, then interactions -
and truncated from the *end* of that order the moment the budget would be exceeded, rather than
silently overflowing it.
"""

from __future__ import annotations

from dataclasses import dataclass

from revops.domain.entities.account import Account
from revops.domain.entities.interaction import Interaction
from revops.domain.entities.opportunity import Opportunity

# Rough token estimate for English text - no tokenizer dependency belongs in the application layer,
# and this only needs to be a stable, conservative approximation, not exact.
_CHARS_PER_TOKEN = 4


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


@dataclass(frozen=True, slots=True)
class ContextSection:
    """One labeled slice of context, in the priority order `ContextBuilder` assembles them."""

    label: str
    text: str


@dataclass(frozen=True, slots=True)
class TaskContext:
    """The context that fit inside the budget, plus which lower-priority sections were dropped."""

    sections: list[ContextSection]
    dropped_labels: list[str]
    token_count: int


def _account_section(account: Account) -> ContextSection:
    since = account.created_at.date()
    text = f"Account: {account.company_name} ({account.domain}), customer since {since}"
    return ContextSection(label="account", text=text)


def _opportunities_section(opportunities: list[Opportunity]) -> ContextSection:
    if not opportunities:
        return ContextSection(label="opportunities", text="No opportunities on record.")
    lines = [f"- {o.stage.value}: ${o.value:,.0f}" for o in opportunities]
    return ContextSection(label="opportunities", text="\n".join(lines))


def _interactions_section(interactions: list[Interaction]) -> ContextSection:
    if not interactions:
        return ContextSection(label="interactions", text="No recorded interactions.")
    lines = [f"- {i.occurred_at.date()} via {i.channel}: {i.summary}" for i in interactions]
    return ContextSection(label="interactions", text="\n".join(lines))


class ContextBuilder:
    """Assembles account/opportunities/interactions into a token-budgeted `TaskContext`.

    Priority order (most to least important) is fixed: account, opportunities, interactions. Once
    a section would push the running total past `token_budget`, that section and every section
    after it in this order are dropped - never a partial/silent overflow.
    """

    def build(
        self,
        account: Account,
        interactions: list[Interaction],
        opportunities: list[Opportunity],
        *,
        token_budget: int,
    ) -> TaskContext:
        candidates = [
            _account_section(account),
            _opportunities_section(opportunities),
            _interactions_section(interactions),
        ]

        included: list[ContextSection] = []
        dropped_labels: list[str] = []
        used_tokens = 0
        budget_exceeded = False

        for section in candidates:
            cost = _estimate_tokens(section.text)
            if budget_exceeded or used_tokens + cost > token_budget:
                budget_exceeded = True
                dropped_labels.append(section.label)
                continue
            included.append(section)
            used_tokens += cost

        return TaskContext(
            sections=included, dropped_labels=dropped_labels, token_count=used_tokens
        )
