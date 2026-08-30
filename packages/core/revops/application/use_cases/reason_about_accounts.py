"""Structured LLM reasoning over trusted deterministic account candidates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pydantic import ValidationError

from revops.application.dto import (
    AccountCandidate,
    LLMResult,
    PrioritizationOutput,
)
from revops.application.ports import LLMGateway
from revops.domain.errors import PolicyViolationError
from revops.domain.policies.task import validate_due_at

_MAX_ATTEMPTS = 3


class StructuredOutputError(ValueError):
    """The model exhausted the bounded structured-output retry budget."""


@dataclass(frozen=True, slots=True)
class ReasonAboutAccounts:
    gateway: LLMGateway

    async def execute(
        self,
        *,
        prompt: str,
        candidates: list[AccountCandidate],
        now: datetime,
    ) -> LLMResult[PrioritizationOutput]:
        current_prompt = prompt
        last_error: Exception | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                result = await self.gateway.complete(
                    prompt=current_prompt, response_model=PrioritizationOutput
                )
                self._validate_against_candidates(result.output, candidates, now)
                return result
            except (ValidationError, PolicyViolationError, ValueError) as exc:
                last_error = exc
                current_prompt = (
                    f"{prompt}\n\nPrevious structured output was invalid (attempt {attempt + 1}). "
                    "Return a complete value matching the schema and trusted candidate data."
                )
        raise StructuredOutputError("LLM structured output failed after 3 attempts") from last_error

    @staticmethod
    def _validate_against_candidates(
        output: PrioritizationOutput, candidates: list[AccountCandidate], now: datetime
    ) -> None:
        trusted = {candidate.account_id: candidate for candidate in candidates}
        if {account.account_id for account in output.accounts} != set(trusted):
            raise PolicyViolationError("ranked accounts must match the trusted candidate set")
        for account in output.accounts:
            candidate = trusted[account.account_id]
            if (
                account.score != candidate.score
                or account.tier != candidate.tier
                or account.evidence != candidate.evidence
            ):
                raise PolicyViolationError("LLM changed deterministic prioritization fields")
        if output.task.account_id not in trusted:
            raise PolicyViolationError("task account is not in the trusted candidate set")
        validate_due_at(output.task.due_at, now)
