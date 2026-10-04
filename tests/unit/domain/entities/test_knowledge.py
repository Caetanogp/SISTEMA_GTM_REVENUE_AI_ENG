"""Unit tests for pure knowledge-ingestion domain contracts."""

from typing import cast

import pytest
from revops.domain.entities.knowledge import (
    MAX_CHUNK_CHARACTERS,
    MAX_CHUNKS,
    KnowledgeCategory,
    KnowledgeDocument,
    KnowledgeFormat,
    KnowledgeLanguage,
    KnowledgeScope,
    KnowledgeVersionState,
    KnowledgeVersionStatus,
    chunk_content,
    normalize_content,
)
from revops.domain.errors import InvalidTransitionError, PolicyViolationError


def _document(**overrides: object) -> KnowledgeDocument:
    values: dict[str, object] = {
        "document_key": "sales/playbook.v1",
        "category": KnowledgeCategory.SALES_PLAYBOOK,
        "language": KnowledgeLanguage.ENGLISH,
        "format": KnowledgeFormat.MARKDOWN,
        "scope": KnowledgeScope.ORGANIZATION,
        "content": "# Discovery\n\nAsk one concise question.",
        "metadata": {"source": "admin", "approved": True},
    }
    values.update(overrides)
    return KnowledgeDocument(
        document_key=cast(str, values["document_key"]),
        category=cast(KnowledgeCategory, values["category"]),
        language=cast(KnowledgeLanguage, values["language"]),
        format=cast(KnowledgeFormat, values["format"]),
        scope=cast(KnowledgeScope, values["scope"]),
        content=cast(str, values["content"]),
        metadata=cast(dict[str, str | int | float | bool | None], values["metadata"]),
    )


def test_document_normalizes_content_and_hashes_canonical_utf8() -> None:
    document = _document(content="Cafe\u0301\r\n\r\nValue")

    assert document.content == "Café\n\nValue"
    assert document.content_hash == _document(content="Café\n\nValue").content_hash


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("document_key", "", "document_key"),
        ("document_key", "Invalid Key", "unsupported"),
        ("content", " \n\t ", "content"),
        ("metadata", {"": "source"}, "metadata keys"),
        ("metadata", {"source": ["admin"]}, "metadata values"),
    ],
)
def test_document_rejects_invalid_values(field: str, value: object, message: str) -> None:
    with pytest.raises(PolicyViolationError, match=message):
        _document(**{field: value})


def test_lifecycle_requires_confirmation_and_ready_version_can_be_activated() -> None:
    state = KnowledgeVersionState()

    with pytest.raises(InvalidTransitionError, match="knowledge version"):
        state.begin_processing()

    state.confirm()
    state.begin_processing()
    state.mark_ready()
    state.ensure_activatable()
    state.retire()

    assert state.status is KnowledgeVersionStatus.RETIRED
    with pytest.raises(InvalidTransitionError, match="activated"):
        state.ensure_activatable()


def test_chunking_is_deterministic_heading_aware_and_bounded() -> None:
    content = "# First\n\n" + ("first " * 700) + "\n\n# Second\n\n" + ("second " * 700)

    first = chunk_content(content)
    second = chunk_content(content)

    assert first == second
    assert first[0].text.startswith("# First")
    assert any("# Second" in chunk.text for chunk in first)
    assert all(len(chunk.text) <= MAX_CHUNK_CHARACTERS for chunk in first)
    assert [chunk.ordinal for chunk in first] == list(range(len(first)))
    assert all(chunk.content_hash for chunk in first)


def test_chunking_preserves_a_bounded_overlap_at_chunk_boundaries() -> None:
    first_paragraph = "a" * 2_900
    second_paragraph = "b" * 200

    chunks = chunk_content(f"{first_paragraph}\n\n{second_paragraph}")

    assert len(chunks) == 2
    assert chunks[1].text.startswith(first_paragraph[-300:])
    assert len(chunks[1].text) <= MAX_CHUNK_CHARACTERS


def test_chunking_rejects_more_than_the_maximum_number_of_chunks() -> None:
    content = "\n\n".join("x" * MAX_CHUNK_CHARACTERS for _ in range(MAX_CHUNKS + 1))

    with pytest.raises(PolicyViolationError, match="chunk limit"):
        chunk_content(content)


def test_normalization_uses_nfc_and_deterministic_newlines() -> None:
    assert normalize_content("  A\rB\r\nCafe\u0301  ") == "A\nB\nCafé"
