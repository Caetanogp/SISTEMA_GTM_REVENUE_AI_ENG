"""Risk classification: which tools exist, at what risk level, and whether HITL is required.

Deny by default (AGENTS.md, Security rules): a tool not on this registry is refused, not silently
allowed at some default risk level.
"""

from __future__ import annotations

from revops.domain.errors import PolicyViolationError
from revops.domain.values.risk import RiskLevel

# The tool risk matrix for SPEC-001 (docs/specs/SPEC-001-.../spec.md, "Tools and risk").
# Adding a tool means registering it here first - see docs/playbooks/agent-tool.md.
_TOOL_RISK: dict[str, RiskLevel] = {
    "search_accounts": RiskLevel.LOW,
    "get_account_context": RiskLevel.LOW,
    "create_task": RiskLevel.MEDIUM,
}


def classify(tool_name: str) -> RiskLevel:
    """Return the risk level for a tool. Raises PolicyViolationError if not on the allowlist."""
    try:
        return _TOOL_RISK[tool_name]
    except KeyError as exc:
        raise PolicyViolationError(f"tool '{tool_name}' is not on the allowlist") from exc


def requires_hitl(risk: RiskLevel) -> bool:
    """Whether a proposed action at this risk level must pause for human approval.

    SPEC-001 requires HITL for MEDIUM as well as HIGH: this slice exists specifically to prove the
    approval/resume path works, even though a MEDIUM-risk write like `create_task` would normally
    execute automatically once evals show that is safe (spec.md, "Tools and risk"). Loosen this
    only on evidence from the eval suite, not by assumption.
    """
    return risk >= RiskLevel.MEDIUM
