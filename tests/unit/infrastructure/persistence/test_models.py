"""Structural checks on the SQLAlchemy models — no database needed.

Verifies the ten tables SPEC-001 tasks.md section 3 requires exist on `Base.metadata`, that
`agent_actions.run_id` is nullable (ADR-0002 — there is no real `agent_run` to reference yet), and
that the three append-only audit tables (`agent_runs`, `agent_actions`, `approvals`) carry no
update-enabling construct: no column with `onupdate`, and no foreign key using `ondelete="CASCADE"`.
"""

from __future__ import annotations

from revops.infrastructure.persistence.models import Base

_EXPECTED_TABLES = {
    "organizations",
    "users",
    "accounts",
    "contacts",
    "opportunities",
    "interactions",
    "tasks",
    "agent_runs",
    "agent_actions",
    "approvals",
}

_APPEND_ONLY_TABLES = {"agent_runs", "agent_actions", "approvals"}


def test_all_ten_tables_are_registered_on_base_metadata() -> None:
    assert set(Base.metadata.tables) >= _EXPECTED_TABLES


def test_agent_actions_run_id_is_nullable() -> None:
    run_id_column = Base.metadata.tables["agent_actions"].columns["run_id"]
    assert run_id_column.nullable is True


def test_append_only_tables_have_no_update_enabling_construct() -> None:
    for table_name in _APPEND_ONLY_TABLES:
        table = Base.metadata.tables[table_name]
        for column in table.columns:
            assert column.onupdate is None, f"{table_name}.{column.name} has onupdate set"
        for fk in table.foreign_keys:
            assert fk.ondelete != "CASCADE", f"{table_name} has a CASCADE delete foreign key"


def test_tenant_scoped_tables_index_organization_id() -> None:
    for table_name in _EXPECTED_TABLES - {"organizations"}:
        table = Base.metadata.tables[table_name]
        column = table.columns["organization_id"]
        assert column.index is True, f"{table_name}.organization_id is not indexed"


def test_accounts_domain_unique_per_organization() -> None:
    table = Base.metadata.tables["accounts"]
    unique_constraints = {
        tuple(sorted(c.name for c in constraint.columns))
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert tuple(sorted(("organization_id", "domain"))) in unique_constraints


def test_contacts_email_unique_per_organization() -> None:
    table = Base.metadata.tables["contacts"]
    unique_constraints = {
        tuple(sorted(c.name for c in constraint.columns))
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    assert tuple(sorted(("organization_id", "email"))) in unique_constraints
