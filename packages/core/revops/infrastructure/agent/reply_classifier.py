"""Bounded adapter for the dedicated reply-intelligence inference boundary."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from revops.application.dto import LLMResult, ReplyClassificationOutput
from revops.application.ports import LLMGateway, ReplyRecord
from revops.infrastructure.agent.prompt_loader import load_classify_reply_prompt

_MODEL_TIMEOUT_SECONDS = 20


@dataclass(frozen=True, slots=True)
class BoundedReplyClassifier:
    """Use the structured gateway once, with a reply-only bounded prompt."""

    gateway: LLMGateway

    async def classify(self, reply: ReplyRecord) -> LLMResult[ReplyClassificationOutput]:
        prompt = load_classify_reply_prompt(reply)
        async with asyncio.timeout(_MODEL_TIMEOUT_SECONDS):
            return await self.gateway.complete(
                prompt=prompt,
                response_model=ReplyClassificationOutput,
            )
