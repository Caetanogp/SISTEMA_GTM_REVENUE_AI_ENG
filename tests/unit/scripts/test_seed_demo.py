from __future__ import annotations

from revops.infrastructure.persistence.demo_seed import DEMO_ORGANIZATION_ID, build_demo_seed


def test_demo_seed_has_expected_synthetic_shape() -> None:
    rows = build_demo_seed()

    assert rows.organization.id == DEMO_ORGANIZATION_ID
    assert rows.organization.demo_mode is True
    assert rows.user.organization_id == rows.organization.id
    assert len(rows.accounts) == 30
    assert len(rows.contacts) == 30
    assert len(rows.opportunities) == 30
    assert len(rows.interactions) == 60
    assert {row.organization_id for row in rows.accounts} == {rows.organization.id}
    assert {row.account_id for row in rows.contacts} == {row.id for row in rows.accounts}


def test_demo_seed_is_stable_and_tenant_scoped() -> None:
    first = build_demo_seed()
    second = build_demo_seed()

    assert [row.id for row in first.accounts] == [row.id for row in second.accounts]
    assert [row.domain for row in first.accounts] == [row.domain for row in second.accounts]
    assert {row.organization_id for row in first.interactions} == {first.organization.id}
    assert all(row.email.endswith(".example.com") for row in first.contacts)
