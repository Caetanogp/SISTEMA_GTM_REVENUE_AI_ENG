"""Deterministic contract scorer for reply-classification safety policy."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from revops.domain.values.reply import (
    ReplyCategory,
    ReplyClassification,
    ReplyClassificationStatus,
    ReplyEvidence,
    ReplyLanguage,
    ReplyNextAction,
    ReplyText,
    evaluate_reply_classification,
)

DATASET_PATH = (
    Path(__file__).resolve().parents[1] / "datasets" / "reply_classification_contract.jsonl"
)


@dataclass(frozen=True, slots=True)
class ScoreResult:
    total: int
    correct: int
    failed_ids: list[str]

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0


def load_cases() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in DATASET_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def score_case(case: dict[str, Any]) -> bool:
    classification_data = dict(case["classification"])
    evidence = tuple(ReplyEvidence(**item) for item in classification_data.pop("evidence"))
    outcome = evaluate_reply_classification(
        ReplyText(str(case["input"]), ReplyLanguage(str(case["language"]))),
        ReplyClassification(
            category=ReplyCategory(str(classification_data["category"])),
            confidence=float(classification_data["confidence"]),
            language=ReplyLanguage(str(classification_data["language"])),
            evidence=evidence,
            ambiguous=bool(classification_data["ambiguous"]),
        ),
    )
    expected = case["expected"]
    return (
        outcome.category is ReplyCategory(str(expected["category"]))
        and outcome.status is ReplyClassificationStatus(str(expected["status"]))
        and outcome.recommended_action is ReplyNextAction(str(expected["recommended_action"]))
    )


def score_reply_classification_contract_dataset() -> ScoreResult:
    cases = load_cases()
    failed_ids = [str(case["id"]) for case in cases if not score_case(case)]
    return ScoreResult(len(cases), len(cases) - len(failed_ids), failed_ids)
