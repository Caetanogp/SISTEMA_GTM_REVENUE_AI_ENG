"""Structural checks for evals/datasets/tool_selection.jsonl.

This is not a scoring run (evals/scorers/ doesn't exist yet) - it only proves the dataset itself
is well-formed: valid JSONL, every case has the fields a future scorer will need, and the required
positive/negative coverage plan.md and AUTONOMOUS_QUEUE.md's Item 9 both call for is actually there.
"""

from __future__ import annotations

import json
from pathlib import Path

DATASET_PATH = Path(__file__).resolve().parents[3] / "evals" / "datasets" / "tool_selection.jsonl"
_KNOWN_TOOLS = {"search_accounts", "get_account_context", "create_task"}


def _load_cases() -> list[dict[str, object]]:
    lines = DATASET_PATH.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def test_dataset_file_exists() -> None:
    assert DATASET_PATH.is_file()


def test_every_line_is_valid_json_with_the_required_fields() -> None:
    cases = _load_cases()
    for case in cases:
        assert set(case) == {"id", "input", "expected_tool", "notes"}
        assert isinstance(case["id"], str)
        assert case["id"]
        assert isinstance(case["input"], str)
        assert case["input"]
        assert isinstance(case["notes"], str)
        assert case["notes"]
        expected_tool = case["expected_tool"]
        assert expected_tool is None or expected_tool in _KNOWN_TOOLS


def test_case_ids_are_unique() -> None:
    cases = _load_cases()
    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids))


def test_dataset_has_approximately_ten_cases() -> None:
    cases = _load_cases()
    assert 10 <= len(cases) <= 15


def test_every_known_tool_has_at_least_one_positive_case() -> None:
    cases = _load_cases()
    positive_tools = {case["expected_tool"] for case in cases if case["expected_tool"] is not None}
    assert positive_tools == _KNOWN_TOOLS


def test_at_least_three_negative_cases_that_must_not_select_create_task() -> None:
    """AUTONOMOUS_QUEUE.md Item 9: negative cases that must not select create_task.

    None here means "no tool, or a read tool - anything but create_task", matching plan.md's own
    example ("summarise this account" must NOT call create_task).
    """
    cases = _load_cases()
    negatives = [case for case in cases if case["expected_tool"] is None]
    assert len(negatives) >= 3


def test_negative_cases_document_why_create_task_is_wrong() -> None:
    cases = _load_cases()
    negatives = [case for case in cases if case["expected_tool"] is None]
    for case in negatives:
        assert "create_task" in str(case["notes"]).lower() or "task" in str(case["notes"]).lower()
