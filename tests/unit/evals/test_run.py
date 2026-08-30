"""Tests for evals/run.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.run import RUNNERS, run_suite, write_report


@pytest.mark.parametrize("suite", ["tool_selection", "lead_scoring"])
def test_run_suite_produces_a_sane_report(suite: str) -> None:
    report = run_suite(suite)
    assert report.suite == suite
    assert report.total_cases > 0
    assert report.correct_cases <= report.total_cases
    assert 0.0 <= report.metric_value <= 1.0


def test_lead_scoring_suite_is_a_full_regression_match() -> None:
    report = run_suite("lead_scoring")
    assert report.metric_value == 1.0
    assert report.failures == []


def test_all_suites_are_registered_as_runners() -> None:
    assert set(RUNNERS) == {"tool_selection", "lead_scoring"}


def test_write_report_writes_valid_json_to_the_given_directory(tmp_path: Path) -> None:
    report = run_suite("lead_scoring")
    path = write_report(report, reports_dir=tmp_path)
    assert path.parent == tmp_path
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["suite"] == "lead_scoring"
    assert payload["correct_cases"] == report.correct_cases
