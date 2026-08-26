import pytest
from revops.domain.errors import PolicyViolationError
from revops.domain.values.company_domain import CompanyDomain


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("acme.com", "acme.com"),
        ("https://www.acme.com/pricing", "acme.com"),
        ("http://ACME.com:8080", "acme.com"),
        ("www.acme.com", "acme.com"),
        ("acme.com?utm_source=x", "acme.com"),
        ("  acme.com  ", "acme.com"),
    ],
)
def test_normalizes_to_bare_domain(raw: str, expected: str) -> None:
    assert CompanyDomain(raw).value == expected


@pytest.mark.parametrize("raw", ["", "not a domain", "acme", "acme.", "-acme.com", "acme..com"])
def test_rejects_invalid_domains(raw: str) -> None:
    with pytest.raises(PolicyViolationError):
        CompanyDomain(raw)


def test_two_domains_differing_by_scheme_and_www_are_equal() -> None:
    assert CompanyDomain("https://www.acme.com") == CompanyDomain("acme.com")


def test_str_returns_normalized_value() -> None:
    assert str(CompanyDomain("https://www.acme.com")) == "acme.com"
