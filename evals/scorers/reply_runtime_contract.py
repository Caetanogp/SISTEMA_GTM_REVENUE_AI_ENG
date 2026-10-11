"""Offline contract scorer for the fixed reply-intelligence runtime."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError
from revops.application.dto import ReplyClassificationOutput, ReplyEvidenceDTO, ReplyResultDTO
from revops.application.ports import ReplyRecord
from revops.application.use_cases.reply import ClassifiedReply
from revops.domain.values.reply import (
    ReplyCategory,
    ReplyClassificationStatus,
    ReplyLanguage,
    ReplyNextAction,
    ReplyText,
)
from revops.domain.values.risk import RiskLevel
from revops.infrastructure.agent.prompt_loader import load_classify_reply_prompt
from revops.infrastructure.agent.reply_runtime import _ARTIFACT_LIMIT_BYTES, _artifact_json
from revops.infrastructure.agent.tools import ClassifyReplyTool

DATASET_PATH = Path(__file__).resolve().parents[1] / "datasets" / "reply_runtime_contract.jsonl"


@dataclass(frozen=True, slots=True)
class ScoreResult:
    total: int
    correct: int
    failed_ids: list[str]

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0


def _reply(text: str = "Não envie 🙂") -> ReplyRecord:
    return ReplyRecord(
        id=uuid4(),
        organization_id=uuid4(),
        account_id=uuid4(),
        contact_id=None,
        submitted_by=uuid4(),
        reply=ReplyText(text, ReplyLanguage.PORTUGUESE),
        idempotency_key="contract",
        created_at=datetime(2026, 10, 11, tzinfo=UTC),
    )


def _prompt_data_fencing() -> bool:
    text = "Não envie 🙂"
    prompt = load_classify_reply_prompt(_reply(text))
    return text in prompt and "<untrusted_reply>" in prompt and "expected_language=pt" in prompt


def _artifact_bounds() -> bool:
    result = ReplyResultDTO(
        category=ReplyCategory.INTERESTED,
        status=ReplyClassificationStatus.CLASSIFIED,
        recommended_action=ReplyNextAction.PREPARE_FOLLOWUP,
        confidence=0.9,
        language=ReplyLanguage.ENGLISH,
        evidence=(),
        limitations=(),
    )
    from revops.application.dto import LLMUsage

    artifact = _artifact_json(
        ClassifiedReply(
            result,
            LLMUsage(
                provider="offline",
                model="offline",
                model_config_json={},
                input_tokens=0,
                output_tokens=0,
                token_cost_usd=Decimal("0"),
                latency_ms=0,
            ),
        )
    )
    return (
        artifact
        == json.dumps(
            json.loads(artifact), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        and len(artifact.encode("utf-8")) <= _ARTIFACT_LIMIT_BYTES
    )


def _strict_schema() -> bool:
    try:
        ReplyClassificationOutput.model_validate(
            {
                "category": "interested",
                "confidence": 0.9,
                "language": "en",
                "evidence": [ReplyEvidenceDTO(start_offset=0, end_offset=1).model_dump()],
                "unexpected": True,
            }
        )
    except ValidationError:
        return True
    return False


def _low_risk_tool() -> bool:
    fields = ClassifyReplyTool.__dataclass_fields__
    return fields["name"].default == "classify_reply" and fields["risk"].default is RiskLevel.LOW


_CHECKS = {
    "prompt_data_fencing": _prompt_data_fencing,
    "artifact_bounds": _artifact_bounds,
    "strict_schema": _strict_schema,
    "low_risk_tool": _low_risk_tool,
}


def score_reply_runtime_contract_dataset() -> ScoreResult:
    failed_ids: list[str] = []
    cases = [
        json.loads(line) for line in DATASET_PATH.read_text(encoding="utf-8").splitlines() if line
    ]
    for case in cases:
        if not _CHECKS[str(case["contract"])]():
            failed_ids.append(str(case["id"]))
    return ScoreResult(
        total=len(cases), correct=len(cases) - len(failed_ids), failed_ids=failed_ids
    )
