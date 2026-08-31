"""Deterministic, explainable deduplication policy for SPEC-003."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import dataclass
from uuid import UUID

from revops.domain.entities.account import Account
from revops.domain.entities.contact import Contact

POLICY_VERSION = "dedupe_v1"

_COMPANY_SUFFIXES = {
    "co",
    "company",
    "corp",
    "corporation",
    "eireli",
    "inc",
    "incorporated",
    "limited",
    "llc",
    "ltd",
    "ltda",
    "sa",
}


def _text_key(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join("".join(char if char.isalnum() else " " for char in without_marks).split())


def company_name_key(value: str) -> str:
    """Return a conservative company key with recognized trailing legal suffixes removed."""

    tokens = _text_key(value).split()
    while tokens and tokens[-1] in _COMPANY_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def person_name_key(value: str) -> str:
    return _text_key(value)


@dataclass(frozen=True, slots=True)
class MatchEvidence:
    score: int
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if not 0 <= self.score <= 100:
            raise ValueError("deduplication score must be between 0 and 100")
        if not self.reasons:
            raise ValueError("a match must include at least one reason")


def match_accounts(left: Account, right: Account) -> MatchEvidence | None:
    reasons: list[tuple[str, int]] = []
    if left.domain == right.domain:
        reasons.append(("account_domain_exact", 100))
    if (left_key := company_name_key(left.company_name)) and left_key == company_name_key(
        right.company_name
    ):
        reasons.append(("account_name_exact", 80))
    if not reasons:
        return None
    return MatchEvidence(max(score for _, score in reasons), tuple(reason for reason, _ in reasons))


def match_contacts(
    left: Contact,
    right: Contact,
    *,
    same_canonical_account: bool,
) -> MatchEvidence | None:
    reasons: list[tuple[str, int]] = []
    if left.email == right.email:
        reasons.append(("contact_email_exact", 100))
    if left.phone is not None and left.phone == right.phone:
        reasons.append(("contact_phone_exact", 90))
    if same_canonical_account and (
        (left_key := person_name_key(left.full_name))
        and left_key == person_name_key(right.full_name)
    ):
        reasons.append(("contact_name_account_exact", 75))
    if not reasons:
        return None
    return MatchEvidence(max(score for _, score in reasons), tuple(reason for reason, _ in reasons))


def account_fingerprint(account: Account) -> str:
    return _fingerprint(
        {"company_name": company_name_key(account.company_name), "domain": account.domain.value}
    )


def contact_fingerprint(contact: Contact, *, canonical_account_id: UUID) -> str:
    return _fingerprint(
        {
            "account_id": str(canonical_account_id),
            "email": contact.email.value,
            "full_name": person_name_key(contact.full_name),
            "phone": contact.phone.value if contact.phone is not None else None,
        }
    )


def _fingerprint(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
