import pytest
from revops.domain.errors import PolicyViolationError
from revops.domain.values.phone import PhoneNumber


def test_phone_strips_outer_whitespace_and_preserves_e164() -> None:
    assert PhoneNumber("  +5511999999999 ").value == "+5511999999999"


@pytest.mark.parametrize("raw", ["", "5511999999999", "+5511999", "+012345678", "+5511 999999999"])
def test_phone_rejects_non_e164_values(raw: str) -> None:
    with pytest.raises(PolicyViolationError):
        PhoneNumber(raw)
