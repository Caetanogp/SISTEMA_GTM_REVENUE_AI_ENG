"""Application contracts for tenant-scoped CRM attribution."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from revops.application.dto import CreateCampaignArgs, CreateTouchpointArgs
from revops.application.ports import CampaignRepository, TouchpointRepository
from revops.domain.entities.campaign import Campaign
from revops.domain.entities.touchpoint import Touchpoint


def _campaign_args(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "name": "September webinar",
        "source": "paid-search",
        "channel": "search",
        "metadata": {"utm_campaign": "september-webinar"},
    }
    return {**defaults, **overrides}


def _touchpoint_args(**overrides: object) -> dict[str, object]:
    defaults: dict[str, object] = {
        "account_id": uuid4(),
        "type": "form_submission",
        "occurred_at": datetime(2026, 9, 12, tzinfo=UTC),
        "metadata": {"form": "demo-request"},
    }
    return {**defaults, **overrides}


def test_campaign_args_accept_json_metadata_and_reject_unknown_fields() -> None:
    args = CreateCampaignArgs(**_campaign_args())

    assert args.metadata == {"utm_campaign": "september-webinar"}
    with pytest.raises(ValidationError):
        CreateCampaignArgs(**_campaign_args(unexpected=True))


def test_campaign_args_has_no_organization_id_field() -> None:
    """The authenticated application boundary injects tenant ownership."""
    assert "organization_id" not in CreateCampaignArgs.model_fields


def test_touchpoint_args_require_an_aware_timestamp_and_json_metadata() -> None:
    args = CreateTouchpointArgs(**_touchpoint_args())

    assert args.occurred_at.tzinfo is UTC
    with pytest.raises(ValidationError, match="timezone-aware"):
        CreateTouchpointArgs(
            **_touchpoint_args(occurred_at=datetime(2026, 9, 12, tzinfo=UTC).replace(tzinfo=None))
        )
    with pytest.raises(ValidationError):
        CreateTouchpointArgs(**_touchpoint_args(metadata={"invalid": uuid4()}))


class _FakeCampaignRepository:
    async def add(self, campaign: Campaign) -> None: ...

    async def get(self, organization_id: UUID, campaign_id: UUID) -> Campaign | None:
        return None

    async def list_for_organization(self, organization_id: UUID) -> list[Campaign]:
        return []


class _FakeTouchpointRepository:
    async def add(self, touchpoint: Touchpoint) -> None: ...

    async def get(self, organization_id: UUID, touchpoint_id: UUID) -> Touchpoint | None:
        return None

    async def list_for_account(self, organization_id: UUID, account_id: UUID) -> list[Touchpoint]:
        return []


def test_attribution_repositories_are_structural_protocols() -> None:
    assert isinstance(_FakeCampaignRepository(), CampaignRepository)
    assert isinstance(_FakeTouchpointRepository(), TouchpointRepository)


def test_touchpoint_repository_has_no_mutating_history_operations() -> None:
    for forbidden in ("update", "delete", "remove"):
        assert not hasattr(TouchpointRepository, forbidden)
