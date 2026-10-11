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


def _metrics_pass(report: SuiteReport, minimums: dict[str, float]) -> bool:
    metrics = report.metrics or {report.metric_name: report.metric_value}
    return all(
        metrics.get(metric.removeprefix("min_"), float("-inf")) >= minimum
        for metric, minimum in minimums.items()
    )


def evaluate_suite(name: str, thresholds: dict[str, dict[str, float]]) -> tuple[bool, SuiteReport]:
    report = ALL_RUNNERS[name]()
    mandatory_contract = name in {
        "rag_ingestion_contract",
        "rag_retrieval_contract",
        "agent_tool_runtime_contract",
        "research_outreach_contract",
        "grounded_generation_contract",
        "reply_runtime_contract",
        "reply_classification_contract",
    }
    minimums = {report.metric_name: 1.00} if mandatory_contract else thresholds[name]
    return _metrics_pass(report, minimums), report


def main() -> int:
    thresholds = load_thresholds()
    all_passed = True
    for suite in ALL_RUNNERS:
        passed, report = evaluate_suite(suite, thresholds)
        mandatory_contract = suite in {
            "rag_ingestion_contract",
            "rag_retrieval_contract",
            "agent_tool_runtime_contract",
            "research_outreach_contract",
            "grounded_generation_contract",
            "reply_runtime_contract",
            "reply_classification_contract",
        }
        minimums = {report.metric_name: 1.00} if mandatory_contract else thresholds[suite]
        status = "PASS" if passed else "FAIL"
        metrics = report.metrics or {report.metric_name: report.metric_value}
        detail = ", ".join(
            _format_metric(metric, minimum, metrics) for metric, minimum in minimums.items()
        )
        print(f"[{status}] {report.suite}: {detail} ({report.correct_cases}/{report.total_cases})")
        if not passed:
            print(f"  failed ids: {', '.join(report.failures)}")
            all_passed = False
    return 0 if all_passed else 1


def _format_metric(metric: str, minimum: float, metrics: dict[str, float]) -> str:
    name = metric.removeprefix("min_")
    value = metrics.get(name, float("nan"))
    return f"{name}={value:.2f} (threshold {minimum:.2f})"


if __name__ == "__main__":
    sys.exit(main())
