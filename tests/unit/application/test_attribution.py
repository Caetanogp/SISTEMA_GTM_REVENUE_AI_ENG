"""Application contracts for tenant-scoped CRM attribution."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from revops.application.attribution_validation import AttributionRelationshipValidator
from revops.application.dto import CreateCampaignArgs, CreateTouchpointArgs
from revops.application.ports import (
    CampaignRepository,
    CanonicalRecordGroup,
    ContactRepository,
    TouchpointRepository,
)
from revops.domain.entities.account import Account
from revops.domain.entities.campaign import Campaign
from revops.domain.entities.contact import Contact
from revops.domain.entities.deduplication import DeduplicationRecordType
from revops.domain.entities.interaction import Interaction
from revops.domain.entities.opportunity import Opportunity
from revops.domain.entities.touchpoint import Touchpoint
from revops.domain.errors import PolicyViolationError
from revops.domain.values.company_domain import CompanyDomain
from revops.domain.values.email import EmailAddress


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

    async def list_for_account(
        self, organization_id: UUID, account_ids: Sequence[UUID] | UUID
    ) -> list[Touchpoint]:
        return []


def test_attribution_repositories_are_structural_protocols() -> None:
    assert isinstance(_FakeCampaignRepository(), CampaignRepository)
    assert isinstance(_FakeTouchpointRepository(), TouchpointRepository)


def test_touchpoint_repository_has_no_mutating_history_operations() -> None:
    for forbidden in ("update", "delete", "remove"):
        assert not hasattr(TouchpointRepository, forbidden)


class _FakeAccounts:
    def __init__(self, accounts: dict[UUID, Account]) -> None:
        self.accounts = accounts

    async def get(self, organization_id: UUID, account_id: UUID) -> Account:
        return self.accounts[account_id]

    async def list_for_organization(self, organization_id: UUID) -> list[Account]:
        return []

    async def list_interactions(
        self, organization_id: UUID, account_ids: Sequence[UUID] | UUID
    ) -> Sequence[Interaction]:
        return []

    async def list_open_opportunities(
        self, organization_id: UUID, account_ids: Sequence[UUID] | UUID
    ) -> Sequence[Opportunity]:
        return []


class _FakeContacts:
    def __init__(self, contacts: dict[UUID, Contact]) -> None:
        self.contacts = contacts

    async def get(self, organization_id: UUID, contact_id: UUID) -> Contact | None:
        return self.contacts.get(contact_id)


class _FakeCampaigns:
    def __init__(self, campaigns: dict[UUID, Campaign]) -> None:
        self.campaigns = campaigns

    async def add(self, campaign: Campaign) -> None: ...

    async def get(self, organization_id: UUID, campaign_id: UUID) -> Campaign | None:
        return self.campaigns.get(campaign_id)

    async def list_for_organization(self, organization_id: UUID) -> list[Campaign]:
        return []


class _FakeCanonicalResolver:
    def __init__(
        self, groups: dict[tuple[DeduplicationRecordType, UUID], CanonicalRecordGroup]
    ) -> None:
        self.groups = groups
        self.reads: list[tuple[UUID, DeduplicationRecordType, UUID]] = []
        self.writes: list[tuple[UUID, DeduplicationRecordType, UUID]] = []

    async def resolve(
        self, organization_id: UUID, record_type: DeduplicationRecordType, record_id: UUID
    ) -> CanonicalRecordGroup | None:
        self.reads.append((organization_id, record_type, record_id))
        return self.groups.get((record_type, record_id))

    async def resolve_for_write(
        self, organization_id: UUID, record_type: DeduplicationRecordType, record_id: UUID
    ) -> CanonicalRecordGroup | None:
        self.writes.append((organization_id, record_type, record_id))
        return self.groups.get((record_type, record_id))

    async def fingerprint_for_write(
        self, organization_id: UUID, record_type: DeduplicationRecordType, record_id: UUID
    ) -> str | None:
        return None


def _relationship_validator(
    *, campaign_organization_id: UUID | None = None, contact_account_id: UUID | None = None
) -> tuple[
    AttributionRelationshipValidator,
    UUID,
    UUID,
    UUID,
    UUID,
    UUID,
    _FakeCanonicalResolver,
]:
    organization_id, account_id, account_alias_id, contact_id, campaign_id = (
        uuid4() for _ in range(5)
    )
    account = Account(
        id=account_id,
        organization_id=organization_id,
        company_name="Acme",
        domain=CompanyDomain("acme.test"),
        created_at=datetime(2026, 9, 12, tzinfo=UTC),
    )
    contact = Contact(
        id=contact_id,
        organization_id=organization_id,
        account_id=contact_account_id or account_alias_id,
        email=EmailAddress("buyer@acme.test"),
        full_name="Buyer",
    )
    campaign = Campaign(
        id=campaign_id,
        organization_id=campaign_organization_id or organization_id,
        name="September webinar",
        source="paid-search",
        channel="search",
        created_at=datetime(2026, 9, 12, tzinfo=UTC),
        updated_at=datetime(2026, 9, 12, tzinfo=UTC),
    )
    groups = {
        (DeduplicationRecordType.ACCOUNT, account_id): CanonicalRecordGroup(
            account_id, (account_id, account_alias_id)
        ),
        (DeduplicationRecordType.ACCOUNT, account_alias_id): CanonicalRecordGroup(
            account_id, (account_id, account_alias_id)
        ),
        (DeduplicationRecordType.CONTACT, contact_id): CanonicalRecordGroup(
            contact_id, (contact_id,)
        ),
    }
    if contact_account_id is not None:
        groups[(DeduplicationRecordType.ACCOUNT, contact_account_id)] = CanonicalRecordGroup(
            contact_account_id, (contact_account_id,)
        )
    resolver = _FakeCanonicalResolver(groups)
    return (
        AttributionRelationshipValidator(
            accounts=_FakeAccounts({account_id: account}),
            contacts=_FakeContacts({contact_id: contact}),
            campaigns=_FakeCampaigns({campaign_id: campaign}),
            canonical=resolver,
        ),
        organization_id,
        account_id,
        account_alias_id,
        contact_id,
        campaign_id,
        resolver,
    )


async def test_relationship_validation_canonicalizes_aliases_before_a_touchpoint_write() -> None:
    validator, organization_id, account_id, account_alias_id, contact_id, campaign_id, resolver = (
        _relationship_validator()
    )

    relationships = await validator.resolve_touchpoint_for_write(
        organization_id,
        account_id=account_alias_id,
        contact_id=contact_id,
        campaign_id=campaign_id,
    )

    assert relationships.account_id == account_id
    assert relationships.contact_id == contact_id
    assert relationships.campaign_id == campaign_id
    assert resolver.writes == [
        (organization_id, DeduplicationRecordType.ACCOUNT, account_alias_id),
        (organization_id, DeduplicationRecordType.CONTACT, contact_id),
        (organization_id, DeduplicationRecordType.ACCOUNT, account_alias_id),
    ]


async def test_relationship_validation_rejects_cross_tenant_relationship_records() -> None:
    validator, organization_id, account_id, _, _, campaign_id, _ = _relationship_validator(
        campaign_organization_id=uuid4()
    )

    with pytest.raises(PolicyViolationError, match="campaign is unavailable"):
        await validator.resolve_touchpoint_for_write(
            organization_id,
            account_id=account_id,
            contact_id=None,
            campaign_id=campaign_id,
        )


async def test_relationship_validation_rejects_a_contact_owned_by_another_account() -> None:
    validator, organization_id, account_id, _, contact_id, campaign_id, _ = _relationship_validator(
        contact_account_id=uuid4()
    )

    with pytest.raises(PolicyViolationError, match="contact does not belong"):
        await validator.resolve_touchpoint_for_write(
            organization_id,
            account_id=account_id,
            contact_id=contact_id,
            campaign_id=campaign_id,
        )


async def test_alias_safe_reads_return_all_canonical_account_members() -> None:
    validator, organization_id, account_id, account_alias_id, _, _, resolver = (
        _relationship_validator()
    )

    group = await validator.resolve_account_for_read(organization_id, account_alias_id)

    assert group == CanonicalRecordGroup(account_id, (account_id, account_alias_id))
    assert resolver.reads == [(organization_id, DeduplicationRecordType.ACCOUNT, account_alias_id)]


def test_contact_repository_is_a_structural_protocol() -> None:
    assert isinstance(_FakeContacts({}), ContactRepository)
