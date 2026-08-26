"""Account: a company - the unit of prioritization. Deduplicated on its normalized domain."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from revops.domain.values.company_domain import CompanyDomain


@dataclass(slots=True)
class Account:
    id: UUID
    organization_id: UUID
    company_name: str
    domain: CompanyDomain
    created_at: datetime
