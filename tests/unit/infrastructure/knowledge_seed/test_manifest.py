"""Contract tests for the reviewed deployment-controlled platform seed."""

from __future__ import annotations

from revops.application.use_cases.knowledge import validate_platform_seed_manifest
from revops.domain.entities.knowledge import KnowledgeScope
from revops.infrastructure.knowledge_seed.manifest import (
    PLATFORM_SEED_MANIFEST,
    SOURCE,
    SOURCE_PDF_SHA256,
)


def test_platform_seed_manifest_is_approved_and_self_validating() -> None:
    validated = validate_platform_seed_manifest(PLATFORM_SEED_MANIFEST)

    assert tuple(item.document_key for item, _ in validated) == (
        "outreach-policy/human-approval",
        "product/platform-overview",
    )
    assert all(item.to_domain().scope is KnowledgeScope.PLATFORM for item, _ in validated)
    assert all(item.to_domain().content_hash == item.content_hash for item, _ in validated)
    assert all(item.revision == 1 for item, _ in validated)
    assert all(item.metadata["source"] == SOURCE for item, _ in validated)
    assert all(item.metadata["source_pdf_sha256"] == SOURCE_PDF_SHA256 for item, _ in validated)
    assert all(item.metadata["approval_status"] == "approved" for item, _ in validated)
    assert all(chunks for _, chunks in validated)
