"""Pure contracts and deterministic text preparation for knowledge ingestion."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import Final
from unicodedata import normalize

from revops.domain.errors import InvalidTransitionError, PolicyViolationError

MAX_CONTENT_BYTES: Final = 1_048_576
MAX_CHUNKS: Final = 500
MAX_CHUNK_CHARACTERS: Final = 3_000
MAX_CHUNK_OVERLAP_CHARACTERS: Final = 300


class KnowledgeCategory(StrEnum):
    ICP = "icp"
    PRODUCT = "product"
    AUTHORIZED_PRICING = "authorized_pricing"
    SALES_PLAYBOOK = "sales_playbook"
    BRAND_VOICE = "brand_voice"
    OBJECTION_HANDLING = "objection_handling"
    OUTREACH_POLICY = "outreach_policy"
    APPROVED_EXAMPLE = "approved_example"


class KnowledgeLanguage(StrEnum):
    ENGLISH = "en"
    PORTUGUESE = "pt"


class KnowledgeFormat(StrEnum):
    TEXT = "text"
    MARKDOWN = "md"


class KnowledgeScope(StrEnum):
    PLATFORM = "platform"
    ORGANIZATION = "organization"


class KnowledgeVersionStatus(StrEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    RETIRED = "retired"


_VERSION_TRANSITIONS: Final[dict[KnowledgeVersionStatus, frozenset[KnowledgeVersionStatus]]] = {
    KnowledgeVersionStatus.DRAFT: frozenset({KnowledgeVersionStatus.CONFIRMED}),
    KnowledgeVersionStatus.CONFIRMED: frozenset({KnowledgeVersionStatus.PROCESSING}),
    KnowledgeVersionStatus.PROCESSING: frozenset(
        {KnowledgeVersionStatus.READY, KnowledgeVersionStatus.FAILED}
    ),
    KnowledgeVersionStatus.READY: frozenset({KnowledgeVersionStatus.RETIRED}),
    KnowledgeVersionStatus.FAILED: frozenset(),
    KnowledgeVersionStatus.RETIRED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    """Validated, normalized submission content before any persistence or I/O."""

    document_key: str
    category: KnowledgeCategory
    language: KnowledgeLanguage
    format: KnowledgeFormat
    scope: KnowledgeScope
    content: str
    metadata: Mapping[str, str | int | float | bool | None]

    def __post_init__(self) -> None:
        if not self.document_key.strip():
            raise PolicyViolationError("knowledge document_key must not be empty")
        if len(self.document_key) > 200:
            raise PolicyViolationError("knowledge document_key must be at most 200 characters")
        if not re.fullmatch(r"[a-z0-9][a-z0-9._/-]*", self.document_key):
            raise PolicyViolationError("knowledge document_key contains unsupported characters")

        normalized_content = normalize_content(self.content)
        if not normalized_content:
            raise PolicyViolationError("knowledge content must not be empty")
        if len(normalized_content.encode("utf-8")) > MAX_CONTENT_BYTES:
            raise PolicyViolationError("knowledge content exceeds the 1 MiB UTF-8 limit")
        object.__setattr__(self, "content", normalized_content)

        if not isinstance(self.metadata, Mapping):
            raise PolicyViolationError("knowledge metadata must be a mapping")
        for key, value in self.metadata.items():
            if not isinstance(key, str) or not key.strip():
                raise PolicyViolationError("knowledge metadata keys must be non-empty strings")
            if not isinstance(value, str | int | float | bool | type(None)):
                raise PolicyViolationError("knowledge metadata values must be scalar JSON values")

    @property
    def content_hash(self) -> str:
        return stable_hash(self.content)


@dataclass(slots=True)
class KnowledgeVersionState:
    """The legal lifecycle transitions for one immutable knowledge version."""

    status: KnowledgeVersionStatus = KnowledgeVersionStatus.DRAFT

    def confirm(self) -> None:
        self._transition_to(KnowledgeVersionStatus.CONFIRMED)

    def begin_processing(self) -> None:
        self._transition_to(KnowledgeVersionStatus.PROCESSING)

    def mark_ready(self) -> None:
        self._transition_to(KnowledgeVersionStatus.READY)

    def mark_failed(self) -> None:
        self._transition_to(KnowledgeVersionStatus.FAILED)

    def retire(self) -> None:
        self._transition_to(KnowledgeVersionStatus.RETIRED)

    def ensure_activatable(self) -> None:
        """Historical activation is permitted only for an already-ready version."""
        if self.status is not KnowledgeVersionStatus.READY:
            raise InvalidTransitionError("only a ready knowledge version can be activated")

    def _transition_to(self, target: KnowledgeVersionStatus) -> None:
        if target not in _VERSION_TRANSITIONS[self.status]:
            raise InvalidTransitionError(
                f"cannot move a knowledge version from {self.status} to {target}"
            )
        self.status = target


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    """A stable, bounded fragment of normalized knowledge content."""

    ordinal: int
    text: str

    @property
    def content_hash(self) -> str:
        return stable_hash(self.text)


def normalize_content(content: str) -> str:
    """Return the canonical Unicode-NFC and newline representation of document content."""
    if not isinstance(content, str):
        raise PolicyViolationError("knowledge content must be text")
    return normalize("NFC", content.replace("\r\n", "\n").replace("\r", "\n")).strip()


def stable_hash(value: str) -> str:
    """Return the lowercase SHA-256 hash of canonical UTF-8 text."""
    return sha256(value.encode("utf-8")).hexdigest()


def chunk_content(content: str) -> tuple[KnowledgeChunk, ...]:
    """Split canonical text at headings/paragraphs while enforcing size and overlap limits."""
    normalized_content = normalize_content(content)
    if not normalized_content:
        raise PolicyViolationError("knowledge content must not be empty")

    chunks: list[str] = []
    current = ""
    for unit in _heading_and_paragraph_units(normalized_content):
        for fragment in _split_oversized_unit(unit):
            current = _append_fragment(chunks, current, fragment)
    if current:
        chunks.append(current)

    if len(chunks) > MAX_CHUNKS:
        raise PolicyViolationError(f"knowledge content exceeds the {MAX_CHUNKS} chunk limit")
    return tuple(KnowledgeChunk(ordinal=index, text=text) for index, text in enumerate(chunks))


def _heading_and_paragraph_units(content: str) -> tuple[str, ...]:
    sections = re.split(r"\n(?=#{1,6}\s)", content)
    units: list[str] = []
    for section in sections:
        units.extend(part.strip() for part in re.split(r"\n{2,}", section) if part.strip())
    return tuple(units)


def _split_oversized_unit(unit: str) -> tuple[str, ...]:
    if len(unit) <= MAX_CHUNK_CHARACTERS:
        return (unit,)

    fragments: list[str] = []
    remaining = unit
    while len(remaining) > MAX_CHUNK_CHARACTERS:
        boundary = max(
            remaining.rfind("\n", 0, MAX_CHUNK_CHARACTERS + 1),
            remaining.rfind(" ", 0, MAX_CHUNK_CHARACTERS + 1),
        )
        if boundary <= 0:
            boundary = MAX_CHUNK_CHARACTERS
        fragments.append(remaining[:boundary].strip())
        remaining = remaining[boundary:].lstrip()
    if remaining:
        fragments.append(remaining)
    return tuple(fragments)


def _append_fragment(chunks: list[str], current: str, fragment: str) -> str:
    separator = "\n\n" if current else ""
    if len(current) + len(separator) + len(fragment) <= MAX_CHUNK_CHARACTERS:
        return f"{current}{separator}{fragment}"

    if current:
        chunks.append(current)
    overlap = current[-MAX_CHUNK_OVERLAP_CHARACTERS:] if current else ""
    if overlap and len(overlap) + 1 + len(fragment) <= MAX_CHUNK_CHARACTERS:
        return f"{overlap}\n{fragment}"
    return fragment
