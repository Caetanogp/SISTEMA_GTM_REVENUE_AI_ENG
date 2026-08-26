"""RiskLevel: how much scrutiny a proposed action requires.

See AGENTS.md, Security rules: "low (reads), medium (internal writes), high (external writes:
email, calendar, bulk operations)". Whether a given level requires human approval is a policy
decision, not an intrinsic property of the level itself — see domain/policies/risk.py.
"""

from __future__ import annotations

from enum import IntEnum


class RiskLevel(IntEnum):
    """Ordered so comparisons work: RiskLevel.HIGH > RiskLevel.MEDIUM > RiskLevel.LOW."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
