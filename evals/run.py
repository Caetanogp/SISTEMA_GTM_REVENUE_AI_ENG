"""Offline eval runner.

Loads the golden datasets under `evals/datasets/` and scores each with its deterministic scorer
under `evals/scorers/` - never a real network call to an LLM provider, so this runs with no `.env`
and no provider credentials. Writes one JSON report per suite under `evals/reports/` (git-ignored;
the durable baseline snapshot lives in
`docs/specs/SPEC-001-vertical-slice-account-prioritization/eval-baseline.md`).

Usage:
    python -m evals.run --suite all
    python -m evals.run --suite tool_selection
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from evals.scorers.lead_scoring import score_lead_scoring_dataset
from evals.scorers.tool_selection import score_tool_selection_dataset

REPORTS_DIR = Path(__file__).resolve().parent / "reports"
SUITES = ("tool_selection", "lead_scoring")


@dataclass(frozen=True, slots=True)
class SuiteReport:
    suite: str
    metric_name: str
    metric_value: float
    total_cases: int
    correct_cases: int
    failures: list[str]
    generated_at: str


def run_tool_selection() -> SuiteReport:
    result = score_tool_selection_dataset()
    return SuiteReport(
        suite="tool_selection",
        metric_name="accuracy",
        metric_value=result.accuracy,
        total_cases=result.total,
        correct_cases=result.correct,
        failures=result.failed_ids,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )


def run_lead_scoring() -> SuiteReport:
    result = score_lead_scoring_dataset()
    return SuiteReport(
        suite="lead_scoring",
        metric_name="exact_match",
        metric_value=result.accuracy,
        total_cases=result.total,
        correct_cases=result.correct,
        failures=result.failed_ids,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )


RUNNERS: dict[str, Callable[[], SuiteReport]] = {
    "tool_selection": run_tool_selection,
    "lead_scoring": run_lead_scoring,
}


def run_suite(name: str) -> SuiteReport:
    return RUNNERS[name]()


def write_report(report: SuiteReport, reports_dir: Path = REPORTS_DIR) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"{report.suite}.json"
    path.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the offline eval suite(s).")
    parser.add_argument("--suite", choices=(*SUITES, "all"), default="all")
    args = parser.parse_args()

    suites = SUITES if args.suite == "all" else (args.suite,)
    for suite in suites:
        report = run_suite(suite)
        path = write_report(report)
        print(
            f"{report.suite}: {report.metric_name}={report.metric_value:.2f} "
            f"({report.correct_cases}/{report.total_cases}) -> {path}"
        )
        if report.failures:
            print(f"  failed ids: {', '.join(report.failures)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
