from datetime import UTC, datetime
from uuid import uuid4

import pytest
from revops.domain.errors import PolicyViolationError
from revops.domain.values.outreach import (
    ClaimReference,
    DraftLanguage,
    FollowupArtifact,
    FollowupStatus,
    GeneratedClaim,
    ResearchFact,
    ResearchSource,
    ResearchStatus,
    validate_claim_references,
)


def _source() -> ResearchSource:
    return ResearchSource(
        source_id="company-home",
        url="https://example.test/",
        retrieved_at=datetime.now(UTC),
        content_hash="a" * 64,
        excerpt="The company serves technology teams.",
    )


def test_research_fact_requires_acquired_source() -> None:
    with pytest.raises(PolicyViolationError):
        ResearchFact(key="industry", value="software", source_ids=())


def test_claim_references_cannot_escape_run_sources() -> None:
    claim = GeneratedClaim(
        claim_id="c1",
        text="Supported claim",
        references=(ClaimReference(claim_id="c1", source_ids=("other-run",)),),
    )
    with pytest.raises(PolicyViolationError):
        validate_claim_references((claim,), frozenset({"company-home"}))


def test_complete_followup_requires_bounded_draft() -> None:
    source = _source()
    fact = ResearchFact(key="industry", value="software", source_ids=(source.source_id,))
    assert fact.source_ids == ("company-home",)
    claim = GeneratedClaim(
        claim_id="c1",
        text="Supported claim",
        references=(ClaimReference(claim_id="c1", source_ids=(source.source_id,)),),
    )
    artifact = FollowupArtifact(
        account_id=uuid4(),
        status=FollowupStatus.COMPLETE,
        language=DraftLanguage.ENGLISH,
        subject="A relevant follow-up",
        body="A grounded message.",
        rationale="The evidence supports this context.",
        claims=(claim,),
        source_ids=(source.source_id,),
        limitations=(),
    )
    assert artifact.status is FollowupStatus.COMPLETE


def test_research_status_is_explicit_for_unavailable_sources() -> None:
    assert ResearchStatus.SOURCE_UNAVAILABLE.value == "source_unavailable"
