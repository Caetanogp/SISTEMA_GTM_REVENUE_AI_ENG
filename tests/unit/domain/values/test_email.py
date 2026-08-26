import pytest
from revops.domain.errors import PolicyViolationError
from revops.domain.values.email import EmailAddress


def test_normalizes_case_and_whitespace() -> None:
    assert EmailAddress("  Jane.Doe@Example.COM ").value == "jane.doe@example.com"


def test_str_returns_normalized_value() -> None:
    assert str(EmailAddress("A@B.com")) == "a@b.com"


@pytest.mark.parametrize(
    "raw",
    ["", "not-an-email", "missing-domain@", "@missing-local.com", "no-at-sign.com", "a@b"],
)
def test_rejects_invalid_addresses(raw: str) -> None:
    with pytest.raises(PolicyViolationError):
        EmailAddress(raw)


def test_two_addresses_differing_only_by_case_are_equal() -> None:
    assert EmailAddress("Jane@Acme.com") == EmailAddress("jane@acme.com")
