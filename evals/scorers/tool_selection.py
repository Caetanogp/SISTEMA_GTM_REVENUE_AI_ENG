"""Heuristic baseline scorer for evals/datasets/tool_selection.jsonl.

SPEC-001's shipped graph has no dynamic tool router yet - `propose_action` always drafts exactly
one `create_task`, chosen deterministically by `PrioritizeAccounts`, never picked among several
tools by an LLM. There is therefore no real product code path this scorer could exercise today,
with or without provider credentials.

`predict_tool` is a small, explicit, rule-based baseline standing in for that future LLM-backed
router - not a claim about current agent behaviour. Its only purpose is to give
`evals/thresholds.toml` a genuine, reproducible number today, so a real router built later has a
floor to beat rather than a first number invented from nothing. When that router exists, this
module should be replaced by a scorer that calls it (via a real or fake LLM gateway, per
`packages/core/revops/infrastructure/llm/fake.py`), not extended further.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DATASET_PATH = Path(__file__).resolve().parents[1] / "datasets" / "tool_selection.jsonl"

NO_TOOL = "no_tool"

# Checked before anything else: an adversarial or explicit refusal/no-op request must never fall
# through to the create_task branch below, even when it also contains create_task-shaped language.
_REFUSAL_PHRASES = ("ignore your instructions",)
_NO_ACTION_PHRASES = ("don't do anything",)
_CREATE_TASK_PHRASES = ("create a task", "remind", "follow up", "follow-up")
_SEARCH_PHRASES = (
    "which accounts",
    "show me every",
    "list the accounts",
    "accounts are in",
    "accounts need",
)


def predict_tool(text: str) -> str:
    """Returns NO_TOOL, "search_accounts", "create_task", or "get_account_context" (the default
    for a named-single-account request, including summaries and factual lookups)."""
    lowered = text.lower()
    if any(phrase in lowered for phrase in _REFUSAL_PHRASES):
        return NO_TOOL
    if any(phrase in lowered for phrase in _NO_ACTION_PHRASES):
        return NO_TOOL
    if any(phrase in lowered for phrase in _CREATE_TASK_PHRASES):
        return "create_task"
    if any(phrase in lowered for phrase in _SEARCH_PHRASES):
        return "search_accounts"
    return "get_account_context"


@dataclass(frozen=True, slots=True)
class ScoreResult:
    total: int
    correct: int
    failed_ids: list[str]

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0


def load_cases() -> list[dict[str, Any]]:
    lines = DATASET_PATH.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def is_correct(expected_tool: object, predicted: str) -> bool:
    """`expected_tool: null` means "no tool, or a read tool - anything but create_task" (see
    tests/unit/evals/test_tool_selection_dataset.py); every other value needs an exact match."""
    if expected_tool is None:
        return predicted != "create_task"
    return predicted == expected_tool


def score_tool_selection_dataset() -> ScoreResult:
    cases = load_cases()
    failed_ids = [
        str(case["id"])
        for case in cases
        if not is_correct(case["expected_tool"], predict_tool(str(case["input"])))
    ]
    return ScoreResult(
        total=len(cases), correct=len(cases) - len(failed_ids), failed_ids=failed_ids
    )
