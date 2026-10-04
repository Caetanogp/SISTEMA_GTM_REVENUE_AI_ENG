"""Structural checks on the SQLAlchemy models - no database needed.

Verifies the eleven tables SPEC-001 tasks.md section 4 requires exist on `Base.metadata`, that
`agent_actions.run_id` is now non-null, and that the four append-only audit tables
(`agent_runs`, `agent_actions`, `approvals`, `agent_run_events`) carry no update-enabling
construct: no column with `onupdate`, and no foreign key using `ondelete="CASCADE"`.
"""

from __future__ import annotations

from pgvector.sqlalchemy import Vector
from revops.infrastructure.persistence.models import Base
from sqlalchemy import CheckConstraint, ColumnDefault, UniqueConstraint

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
    "agent_run_events",
    "campaigns",
    "touchpoints",
}

_APPEND_ONLY_TABLES = {"agent_runs", "agent_actions", "approvals", "agent_run_events"}


def test_all_eleven_tables_are_registered_on_base_metadata() -> None:
    assert set(Base.metadata.tables) >= _EXPECTED_TABLES


def test_knowledge_tables_use_explicit_corpus_identity_and_vector_storage() -> None:
    expected = {
        "knowledge_corpora",
        "knowledge_documents",
        "knowledge_document_versions",
        "knowledge_chunks",
        "knowledge_revisions",
        "knowledge_revision_entries",
        "knowledge_revision_activations",
        "knowledge_corpus_heads",
    }
    assert expected <= set(Base.metadata.tables)

    corpora = Base.metadata.tables["knowledge_corpora"]
    checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in corpora.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert "ck_knowledge_corpora_scope" in checks
    assert "ck_knowledge_corpora_scope_owner" in checks
    assert corpora.columns["organization_id"].nullable is True

    chunks = Base.metadata.tables["knowledge_chunks"]
    assert isinstance(chunks.columns["embedding"].type, Vector)
    assert chunks.columns["embedding"].type.dim == 1536
    assert any(index.name == "ix_knowledge_chunks_corpus_id" for index in chunks.indexes)


def test_knowledge_versions_are_idempotent_and_revisions_are_append_only() -> None:
    versions = Base.metadata.tables["knowledge_document_versions"]
    assert any(
        isinstance(constraint, UniqueConstraint)
        and tuple(column.name for column in constraint.columns) == ("corpus_id", "idempotency_key")
        for constraint in versions.constraints
    )

    revisions = Base.metadata.tables["knowledge_revisions"]
    assert all(column.onupdate is None for column in revisions.columns)

    entries = Base.metadata.tables["knowledge_revision_entries"]
    assert "uq_knowledge_revision_entry_document" in {
        constraint.name for constraint in entries.constraints
    }
    activations = Base.metadata.tables["knowledge_revision_activations"]
    assert "uq_knowledge_revision_activation_idempotency" in {
        constraint.name for constraint in activations.constraints
    }
    assert all(column.onupdate is None for column in activations.columns)


def test_knowledge_processing_events_are_append_only_and_idempotent() -> None:
    events = Base.metadata.tables["knowledge_processing_events"]
    assert all(column.onupdate is None for column in events.columns)
    assert "uq_knowledge_processing_events_identity" in {
        constraint.name
        for constraint in events.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert "ix_knowledge_processing_events_history" in {index.name for index in events.indexes}


def test_agent_actions_run_id_is_not_nullable() -> None:
    run_id_column = Base.metadata.tables["agent_actions"].columns["run_id"]
    assert run_id_column.nullable is False


def test_agent_runs_have_explicit_unique_thread_id() -> None:
    table = Base.metadata.tables["agent_runs"]
    thread_id = table.columns["thread_id"]

    assert thread_id.nullable is False
    assert any(
        isinstance(constraint, UniqueConstraint)
        and tuple(column.name for column in constraint.columns) == ("thread_id",)
        for constraint in table.constraints
    )


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
        if isinstance(constraint, UniqueConstraint)
    }
    assert tuple(sorted(("organization_id", "domain"))) in unique_constraints


def test_contacts_email_unique_per_organization() -> None:
    table = Base.metadata.tables["contacts"]
    unique_constraints = {
        tuple(sorted(c.name for c in constraint.columns))
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert tuple(sorted(("organization_id", "email"))) in unique_constraints


def test_deduplication_tables_have_tenant_scoped_idempotency_and_alias_constraints() -> None:
    scans = Base.metadata.tables["deduplication_scans"]
    events = Base.metadata.tables["deduplication_events"]
    account_aliases = Base.metadata.tables["deduplication_account_aliases"]
    contact_aliases = Base.metadata.tables["deduplication_contact_aliases"]
    assert any(
        {column.name for column in constraint.columns} == {"organization_id", "idempotency_key"}
        for constraint in scans.constraints
        if isinstance(constraint, UniqueConstraint)
    )
    assert any(
        {column.name for column in constraint.columns} == {"organization_id", "idempotency_key"}
        for constraint in events.constraints
        if isinstance(constraint, UniqueConstraint)
    )
    assert any(
        {column.name for column in index.columns} == {"organization_id", "alias_id"}
        for index in (*account_aliases.indexes, *contact_aliases.indexes)
    )


def test_attribution_models_declare_the_approved_columns_and_indexes() -> None:
    campaigns = Base.metadata.tables["campaigns"]
    touchpoints = Base.metadata.tables["touchpoints"]
    interactions = Base.metadata.tables["interactions"]
    opportunities = Base.metadata.tables["opportunities"]

    assert {"name", "source", "channel", "metadata", "created_at", "updated_at"} <= set(
        campaigns.columns.keys()
    )
    assert {
        "account_id",
        "contact_id",
        "campaign_id",
        "type",
        "metadata",
        "occurred_at",
        "created_at",
    } <= set(touchpoints.columns.keys())
    assert {"contact_id", "content"} <= set(interactions.columns.keys())
    assert {"status"} <= set(opportunities.columns.keys())
    assert {index.name for index in touchpoints.indexes} >= {
        "ix_touchpoints_org_account_occurred_at",
        "ix_touchpoints_org_campaign_occurred_at",
    }
    status_default = opportunities.columns["status"].default
    assert isinstance(status_default, ColumnDefault)
    assert status_default.arg == "open"


def test_attribution_relationships_use_tenant_scoped_foreign_keys() -> None:
    expected_relationships = {
        "touchpoints": {
            ("organization_id", "account_id"),
            ("organization_id", "contact_id"),
            ("organization_id", "campaign_id"),
        },
        "interactions": {
            ("organization_id", "account_id"),
            ("organization_id", "contact_id"),
        },
        "opportunities": {("organization_id", "account_id")},
    }

    for table_name, relationships in expected_relationships.items():
        table = Base.metadata.tables[table_name]
        foreign_key_columns = {
            tuple(foreign_key.parent.name for foreign_key in constraint.elements)
            for constraint in table.foreign_key_constraints
            if len(constraint.elements) == 2
        }
        assert relationships <= foreign_key_columns


def test_opportunity_status_is_constrained_to_the_approved_lifecycle() -> None:
    opportunities = Base.metadata.tables["opportunities"]
    constraints = {
        constraint.name: str(constraint.sqltext)
        for constraint in opportunities.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert constraints["ck_opportunities_status"] == "status IN ('open', 'won', 'lost')"
