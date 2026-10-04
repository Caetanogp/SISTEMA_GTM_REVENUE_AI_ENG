"""Assembly of retrieved knowledge as fenced, attributable, untrusted task context."""

from __future__ import annotations

from revops.application.context.builder import estimate_tokens
from revops.application.dto import OmittedKnowledgePassage, TaskKnowledgeContext
from revops.domain.values.retrieval import (
    RetrievalTokenBudget,
    RetrievedPassage,
    order_retrieved_passages,
)


class KnowledgeContextAssembler:
    """Fit ranked passages into a budget without treating source text as instructions."""

    def assemble(
        self,
        passages: tuple[RetrievedPassage, ...],
        *,
        token_budget: RetrievalTokenBudget,
    ) -> TaskKnowledgeContext:
        included: list[RetrievedPassage] = []
        omitted: list[OmittedKnowledgePassage] = []
        sections: list[str] = []
        used_tokens = 0
        budget_exceeded = False

        for passage in order_retrieved_passages(passages):
            section = _fenced_section(passage)
            cost = estimate_tokens(section)
            if budget_exceeded or used_tokens + cost > token_budget.value:
                budget_exceeded = True
                omitted.append(
                    OmittedKnowledgePassage(
                        provenance=passage.provenance,
                        score=passage.score,
                    )
                )
                continue
            sections.append(section)
            included.append(passage)
            used_tokens += cost

        return TaskKnowledgeContext(
            text="\n\n".join(sections),
            token_count=used_tokens,
            included=tuple(included),
            omitted=tuple(omitted),
        )


def _fenced_section(passage: RetrievedPassage) -> str:
    provenance = passage.provenance
    return (
        "[UNTRUSTED_KNOWLEDGE_SOURCE]\n"
        f"document_key: {provenance.document_key}\n"
        f"document_version_id: {provenance.document_version_id}\n"
        f"chunk_id: {provenance.chunk_id}\n"
        f"chunk_ordinal: {provenance.chunk_ordinal}\n"
        f"category: {provenance.category.value}\n"
        f"language: {provenance.language.value}\n"
        f"active_revision_id: {provenance.active_revision_id}\n"
        f"retrieval_score: {passage.score.value}\n"
        "passage:\n"
        f"{passage.text}\n"
        "[/UNTRUSTED_KNOWLEDGE_SOURCE]"
    )
