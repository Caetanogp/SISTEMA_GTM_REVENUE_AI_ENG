"""Tests for evals/scorers/lead_scoring.py."""

from __future__ import annotations

from evals.scorers.lead_scoring import load_cases, score_case, score_lead_scoring_dataset


def test_load_cases_matches_the_dataset_file() -> None:
    cases = load_cases()
    assert 12 <= len(cases) <= 18


def test_every_case_scores_correct_against_the_real_policy() -> None:
    for case in load_cases():
        assert score_case(case), case["id"]


def test_score_lead_scoring_dataset_reports_full_accuracy() -> None:
    result = score_lead_scoring_dataset()
    assert result.total == len(load_cases())
    assert result.correct == result.total
    assert result.failed_ids == []
    assert result.accuracy == 1.0


def test_score_case_catches_a_deliberately_wrong_expectation() -> None:
    tampered = dict(load_cases()[0])
    tampered["expected_score"] = (tampered["expected_score"] + 1) % 101
    assert not score_case(tampered)
