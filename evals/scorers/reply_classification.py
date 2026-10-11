"""Independent deterministic baseline for the synthetic reply-classification dataset.

This deliberately does not call the production reply policy.  It is a transparent lexical
baseline that makes the labelled dataset and its quality floors reproducible without an LLM.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from revops.domain.values.reply import ReplyCategory

DATASET_PATH = Path(__file__).resolve().parents[1] / "datasets" / "reply_classification.jsonl"

_MARKERS: tuple[tuple[ReplyCategory, tuple[str, ...]], ...] = (
    (
        ReplyCategory.UNSUBSCRIBE,
        (
            "unsubscribe",
            "remove me",
            "do not contact",
            "opt out",
            "mailing list",
            "descadastr",
            "remova-me",
            "não entre em contato",
            "cancelar inscrição",
            "lista de emails",
        ),
    ),
    (
        ReplyCategory.OUT_OF_OFFICE,
        (
            "out of office",
            "away until",
            "on vacation",
            "back on",
            "returning on",
            "fora do escritório",
            "estou de férias",
            "retorno em",
            "ausente até",
            "volto em",
        ),
    ),
    (
        ReplyCategory.AUTOMATIC_RESPONSE,
        (
            "automatic reply",
            "automated message",
            "auto-reply",
            "delivery notification",
            "generated automatically",
            "resposta automática",
            "mensagem automática",
            "aviso automático",
            "gerada automaticamente",
            "email automático",
        ),
    ),
    (
        ReplyCategory.WRONG_PERSON,
        (
            "wrong person",
            "not responsible",
            "contact someone else",
            "not the right person",
            "you have reached",
            "pessoa errada",
            "não sou responsável",
            "fale com",
            "contato correto",
            "não é comigo",
        ),
    ),
    (
        ReplyCategory.NOT_INTERESTED,
        (
            "not interested",
            "no interest",
            "stop pitching",
            "not a fit",
            "decline",
            "não tenho interesse",
            "sem interesse",
            "não é adequado",
            "não quero",
            "recuso",
        ),
    ),
    (
        ReplyCategory.OBJECTION,
        (
            "too expensive",
            "budget",
            "concern",
            "security concern",
            "contract terms",
            "muito caro",
            "orçamento",
            "preocupação",
            "segurança",
            "termos do contrato",
        ),
    ),
    (
        ReplyCategory.QUESTION,
        ("?", "could you", "what is", "how does", "can you", "como", "qual", "vocês", "pode"),
    ),
    (
        ReplyCategory.INTERESTED,
        (
            "interested",
            "would like",
            "schedule",
            "let's talk",
            "send a proposal",
            "interessado",
            "gostaria",
            "agendar",
            "vamos conversar",
            "envie uma proposta",
        ),
    ),
)

_INTERESTED_MARKERS = (
    "interested",
    "would like",
    "schedule",
    "let's talk",
    "send a proposal",
    "interessado",
    "gostaria",
    "agendar",
    "vamos conversar",
    "envie uma proposta",
)

_PORTUGUESE_MARKERS: tuple[tuple[ReplyCategory, tuple[str, ...]], ...] = (
    (ReplyCategory.NOT_INTERESTED, ("n\u00e3o \u00e9 adequada",)),
    (ReplyCategory.OBJECTION, ("muito cara", "seguran\u00e7a")),
)

_NOT_INTERESTED_MARKERS = ("not interested", "no interest", "stop pitching", "not a fit", "decline")


@dataclass(frozen=True, slots=True)
class ClassificationScoreResult:
    total: int
    correct: int
    failed_ids: list[str]
    macro_f1: float
    unsubscribe_recall: float

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0


def load_cases() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in DATASET_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def predict_category(text: str) -> ReplyCategory:
    """Return the first explicit category marker, or unknown if none applies."""
    lowered = text.casefold()
    unsubscribe_markers = _MARKERS[0][1]
    if any(marker in lowered for marker in unsubscribe_markers):
        return ReplyCategory.UNSUBSCRIBE
    if any(marker in lowered for marker in _NOT_INTERESTED_MARKERS):
        return ReplyCategory.NOT_INTERESTED
    if any(marker in lowered for marker in _INTERESTED_MARKERS):
        return ReplyCategory.INTERESTED
    for category, markers in _PORTUGUESE_MARKERS:
        if any(marker in lowered for marker in markers):
            return category
    for category, markers in _MARKERS:
        if any(marker in lowered for marker in markers):
            return category
    return ReplyCategory.UNKNOWN


def _macro_f1(cases: list[dict[str, Any]]) -> float:
    categories = tuple(ReplyCategory)
    scores: list[float] = []
    for category in categories:
        true_positive = sum(
            predict_category(str(case["input"])) is category
            and ReplyCategory(str(case["expected"])) is category
            for case in cases
        )
        false_positive = sum(
            predict_category(str(case["input"])) is category
            and ReplyCategory(str(case["expected"])) is not category
            for case in cases
        )
        false_negative = sum(
            predict_category(str(case["input"])) is not category
            and ReplyCategory(str(case["expected"])) is category
            for case in cases
        )
        denominator = (2 * true_positive) + false_positive + false_negative
        scores.append((2 * true_positive / denominator) if denominator else 0.0)
    return sum(scores) / len(scores) if scores else 0.0


def _unsubscribe_recall(cases: list[dict[str, Any]]) -> float:
    unsubscribe_cases = [
        case for case in cases if ReplyCategory(str(case["expected"])) is ReplyCategory.UNSUBSCRIBE
    ]
    if not unsubscribe_cases:
        return 0.0
    correct = sum(
        predict_category(str(case["input"])) is ReplyCategory.UNSUBSCRIBE
        for case in unsubscribe_cases
    )
    return correct / len(unsubscribe_cases)


def score_reply_classification_dataset() -> ClassificationScoreResult:
    cases = load_cases()
    failed_ids = [
        str(case["id"])
        for case in cases
        if predict_category(str(case["input"])) is not ReplyCategory(str(case["expected"]))
    ]
    return ClassificationScoreResult(
        total=len(cases),
        correct=len(cases) - len(failed_ids),
        failed_ids=failed_ids,
        macro_f1=_macro_f1(cases),
        unsubscribe_recall=_unsubscribe_recall(cases),
    )
