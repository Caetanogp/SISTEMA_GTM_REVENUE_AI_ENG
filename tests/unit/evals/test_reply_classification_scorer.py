"""Tests for the offline reply-classification dataset and scorers."""

from __future__ import annotations

from collections import Counter

from revops.domain.values.reply import ReplyCategory

from evals.scorers.reply_classification import (
    load_cases,
    predict_category,
    score_reply_classification_dataset,
)
from evals.scorers.reply_classification_contract import (
    load_cases as load_contract_cases,
)
from evals.scorers.reply_classification_contract import (
    score_case,
    score_reply_classification_contract_dataset,
)


def test_dataset_has_five_synthetic_cases_per_category_and_language() -> None:
    cases = load_cases()
    assert len(cases) == 90
    assert all(set(case) == {"id", "input", "expected", "metadata"} for case in cases)
    assert all(
        case["metadata"] == {"language": case["metadata"]["language"], "synthetic": True}
        for case in cases
    )
    coverage = Counter((case["expected"], case["metadata"]["language"]) for case in cases)
    assert coverage == {
        (category.value, language): 5 for category in ReplyCategory for language in ("en", "pt")
    }
    assert len({case["id"] for case in cases}) == len(cases)


def test_baseline_metrics_meet_the_approved_floors() -> None:
    result = score_reply_classification_dataset()
    assert result.total == 90
    assert result.accuracy >= 0.85
    assert result.macro_f1 >= 0.80
    assert result.unsubscribe_recall == 1.0
    assert result.failed_ids == []


def test_explicit_opt_out_marker_wins_in_the_independent_baseline() -> None:
    assert (
        predict_category("Please unsubscribe me, I am interested in a demo.")
        is ReplyCategory.UNSUBSCRIBE
    )


def test_contract_cases_all_pass() -> None:
    cases = load_contract_cases()
    assert all(score_case(case) for case in cases)
    result = score_reply_classification_contract_dataset()
    assert result.accuracy == 1.0
    assert result.failed_ids == []
