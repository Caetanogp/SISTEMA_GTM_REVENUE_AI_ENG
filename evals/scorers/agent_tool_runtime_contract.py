"""Deterministic contract scorer for the bounded single-agent tool runtime."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ValidationError
from revops.application.dto import (
    AgentToolDecision,
    CreateTaskToolArgs,
    GetAccountContextArgs,
    SearchAccountsArgs,
)
from revops.domain.values.risk import RiskLevel
from revops.domain.values.runtime import RuntimeFailureCode, ToolCallBudget, expected_tool

DATASET_PATH = (
    Path(__file__).resolve().parents[1] / "datasets" / "agent_tool_runtime_contract.jsonl"
)

_ARGUMENT_MODELS: dict[str, type[BaseModel]] = {
    "search_accounts": SearchAccountsArgs,
    "get_account_context": GetAccountContextArgs,
    "create_task": CreateTaskToolArgs,
}


@dataclass(frozen=True, slots=True)
class ScoreResult:
    total: int
    correct: int
    failed_ids: list[str]

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0


def load_cases() -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in DATASET_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _score_decision(case: dict[str, object]) -> bool:
    try:
        decision = AgentToolDecision.model_validate(case["decision"])
        tool_name = decision.tool_name
        if expected_tool(decision.outcome) != tool_name:
            return not bool(case["expected"])
        argument_model = _ARGUMENT_MODELS[tool_name]
        argument_model.model_validate(decision.arguments)
        return bool(case["expected"])
    except (KeyError, ValidationError, ValueError):
        return not bool(case["expected"])


def _score_budget(case: dict[str, object]) -> bool:
    budget = ToolCallBudget(calls=int(str(case["calls"])), writes=int(str(case["writes"])))
    risk = RiskLevel.MEDIUM if case["risk"] == "medium" else RiskLevel.LOW
    return budget.reserve(risk) == RuntimeFailureCode(str(case["expected"]))


def score_agent_tool_runtime_contract_dataset() -> ScoreResult:
    cases = load_cases()
    failed_ids: list[str] = []
    for case in cases:
        passed = _score_decision(case) if case["kind"] == "decision" else _score_budget(case)
        if not passed:
            failed_ids.append(str(case["id"]))
    return ScoreResult(
        total=len(cases),
        correct=len(cases) - len(failed_ids),
        failed_ids=failed_ids,
    )
