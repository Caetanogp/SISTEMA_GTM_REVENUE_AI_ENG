"""Value objects: immutable, defined by their content, validated on construction."""

from revops.domain.values.company_domain import CompanyDomain
from revops.domain.values.email import EmailAddress
from revops.domain.values.phone import PhoneNumber
from revops.domain.values.risk import RiskLevel
from revops.domain.values.score import Score, ScoreTier

__all__ = ["CompanyDomain", "EmailAddress", "PhoneNumber", "RiskLevel", "Score", "ScoreTier"]
