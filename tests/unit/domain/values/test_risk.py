from revops.domain.values.risk import RiskLevel


def test_ordering() -> None:
    assert RiskLevel.LOW < RiskLevel.MEDIUM < RiskLevel.HIGH


def test_high_is_at_least_medium() -> None:
    assert RiskLevel.HIGH >= RiskLevel.MEDIUM


def test_low_is_not_at_least_medium() -> None:
    assert not (RiskLevel.LOW >= RiskLevel.MEDIUM)
