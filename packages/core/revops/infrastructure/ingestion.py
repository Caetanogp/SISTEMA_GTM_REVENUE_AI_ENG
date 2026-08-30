"""Strict CSV transport parsing and deterministic synthetic account enrichment."""

from __future__ import annotations

import csv
import hashlib
import io
from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict

from revops.application.dto import IngestionRecordInput

_MAX_BODY_BYTES = 5 * 1024 * 1024
_MAX_ROWS = 1_000
_HEADERS = frozenset({"company_name", "domain", "email", "full_name", "title"})
_REQUIRED_HEADERS = frozenset({"company_name", "domain"})


class IngestionTransportError(ValueError):
    """A batch-level unsafe transport shape; callers must not stage it."""


class SyntheticEnrichmentProfile(BaseModel):
    """The versioned, strictly shaped profile persisted by the synthetic provider."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    schema_version: str
    industry: str
    employee_band: str
    country: str
    summary: str


def parse_csv_records(body: bytes) -> list[IngestionRecordInput]:
    """Parse a bounded UTF-8 CSV envelope without accepting unknown structure."""
    if not body or len(body) > _MAX_BODY_BYTES:
        raise IngestionTransportError("csv_body_size_invalid")
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise IngestionTransportError("csv_encoding_invalid") from exc
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        headers = reader.fieldnames
        if headers is None or len(headers) != len(set(headers)):
            raise IngestionTransportError("csv_headers_invalid")
        header_set = frozenset(headers)
        if not _REQUIRED_HEADERS.issubset(header_set) or not header_set.issubset(_HEADERS):
            raise IngestionTransportError("csv_headers_invalid")
        records = []
        for row in reader:
            if None in row:
                raise IngestionTransportError("csv_row_shape_invalid")
            records.append(IngestionRecordInput.model_validate(row))
            if len(records) > _MAX_ROWS:
                raise IngestionTransportError("csv_row_count_invalid")
    except csv.Error as exc:
        raise IngestionTransportError("csv_malformed") from exc
    if not records:
        raise IngestionTransportError("csv_row_count_invalid")
    return records


class SyntheticEnrichmentGateway:
    """A reproducible low-risk adapter; it never calls an external provider."""

    provider = "synthetic_v1"
    schema_version = "v1"
    _INDUSTRIES = ("software", "healthcare", "manufacturing", "financial_services")
    _EMPLOYEE_BANDS = ("1-50", "51-200", "201-1,000", "1,001+")
    _COUNTRIES = ("Brazil", "Canada", "Germany", "United States")

    async def enrich(self, *, domain: str) -> Mapping[str, object]:
        digest = hashlib.sha256(domain.encode("utf-8")).digest()
        profile = SyntheticEnrichmentProfile(
            provider=self.provider,
            schema_version=self.schema_version,
            industry=self._INDUSTRIES[digest[0] % len(self._INDUSTRIES)],
            employee_band=self._EMPLOYEE_BANDS[digest[1] % len(self._EMPLOYEE_BANDS)],
            country=self._COUNTRIES[digest[2] % len(self._COUNTRIES)],
            summary=f"Synthetic enrichment profile for {domain}.",
        )
        return profile.model_dump()
