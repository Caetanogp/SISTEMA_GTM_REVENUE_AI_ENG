"""Tenant-safe relationship and canonical-identity validation for CRM attribution."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from revops.application.ports import (
    AccountRepository,
    CampaignRepository,
    CanonicalRecordGroup,
    CanonicalResolver,
    ContactRepository,
)
from revops.domain.entities.deduplication import DeduplicationRecordType
from revops.domain.errors import PolicyViolationError


@dataclass(frozen=True, slots=True)
class ResolvedTouchpointRelationships:
    """Canonical relationship identifiers safe to persist for a new touchpoint."""

    account_id: UUID
    contact_id: UUID | None
    campaign_id: UUID | None


@dataclass(frozen=True, slots=True)
class AttributionRelationshipValidator:
    """Resolve aliases and reject unavailable or cross-tenant attribution relationships."""

    accounts: AccountRepository
    contacts: ContactRepository
    campaigns: CampaignRepository
    canonical: CanonicalResolver

    async def resolve_account_for_read(
        self, organization_id: UUID, account_id: UUID
    ) -> CanonicalRecordGroup:
        """Return every current alias member so historical account events remain visible."""
        return await self._resolve(
            organization_id, DeduplicationRecordType.ACCOUNT, account_id, for_write=False
        )

    async def resolve_touchpoint_for_write(
        self,
        organization_id: UUID,
        *,
        account_id: UUID,
        contact_id: UUID | None,
        campaign_id: UUID | None,
    ) -> ResolvedTouchpointRelationships:
        """Resolve new relationship IDs under locks before an adapter starts its write."""
        account_group = await self._resolve(
            organization_id, DeduplicationRecordType.ACCOUNT, account_id, for_write=True
        )
        account = await self.accounts.get(organization_id, account_group.canonical_id)
        if account.organization_id != organization_id:
            raise PolicyViolationError("account is unavailable")

        canonical_contact_id: UUID | None = None
        if contact_id is not None:
            contact_group = await self._resolve(
                organization_id, DeduplicationRecordType.CONTACT, contact_id, for_write=True
            )
            contact = await self.contacts.get(organization_id, contact_group.canonical_id)
            if contact is None or contact.organization_id != organization_id:
                raise PolicyViolationError("contact is unavailable")
            contact_account_group = await self._resolve(
                organization_id,
                DeduplicationRecordType.ACCOUNT,
                contact.account_id,
                for_write=True,
            )
            if contact_account_group.canonical_id != account_group.canonical_id:
                raise PolicyViolationError("contact does not belong to the touchpoint account")
            canonical_contact_id = contact_group.canonical_id

        if campaign_id is not None:
            campaign = await self.campaigns.get(organization_id, campaign_id)
            if campaign is None or campaign.organization_id != organization_id:
                raise PolicyViolationError("campaign is unavailable")

        return ResolvedTouchpointRelationships(
            account_id=account_group.canonical_id,
            contact_id=canonical_contact_id,
            campaign_id=campaign_id,
        )

    async def _resolve(
        self,
        organization_id: UUID,
        record_type: DeduplicationRecordType,
        record_id: UUID,
        *,
        for_write: bool,
    ) -> CanonicalRecordGroup:
        resolve = self.canonical.resolve_for_write if for_write else self.canonical.resolve
        group = await resolve(organization_id, record_type, record_id)
        if group is None:
            raise PolicyViolationError(f"{record_type.value} is unavailable")
        return group
