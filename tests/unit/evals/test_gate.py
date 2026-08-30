"""Tests for evals/gate.py."""

from __future__ import annotations

from evals.gate import evaluate_suite, load_thresholds, main


def test_load_thresholds_declares_both_suites() -> None:
    thresholds = load_thresholds()
    assert set(thresholds) == {"tool_selection", "lead_scoring"}
    assert thresholds["lead_scoring"]["min_exact_match"] == 1.0
    assert thresholds["tool_selection"]["min_accuracy"] == 0.80


def test_lead_scoring_passes_its_own_threshold() -> None:
    thresholds = load_thresholds()
    passed, report = evaluate_suite("lead_scoring", thresholds)
    assert passed
    assert report.metric_value == 1.0


def test_tool_selection_passes_its_own_threshold() -> None:
    thresholds = load_thresholds()
    passed, report = evaluate_suite("tool_selection", thresholds)
    assert passed
    assert report.metric_value >= 0.80


def test_evaluate_suite_fails_when_the_threshold_is_impossible() -> None:
    thresholds = {"lead_scoring": {"min_exact_match": 1.01}}
    passed, _report = evaluate_suite("lead_scoring", thresholds)
    assert not passed


def test_main_exits_zero_when_every_suite_passes() -> None:
    assert main() == 0
