"""Prompt loading helpers for the agent graph."""

from __future__ import annotations

from html import escape
from pathlib import Path

from revops.application.dto import AccountCandidate, RuntimeToolEvidence
from revops.application.ports import ReplyRecord

_PROMPT_PATH = Path(__file__).with_name("prompts") / "prioritize_accounts.v2.md"


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


_RUNTIME_PROMPT_PATH = Path(__file__).with_name("prompts") / "agent_tool_runtime.v2.md"
_LEGACY_RUNTIME_PROMPT_PATH = Path(__file__).with_name("prompts") / "agent_tool_runtime.v1.md"
_REPLY_PROMPT_PATH = Path(__file__).with_name("prompts") / "classify_reply.v1.md"
_REPLY_OPEN = "<untrusted_reply>"
_REPLY_CLOSE = "</untrusted_reply>"
_REPLY_CONTEXT_LIMIT_BYTES = 4_096


def load_agent_tool_runtime_prompt(
    request_text: str,
    context_text: str,
    evidence: tuple[RuntimeToolEvidence, ...],
) -> str:
    """Fence untrusted request/context and expose only sanitized prior evidence."""
    return _load_runtime_prompt(_RUNTIME_PROMPT_PATH, request_text, context_text, evidence)


def load_legacy_agent_tool_runtime_prompt(
    request_text: str,
    context_text: str,
    evidence: tuple[RuntimeToolEvidence, ...],
) -> str:
    """Load the SPEC-009 contract for checkpoints created before SPEC-010."""
    return _load_runtime_prompt(_LEGACY_RUNTIME_PROMPT_PATH, request_text, context_text, evidence)


def load_classify_reply_prompt(reply: ReplyRecord) -> str:
    """Render the fixed reply prompt without changing authorized evidence offsets."""
    text = reply.reply.value
    if _REPLY_OPEN in text or _REPLY_CLOSE in text:
        raise ValueError("reply contains a reserved deterministic prompt delimiter")
    template = _REPLY_PROMPT_PATH.read_text(encoding="utf-8")
    rendered = template.replace("{{language}}", reply.reply.language.value).replace(
        "{{reply_text}}", text
    )
    if len(rendered.encode("utf-8")) > _REPLY_CONTEXT_LIMIT_BYTES:
        raise ValueError("reply classification context exceeds the 4096-byte limit")
    return rendered


def _load_runtime_prompt(
    path: Path,
    request_text: str,
    context_text: str,
    evidence: tuple[RuntimeToolEvidence, ...],
) -> str:
    template = path.read_text(encoding="utf-8")
    rendered_evidence = "\n".join(
        f"- sequence={item.sequence} tool={item.tool_name} risk={item.risk} outcome={item.outcome}"
        for item in evidence
    )
    return (
        template.replace("{{request_text}}", escape(request_text, quote=False))
        .replace("{{context_text}}", escape(context_text, quote=False))
        .replace("{{evidence}}", escape(rendered_evidence, quote=False))
    )
