"""Deterministic pass/fail gate for the offline eval suite.

Never trusts a stale report file - re-scores fresh every run (same functions as evals/run.py), so
the gate can never pass on yesterday's numbers after today's code regressed something. CI (or a
human) treats a non-zero exit here as a merge blocker, per AGENTS.md's Definition of Done: "the
eval suite is not regressed".

Usage:
    python -m evals.gate
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

from evals.run import ALL_RUNNERS, SuiteReport

THRESHOLDS_PATH = Path(__file__).resolve().parent / "thresholds.toml"


def load_thresholds() -> dict[str, dict[str, float]]:
    with THRESHOLDS_PATH.open("rb") as f:
        return tomllib.load(f)


def _threshold_for(suite: str, thresholds: dict[str, dict[str, float]]) -> float:
    # Each suite declares exactly one metric threshold today (see evals/thresholds.toml).
    return next(iter(thresholds[suite].values()))


def evaluate_suite(name: str, thresholds: dict[str, dict[str, float]]) -> tuple[bool, SuiteReport]:
    report = ALL_RUNNERS[name]()
    mandatory_contract = name in {
        "rag_ingestion_contract",
        "rag_retrieval_contract",
        "agent_tool_runtime_contract",
    }
    minimum = 1.00 if mandatory_contract else _threshold_for(name, thresholds)
    return report.metric_value >= minimum, report


def main() -> int:
    thresholds = load_thresholds()
    all_passed = True
    for suite in ALL_RUNNERS:
        passed, report = evaluate_suite(suite, thresholds)
        mandatory_contract = suite in {
            "rag_ingestion_contract",
            "rag_retrieval_contract",
            "agent_tool_runtime_contract",
        }
        minimum = 1.00 if mandatory_contract else _threshold_for(suite, thresholds)
        status = "PASS" if passed else "FAIL"
        print(
            f"[{status}] {report.suite}: {report.metric_name}={report.metric_value:.2f} "
            f"(threshold {minimum:.2f}, {report.correct_cases}/{report.total_cases})"
        )
        if not passed:
            print(f"  failed ids: {', '.join(report.failures)}")
            all_passed = False
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
