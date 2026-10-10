"""Immutable values and deterministic policy for bounded reply classification."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

from revops.domain.errors import PolicyViolationError

REPLY_CONFIDENCE_THRESHOLD = 0.80


class ReplyLanguage(StrEnum):
    """Languages supported by the current reply-classification boundary."""

    ENGLISH = "en"
    PORTUGUESE = "pt"


class ReplyCategory(StrEnum):
    INTERESTED = "interested"
    NOT_INTERESTED = "not_interested"
    OBJECTION = "objection"
    QUESTION = "question"
    OUT_OF_OFFICE = "out_of_office"
    WRONG_PERSON = "wrong_person"
    UNSUBSCRIBE = "unsubscribe"
    AUTOMATIC_RESPONSE = "automatic_response"
    UNKNOWN = "unknown"


class ReplyNextAction(StrEnum):
    PREPARE_FOLLOWUP = "prepare_followup"
    END_FOLLOWUP = "end_followup"
    REVIEW_OBJECTION = "review_objection"
    ANSWER_QUESTION = "answer_question"
    WAIT_FOR_RETURN = "wait_for_return"
    REVIEW_CONTACT = "review_contact"
    HONOR_OPT_OUT = "honor_opt_out"
    REVIEW_AUTOMATIC_RESPONSE = "review_automatic_response"
    MANUAL_REVIEW = "manual_review"


class ReplyClassificationStatus(StrEnum):
    CLASSIFIED = "classified"
    REVIEW_REQUIRED = "review_required"


_CATEGORY_ACTIONS: dict[ReplyCategory, ReplyNextAction] = {
    ReplyCategory.INTERESTED: ReplyNextAction.PREPARE_FOLLOWUP,
    ReplyCategory.NOT_INTERESTED: ReplyNextAction.END_FOLLOWUP,
    ReplyCategory.OBJECTION: ReplyNextAction.REVIEW_OBJECTION,
    ReplyCategory.QUESTION: ReplyNextAction.ANSWER_QUESTION,
    ReplyCategory.OUT_OF_OFFICE: ReplyNextAction.WAIT_FOR_RETURN,
    ReplyCategory.WRONG_PERSON: ReplyNextAction.REVIEW_CONTACT,
    ReplyCategory.UNSUBSCRIBE: ReplyNextAction.HONOR_OPT_OUT,
    ReplyCategory.AUTOMATIC_RESPONSE: ReplyNextAction.REVIEW_AUTOMATIC_RESPONSE,
    ReplyCategory.UNKNOWN: ReplyNextAction.MANUAL_REVIEW,
}

# These exact, case-insensitive phrases express an explicit opt-out in the supported languages.
# The guard is deliberately narrow: uncertain intent remains subject to normal review policy.
_UNSUBSCRIBE_MARKERS: dict[ReplyLanguage, tuple[str, ...]] = {
    ReplyLanguage.ENGLISH: ("unsubscribe", "remove me from your list", "do not contact me"),
    ReplyLanguage.PORTUGUESE: (
        "descadastr",
        "remova-me da sua lista",
        "não entre em contato",
    ),
}


@dataclass(frozen=True, slots=True)
class ReplyText:
    """The current reply and its declared supported language."""

    value: str
    language: ReplyLanguage

    def __post_init__(self) -> None:
        if not isinstance(self.language, ReplyLanguage):
            raise PolicyViolationError("reply language must be supported")
        if not self.value or len(self.value) > 8_000:
            raise PolicyViolationError("reply text must be 1-8,000 characters")


@dataclass(frozen=True, slots=True)
class ReplyEvidence:
    """A half-open character range in the current reply text."""

    start_offset: int
    end_offset: int

    def __post_init__(self) -> None:
        if isinstance(self.start_offset, bool) or isinstance(self.end_offset, bool):
            raise PolicyViolationError("reply evidence offsets must be integers")
        if not isinstance(self.start_offset, int) or not isinstance(self.end_offset, int):
            raise PolicyViolationError("reply evidence offsets must be integers")
        if self.start_offset < 0 or self.end_offset <= self.start_offset:
            raise PolicyViolationError("reply evidence offsets must define a non-empty range")

    def is_valid_for(self, reply: ReplyText) -> bool:
        """Whether this range stays within the authorized current reply."""
        return self.end_offset <= len(reply.value)


@dataclass(frozen=True, slots=True)
class ReplyClassification:
    """A structured proposal whose policy outcome is evaluated without I/O."""

    category: ReplyCategory
    confidence: float
    language: ReplyLanguage
    evidence: tuple[ReplyEvidence, ...]
    ambiguous: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.category, ReplyCategory):
            raise PolicyViolationError("reply category must be supported")
        if not isinstance(self.language, ReplyLanguage):
            raise PolicyViolationError("reply classification language must be supported")
        if not isinstance(self.evidence, tuple) or not all(
            isinstance(item, ReplyEvidence) for item in self.evidence
        ):
            raise PolicyViolationError(
                "reply evidence must be an immutable tuple of evidence ranges"
            )
        if not isinstance(self.ambiguous, bool):
            raise PolicyViolationError("reply ambiguity must be boolean")
        if isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float)):
            raise PolicyViolationError("reply confidence must be a finite number within [0, 1]")
        if not isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise PolicyViolationError("reply confidence must be a finite number within [0, 1]")


@dataclass(frozen=True, slots=True)
class ReplyClassificationOutcome:
    """The safe, deterministic result exposed to later layers."""

    category: ReplyCategory
    status: ReplyClassificationStatus
    recommended_action: ReplyNextAction


def mapped_next_action(category: ReplyCategory) -> ReplyNextAction:
    """Return the approved action mapping for a reply category."""
    return _CATEGORY_ACTIONS[category]


def has_explicit_unsubscribe_intent(reply: ReplyText) -> bool:
    """Recognize conservative, explicit English or Portuguese opt-out markers."""
    normalized = reply.value.casefold()
    return any(marker in normalized for marker in _UNSUBSCRIBE_MARKERS[reply.language])


def evaluate_reply_classification(
    reply: ReplyText, classification: ReplyClassification
) -> ReplyClassificationOutcome:
    """Apply review and opt-out precedence to a structured classification proposal."""
    category = (
        ReplyCategory.UNSUBSCRIBE
        if has_explicit_unsubscribe_intent(reply)
        else classification.category
    )
    requires_review = (
        classification.confidence < REPLY_CONFIDENCE_THRESHOLD
        or classification.ambiguous
        or classification.language is not reply.language
        or not classification.evidence
        or not all(evidence.is_valid_for(reply) for evidence in classification.evidence)
    )
    if requires_review:
        return ReplyClassificationOutcome(
            category=category,
            status=ReplyClassificationStatus.REVIEW_REQUIRED,
            recommended_action=ReplyNextAction.MANUAL_REVIEW,
        )
    return ReplyClassificationOutcome(
        category=category,
        status=ReplyClassificationStatus.CLASSIFIED,
        recommended_action=mapped_next_action(category),
    )
