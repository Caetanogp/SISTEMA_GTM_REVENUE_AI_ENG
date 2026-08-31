"""Adversarial cases for untrusted ingestion transport data."""

from __future__ import annotations

import pytest
from revops.infrastructure.ingestion import IngestionTransportError, parse_csv_records


def test_csv_rejects_unknown_headers_before_staging() -> None:
    with pytest.raises(IngestionTransportError, match="csv_headers_invalid"):
        parse_csv_records(b"company_name,domain,ignore_me\nAcme,acme.example,payload")


def test_csv_rejects_malformed_rows_before_staging() -> None:
    with pytest.raises(IngestionTransportError, match="csv_malformed"):
        parse_csv_records(b'company_name,domain\n"Acme,acme.example\n')


def test_csv_keeps_formula_like_values_as_untrusted_data() -> None:
    records = parse_csv_records(b"company_name,domain\n=IMPORTXML(A1),safe.example\n")
    assert records[0].company_name == "=IMPORTXML(A1)"
