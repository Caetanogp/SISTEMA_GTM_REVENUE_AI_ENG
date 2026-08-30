"""Prompt loading helpers for the agent graph."""

from __future__ import annotations

from html import escape
from pathlib import Path

from revops.application.dto import AccountCandidate

_PROMPT_PATH = Path(__file__).with_name("prompts") / "prioritize_accounts.v1.md"


def load_prioritize_accounts_prompt(
    *, request_text: str, candidates: list[AccountCandidate]
) -> str:
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    return template.replace("{{request_text}}", escape(request_text, quote=False)).replace(
        "{{candidates}}", _render_candidates(candidates)
    )


def _render_candidates(candidates: list[AccountCandidate]) -> str:
    blocks: list[str] = []
    for candidate in candidates:
        sections = "\n".join(
            f"    - {section.label}: {section.text}" for section in candidate.context
        )
        blocks.append(
            "\n".join(
                [
                    f"- account_id: {candidate.account_id}",
                    f"  company_name: {candidate.company_name}",
                    f"  score: {candidate.score}",
                    f"  tier: {candidate.tier}",
                    f"  evidence: {candidate.evidence}",
                    f"  dropped_context_labels: {candidate.dropped_context_labels}",
                    f"  token_count: {candidate.token_count}",
                    "  context:",
                    sections or "    - none",
                ]
            )
        )
    return "\n\n".join(blocks)
