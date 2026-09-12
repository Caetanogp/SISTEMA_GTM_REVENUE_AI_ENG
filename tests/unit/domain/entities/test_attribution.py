"""Domain contracts for the CRM attribution foundation."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast
from uuid import uuid4

import pytest
from revops.domain.entities.campaign import Campaign
from revops.domain.entities.opportunity import Opportunity, OpportunityStage, OpportunityStatus
from revops.domain.entities.touchpoint import Touchpoint
from revops.domain.errors import PolicyViolationError

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_campaign_preserves_explicit_provenance_and_timestamps() -> None:
    campaign = Campaign(
        id=uuid4(),
        organization_id=uuid4(),
        name="Q1 launch",
        source="linkedin",
        channel="paid_social",
        metadata={"utm_campaign": "q1-launch"},
        created_at=NOW,
        updated_at=NOW + timedelta(hours=1),
    )

    assert campaign.metadata["utm_campaign"] == "q1-launch"
    assert campaign.updated_at > campaign.created_at


@pytest.mark.parametrize("field_name", ["created_at", "updated_at"])
def test_campaign_rejects_naive_timestamps(field_name: str) -> None:
    created_at = NOW.replace(tzinfo=None) if field_name == "created_at" else NOW
    updated_at = NOW.replace(tzinfo=None) if field_name == "updated_at" else NOW

    with pytest.raises(PolicyViolationError, match=f"{field_name} must be timezone-aware"):
        Campaign(
            id=uuid4(),
            organization_id=uuid4(),
            name="Q1 launch",
            source="linkedin",
            channel="paid_social",
            created_at=created_at,
            updated_at=updated_at,
        )


def test_campaign_rejects_updated_timestamp_before_creation() -> None:
    with pytest.raises(PolicyViolationError, match="updated_at must not be earlier"):
        Campaign(
            id=uuid4(),
            organization_id=uuid4(),
            name="Q1 launch",
            source="linkedin",
            channel="paid_social",
            created_at=NOW,
            updated_at=NOW - timedelta(seconds=1),
        )


def test_touchpoint_allows_optional_contact_and_campaign_relationships() -> None:
    touchpoint = Touchpoint(
        id=uuid4(),
        organization_id=uuid4(),
        account_id=uuid4(),
        contact_id=uuid4(),
        campaign_id=uuid4(),
        type="form_submission",
        metadata={"form_id": "pricing"},
        occurred_at=NOW,
        created_at=NOW,
    )

    assert touchpoint.contact_id is not None
    assert touchpoint.campaign_id is not None
    assert touchpoint.metadata == {"form_id": "pricing"}


@pytest.mark.parametrize("field_name", ["occurred_at", "created_at"])
def test_touchpoint_rejects_naive_timestamps(field_name: str) -> None:
    occurred_at = NOW.replace(tzinfo=None) if field_name == "occurred_at" else NOW
    created_at = NOW.replace(tzinfo=None) if field_name == "created_at" else NOW

    with pytest.raises(PolicyViolationError, match=f"{field_name} must be timezone-aware"):
        Touchpoint(
            id=uuid4(),
            organization_id=uuid4(),
            account_id=uuid4(),
            type="page_view",
            occurred_at=occurred_at,
            created_at=created_at,
        )


@pytest.mark.parametrize("status", list(OpportunityStatus))
def test_opportunity_accepts_only_declared_lifecycle_statuses(status: OpportunityStatus) -> None:
    opportunity = Opportunity(
        id=uuid4(),
        organization_id=uuid4(),
        account_id=uuid4(),
        stage=OpportunityStage.PROSPECTING,
        value=Decimal("1000"),
        status=status,
    )

    assert opportunity.status is status


def test_opportunity_defaults_to_open_status() -> None:
    opportunity = Opportunity(
        id=uuid4(),
        organization_id=uuid4(),
        account_id=uuid4(),
        stage=OpportunityStage.PROSPECTING,
        value=Decimal("1000"),
    )

    assert opportunity.status is OpportunityStatus.OPEN


def test_opportunity_rejects_invalid_lifecycle_status() -> None:
    with pytest.raises(PolicyViolationError, match="status must be an OpportunityStatus"):
        Opportunity(
            id=uuid4(),
            organization_id=uuid4(),
            account_id=uuid4(),
            stage=OpportunityStage.PROSPECTING,
            value=Decimal("1000"),
            status=cast(OpportunityStatus, "closed"),
        )
