"""Deterministic scorer for evals/datasets/lead_scoring.jsonl.

The "model" under test is not an LLM: `prioritize_account` is the actual deterministic domain
policy that ships in production (`packages/core/revops/domain/policies/prioritization.py`).
Scoring it against its own golden dataset is a regression guard, not a quality measurement - a
mismatch here means the domain scoring rules changed, and the eval gate should catch that
immediately, before it reaches a real account.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from revops.domain.entities.interaction import Interaction
from revops.domain.entities.opportunity import Opportunity, OpportunityStage
from revops.domain.policies.prioritization import prioritize_account

DATASET_PATH = Path(__file__).resolve().parents[1] / "datasets" / "lead_scoring.jsonl"


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


def score_case(case: dict[str, Any]) -> bool:
    """True if `prioritize_account` reproduces this case's recorded expected outcome."""
    org_id = uuid4()
    account_id = uuid4()
    now = datetime.fromisoformat(str(case["now"]))
    interactions = [
        Interaction(
            id=uuid4(),
            organization_id=org_id,
            account_id=account_id,
            channel=spec["channel"],
            occurred_at=now - timedelta(days=spec["days_ago"]),
        )
        for spec in case["interactions"]
    ]
    opportunities = [
        Opportunity(
            id=uuid4(),
            organization_id=org_id,
            account_id=account_id,
            stage=OpportunityStage(spec["stage"]),
            value=Decimal(spec["value"]),
        )
        for spec in case["opportunities"]
    ]
    score, _evidence = prioritize_account(interactions, opportunities, now)
    expected_score: int = case["expected_score"]
    expected_tier: str = case["expected_tier"]
    return score.value == expected_score and score.tier.value == expected_tier


def score_lead_scoring_dataset() -> ScoreResult:
    cases = load_cases()
    failed_ids = [str(case["id"]) for case in cases if not score_case(case)]
    return ScoreResult(
        total=len(cases), correct=len(cases) - len(failed_ids), failed_ids=failed_ids
    )
