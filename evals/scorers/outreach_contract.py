"""Deterministic contract scorers for SPEC-010 research and grounded generation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError
from revops.application.dto import ClaimVerificationOutput, FollowupGenerationOutput


@dataclass(frozen=True, slots=True)
class ScoreResult:
    total: int
    correct: int
    failed_ids: list[str]

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0


def _load(name: str) -> list[dict[str, object]]:
    path = Path(__file__).resolve().parents[1] / "datasets" / f"{name}.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def score_research_outreach_contract_dataset() -> ScoreResult:
    cases = _load("research_outreach_contract")
    failures: list[str] = []
    for case in cases:
        source_values_raw = case["source_ids"]
        fact_values = case.get("fact_source_ids", [])
        source_values = source_values_raw if isinstance(source_values_raw, list) else []
        sources = {str(item) for item in source_values}
        facts = fact_values if isinstance(fact_values, list) else []
        valid = bool(sources) and all(str(item) in sources for item in facts)
        if not bool(case["authorized"]):
            valid = False
        if bool(case["expected_complete"]):
            valid = valid and bool(case["facts"])
        else:
            valid = not valid or not bool(case["facts"])
        if valid != bool(case["expected_pass"]):
            failures.append(str(case["id"]))
    return ScoreResult(len(cases), len(cases) - len(failures), failures)


def score_grounded_generation_contract_dataset() -> ScoreResult:
    cases = _load("grounded_generation_contract")
    failures: list[str] = []
    for case in cases:
        try:
            draft = FollowupGenerationOutput.model_validate(case["draft"])
            verification = ClaimVerificationOutput.model_validate(case["verification"])
            evidence_values_raw = case["evidence_ids"]
            evidence_values = evidence_values_raw if isinstance(evidence_values_raw, list) else []
            evidence = {str(item) for item in evidence_values}
            references_valid = all(
                set(claim.source_ids).issubset(evidence) for claim in draft.claims
            )
            passed = (references_valid and verification.accepted) == bool(case["expected_accepted"])
        except (ValidationError, KeyError, TypeError):
            passed = not bool(case["expected_accepted"])
        if not passed:
            failures.append(str(case["id"]))
    return ScoreResult(len(cases), len(cases) - len(failures), failures)
