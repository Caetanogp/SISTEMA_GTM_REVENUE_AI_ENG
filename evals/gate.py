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

from evals.run import RUNNERS, SuiteReport

THRESHOLDS_PATH = Path(__file__).resolve().parent / "thresholds.toml"


def load_thresholds() -> dict[str, dict[str, float]]:
    with THRESHOLDS_PATH.open("rb") as f:
        return tomllib.load(f)


def _threshold_for(suite: str, thresholds: dict[str, dict[str, float]]) -> float:
    # Each suite declares exactly one metric threshold today (see evals/thresholds.toml).
    return next(iter(thresholds[suite].values()))


def evaluate_suite(name: str, thresholds: dict[str, dict[str, float]]) -> tuple[bool, SuiteReport]:
    report = RUNNERS[name]()
    minimum = _threshold_for(name, thresholds)
    return report.metric_value >= minimum, report


def main() -> int:
    thresholds = load_thresholds()
    all_passed = True
    for suite in RUNNERS:
        passed, report = evaluate_suite(suite, thresholds)
        minimum = _threshold_for(suite, thresholds)
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
