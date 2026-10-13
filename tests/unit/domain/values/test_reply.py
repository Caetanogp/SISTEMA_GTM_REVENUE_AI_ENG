import math
from typing import cast

import pytest
from revops.domain.errors import PolicyViolationError
from revops.domain.values.reply import (
    REPLY_CONFIDENCE_THRESHOLD,
    ReplyCategory,
    ReplyClassification,
    ReplyClassificationStatus,
    ReplyEvidence,
    ReplyLanguage,
    ReplyNextAction,
    ReplyText,
    evaluate_reply_classification,
    mapped_next_action,
)


@pytest.mark.parametrize(
    ("category", "action"),
    [
        (ReplyCategory.INTERESTED, ReplyNextAction.PREPARE_FOLLOWUP),
        (ReplyCategory.NOT_INTERESTED, ReplyNextAction.END_FOLLOWUP),
        (ReplyCategory.OBJECTION, ReplyNextAction.REVIEW_OBJECTION),
        (ReplyCategory.QUESTION, ReplyNextAction.ANSWER_QUESTION),
        (ReplyCategory.OUT_OF_OFFICE, ReplyNextAction.WAIT_FOR_RETURN),
        (ReplyCategory.WRONG_PERSON, ReplyNextAction.REVIEW_CONTACT),
        (ReplyCategory.UNSUBSCRIBE, ReplyNextAction.HONOR_OPT_OUT),
        (ReplyCategory.AUTOMATIC_RESPONSE, ReplyNextAction.REVIEW_AUTOMATIC_RESPONSE),
        (ReplyCategory.UNKNOWN, ReplyNextAction.MANUAL_REVIEW),
    ],
)
def test_category_mapping_is_the_approved_contract(
    category: ReplyCategory, action: ReplyNextAction
) -> None:
    assert mapped_next_action(category) is action


def _classification(
    category: ReplyCategory = ReplyCategory.INTERESTED,
    confidence: float = REPLY_CONFIDENCE_THRESHOLD,
    language: ReplyLanguage = ReplyLanguage.ENGLISH,
    evidence: tuple[ReplyEvidence, ...] = (ReplyEvidence(0, 4),),
    ambiguous: bool = False,
) -> ReplyClassification:
    return ReplyClassification(category, confidence, language, evidence, ambiguous)


def test_threshold_is_inclusive() -> None:
    reply = ReplyText("Yes!", ReplyLanguage.ENGLISH)
    outcome = evaluate_reply_classification(reply, _classification())
    assert outcome.status is ReplyClassificationStatus.CLASSIFIED
    assert outcome.recommended_action is ReplyNextAction.PREPARE_FOLLOWUP


@pytest.mark.parametrize("confidence", [0.0, REPLY_CONFIDENCE_THRESHOLD - 0.01])
def test_low_confidence_requires_manual_review(confidence: float) -> None:
    reply = ReplyText("Yes!", ReplyLanguage.ENGLISH)
    outcome = evaluate_reply_classification(reply, _classification(confidence=confidence))
    assert outcome.status is ReplyClassificationStatus.REVIEW_REQUIRED
    assert outcome.recommended_action is ReplyNextAction.MANUAL_REVIEW


@pytest.mark.parametrize("confidence", [-0.1, 1.1, math.inf, math.nan])
def test_confidence_must_be_finite_and_in_range(confidence: float) -> None:
    with pytest.raises(PolicyViolationError):
        _classification(confidence=confidence)


@pytest.mark.parametrize(
    "classification",
    [
        _classification(ambiguous=True),
        _classification(language=ReplyLanguage.PORTUGUESE),
        _classification(evidence=(ReplyEvidence(0, 5),)),
        _classification(evidence=()),
    ],
)
def test_ambiguous_incompatible_or_invalid_evidence_requires_review(
    classification: ReplyClassification,
) -> None:
    reply = ReplyText("Yes!", ReplyLanguage.ENGLISH)
    outcome = evaluate_reply_classification(reply, classification)
    assert outcome.status is ReplyClassificationStatus.REVIEW_REQUIRED
    assert outcome.recommended_action is ReplyNextAction.MANUAL_REVIEW


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("Please unsubscribe me, but I liked the demo.", ReplyLanguage.ENGLISH),
        ("Por favor, descadastre-me, mas gostei da demonstração.", ReplyLanguage.PORTUGUESE),
    ],
)
def test_explicit_unsubscribe_precedes_commercial_category(
    text: str, language: ReplyLanguage
) -> None:
    reply = ReplyText(text, language)
    evidence = ReplyEvidence(0, len(text))
    outcome = evaluate_reply_classification(
        reply,
        _classification(language=language, evidence=(evidence,)),
    )
    assert outcome.category is ReplyCategory.UNSUBSCRIBE
    assert outcome.status is ReplyClassificationStatus.CLASSIFIED
    assert outcome.recommended_action is ReplyNextAction.HONOR_OPT_OUT


def test_reply_and_evidence_bounds_are_enforced() -> None:
    with pytest.raises(PolicyViolationError):
        ReplyText("", ReplyLanguage.ENGLISH)
    with pytest.raises(PolicyViolationError):
        ReplyText("x" * 8_001, ReplyLanguage.PORTUGUESE)
    with pytest.raises(PolicyViolationError):
        ReplyEvidence(2, 2)
    with pytest.raises(PolicyViolationError):
        ReplyClassification(
            ReplyCategory.INTERESTED,
            REPLY_CONFIDENCE_THRESHOLD,
            ReplyLanguage.ENGLISH,
            cast(tuple[ReplyEvidence, ...], [ReplyEvidence(0, 1)]),
        )
