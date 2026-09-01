from __future__ import annotations

import asyncio

import pytest
from revops.infrastructure.ingestion import (
    IngestionTransportError,
    SyntheticEnrichmentGateway,
    parse_csv_records,
)


def test_parse_csv_records_accepts_bom_and_optional_contact_fields() -> None:
    rows = parse_csv_records(
        b"\xef\xbb\xbfcompany_name,domain,email,full_name,title\r\nAcme,acme.test,ada@acme.test,Ada,CTO\r\n"
    )
    assert rows[0].company_name == "Acme"
    assert rows[0].email == "ada@acme.test"


def test_parse_csv_records_accepts_optional_phone() -> None:
    rows = parse_csv_records(
        b"company_name,domain,email,full_name,phone\r\nAcme,acme.test,ada@acme.test,Ada,+5511999999999\r\n"
    )
    assert rows[0].phone == "+5511999999999"


@pytest.mark.parametrize(
    "body",
    [
        b"company_name,domain,unknown\nAcme,acme.test,x\n",
        b"company_name,company_name\nAcme,acme.test\n",
        b"company_name,domain\n",
    ],
)
def test_parse_csv_records_rejects_unsafe_envelopes(body: bytes) -> None:
    with pytest.raises(IngestionTransportError):
        parse_csv_records(body)


def test_synthetic_enrichment_is_deterministic_and_versioned() -> None:
    gateway = SyntheticEnrichmentGateway()
    first = asyncio.run(gateway.enrich(domain="acme.test"))
    assert first == asyncio.run(gateway.enrich(domain="acme.test"))
    assert first.provider == "synthetic_v1"
    assert first.schema_version == "v1"
