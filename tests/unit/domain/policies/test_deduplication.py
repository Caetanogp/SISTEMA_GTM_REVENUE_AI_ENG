from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from revops.domain.entities.account import Account
from revops.domain.entities.contact import Contact
from revops.domain.entities.deduplication import (
    DeduplicationCandidate,
    DeduplicationCandidateStatus,
    DeduplicationRecordType,
    DeduplicationScanState,
    DeduplicationScanStatus,
    RecordAlias,
)
from revops.domain.errors import InvalidTransitionError, PolicyViolationError
from revops.domain.policies.deduplication import (
    POLICY_VERSION,
    account_fingerprint,
    company_name_key,
    contact_fingerprint,
    match_accounts,
    match_contacts,
    person_name_key,
)
from revops.domain.values.company_domain import CompanyDomain
from revops.domain.values.email import EmailAddress
from revops.domain.values.phone import PhoneNumber

ORG = UUID("00000000-0000-0000-0000-000000000001")
ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000010")
OTHER_ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000011")
CONTACT_ID = UUID("00000000-0000-0000-0000-000000000020")
OTHER_CONTACT_ID = UUID("00000000-0000-0000-0000-000000000021")
EVENT_ID = UUID("00000000-0000-0000-0000-000000000030")


def _account(account_id: UUID, name: str, domain: str) -> Account:
    return Account(account_id, ORG, name, CompanyDomain(domain), datetime(2026, 1, 1, tzinfo=UTC))


def _contact(contact_id: UUID, account_id: UUID, name: str, email: str, phone: str) -> Contact:
    return Contact(
        id=contact_id,
        organization_id=ORG,
        account_id=account_id,
        email=EmailAddress(email),
        full_name=name,
        phone=PhoneNumber(phone),
    )


def test_text_keys_remove_accents_punctuation_and_company_suffix() -> None:
    assert company_name_key(" Acmé, Ltd. ") == "acme"
    assert person_name_key("João D'Ávila") == "joao d avila"


def test_account_matching_is_exact_and_explainable() -> None:
    left = _account(ACCOUNT_ID, "Acme Ltd", "acme.com")
    right = _account(OTHER_ACCOUNT_ID, "ACME", "other.example")

    evidence = match_accounts(left, right)

    assert evidence is not None
    assert evidence.score == 80
    assert evidence.reasons == ("account_name_exact",)


def test_contact_matching_uses_phone_or_name_inside_same_account() -> None:
    left = _contact(CONTACT_ID, ACCOUNT_ID, "Jane Doe", "jane@example.com", "+5511999999999")
    right = _contact(
        OTHER_CONTACT_ID, OTHER_ACCOUNT_ID, "Jane Doe", "other@example.com", "+5511888888888"
    )

    assert match_contacts(left, right, same_canonical_account=False) is None
    evidence = match_contacts(left, right, same_canonical_account=True)
    assert evidence is not None
    assert evidence.score == 75
    assert evidence.reasons == ("contact_name_account_exact",)


def test_fingerprints_are_stable_and_include_canonical_account() -> None:
    account = _account(ACCOUNT_ID, "Acme Ltd", "acme.com")
    contact = _contact(CONTACT_ID, ACCOUNT_ID, "Jane Doe", "jane@example.com", "+5511999999999")

    assert account_fingerprint(account) == account_fingerprint(
        _account(ACCOUNT_ID, "ACME", "acme.com")
    )
    assert contact_fingerprint(contact, canonical_account_id=ACCOUNT_ID) != contact_fingerprint(
        contact, canonical_account_id=OTHER_ACCOUNT_ID
    )


def test_scan_state_supports_broker_retry_but_not_terminal_reentry() -> None:
    scan = DeduplicationScanState()
    scan.record_queue_failure()
    scan.retry_queue()
    scan.begin_processing()
    scan.complete()

    assert scan.status is DeduplicationScanStatus.COMPLETED
    with pytest.raises(InvalidTransitionError):
        scan.begin_processing()


def test_candidate_requires_ordered_ids_and_has_one_way_decision() -> None:
    candidate = DeduplicationCandidate(
        record_type=DeduplicationRecordType.ACCOUNT,
        left_id=ACCOUNT_ID,
        right_id=OTHER_ACCOUNT_ID,
        score=80,
        reasons=("account_name_exact",),
        policy_version=POLICY_VERSION,
        left_fingerprint="a" * 64,
        right_fingerprint="b" * 64,
    )

    candidate.dismiss()
    assert candidate.status is DeduplicationCandidateStatus.DISMISSED
    with pytest.raises(InvalidTransitionError):
        candidate.mark_merged()
    with pytest.raises(PolicyViolationError):
        DeduplicationCandidate(
            record_type=DeduplicationRecordType.ACCOUNT,
            left_id=OTHER_ACCOUNT_ID,
            right_id=ACCOUNT_ID,
            score=80,
            reasons=("account_name_exact",),
            policy_version=POLICY_VERSION,
            left_fingerprint="a" * 64,
            right_fingerprint="b" * 64,
        )


def test_alias_is_reversible_once() -> None:
    alias = RecordAlias(
        organization_id=uuid4(),
        record_type=DeduplicationRecordType.ACCOUNT,
        alias_id=ACCOUNT_ID,
        canonical_id=OTHER_ACCOUNT_ID,
        merge_event_id=EVENT_ID,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    alias.revert(occurred_at=datetime(2026, 1, 2, tzinfo=UTC))

    assert not alias.is_active
    with pytest.raises(InvalidTransitionError):
        alias.revert(occurred_at=datetime(2026, 1, 3, tzinfo=UTC))
