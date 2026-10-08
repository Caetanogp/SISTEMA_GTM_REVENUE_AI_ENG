"""Deterministic no-network adapters used by SPEC-010 contract tests and evals."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from uuid import UUID

from revops.application.ports import (
    CompanyResearcher,
    OutreachContextProvider,
    ResearchPage,
    TrustedRunContext,
)
from revops.domain.entities.account import Account


@dataclass(frozen=True, slots=True)
class FixtureCompanyResearcher(CompanyResearcher):
    """Return synthetic pages only; this adapter cannot make a network request."""

    pages: tuple[ResearchPage, ...]

    async def research(
        self, *, context: TrustedRunContext, account: Account, objective: str
    ) -> Sequence[ResearchPage]:
        del context, account, objective
        return self.pages


@dataclass(frozen=True, slots=True)
class StaticOutreachContextProvider(OutreachContextProvider):
    """Provide a bounded synthetic CRM/RAG envelope for deterministic tests."""

    context: Mapping[str, object]

    async def build(
        self,
        *,
        context: TrustedRunContext,
        account_id: UUID,
        contact_id: UUID | None,
        objective: str,
    ) -> Mapping[str, object]:
        del context, account_id, contact_id, objective
        return dict(self.context)
