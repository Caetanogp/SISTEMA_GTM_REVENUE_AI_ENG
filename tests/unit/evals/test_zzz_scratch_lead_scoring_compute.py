"""Structural and regression checks for evals/datasets/lead_scoring.jsonl.

Unlike tool_selection.jsonl (which needs a future LLM-backed scorer), the expected score and tier
here are fully deterministic: `prioritize_account` is pure domain logic, so this test reconstructs
each case's interactions/opportunities and asserts the recorded expected_score/expected_tier still
match what the policy actually computes. That makes this dataset a regression guard on
`policies/prioritization.py`, not just a schema check - if a future change to the scoring weights
or thresholds changes an outcome, this test catches it here rather than only downstream.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from revops.domain.entities.interaction import Interaction
from revops.domain.entities.opportunity import Opportunity, OpportunityStage
from revops.domain.policies.prioritization import prioritize_account

DATASET_PATH = Path(__file__).resolve().parents[3] / "evals" / "datasets" / "lead_scoring.jsonl"
_TIERS = {"hot", "warm", "cold"}
_STAGES = {stage.value for stage in OpportunityStage}


def _load_cases() -> list[dict[str, Any]]:
    lines = DATASET_PATH.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def test_dataset_file_exists() -> None:
    assert DATASET_PATH.is_file()


def test_every_line_is_valid_json_with_the_required_fields() -> None:
    cases = _load_cases()
    for case in cases:
        assert set(case) == {
            "id",
            "account_name",
            "now",
            "interactions",
            "opportunities",
            "expected_score",
            "expected_tier",
            "notes",
        }
        assert isinstance(case["id"], str)
        assert case["id"]
        assert isinstance(case["account_name"], str)
        assert case["account_name"]
        assert isinstance(case["notes"], str)
        assert case["notes"]
        assert isinstance(case["expected_score"], int)
        assert 0 <= case["expected_score"] <= 100
        assert case["expected_tier"] in _TIERS
        for interaction in case["interactions"]:
            assert set(interaction) == {"days_ago", "channel"}
            assert isinstance(interaction["days_ago"], int)
            assert interaction["days_ago"] >= 0
            assert isinstance(interaction["channel"], str)
            assert interaction["channel"]
        for opportunity in case["opportunities"]:
            assert set(opportunity) == {"stage", "value"}
            assert opportunity["stage"] in _STAGES
            assert isinstance(opportunity["value"], int)
            assert opportunity["value"] >= 0
        # Fails loudly (invalid isoformat) if `now` is ever malformed.
        datetime.fromisoformat(str(case["now"]))


def test_case_ids_are_unique() -> None:
    cases = _load_cases()
    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids))


def test_dataset_has_approximately_fifteen_cases() -> None:
    cases = _load_cases()
    assert 12 <= len(cases) <= 18


def test_all_three_tiers_are_represented() -> None:
    cases = _load_cases()
    tiers = {case["expected_tier"] for case in cases}
    assert tiers == _TIERS


def test_expected_score_and_tier_match_the_actual_domain_policy() -> None:
    """The regression guard: recompute via prioritize_account and compare, case by case."""
    org_id = uuid4()
    for case in _load_cases():
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
        assert score.value == case["expected_score"], case["id"]
        assert score.tier.value == case["expected_tier"], case["id"]
