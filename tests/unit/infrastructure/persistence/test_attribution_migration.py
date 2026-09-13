"""Offline structural checks for the additive CRM attribution migration."""

from __future__ import annotations

import ast
from pathlib import Path

_MIGRATION_PATH = (
    Path(__file__).parents[4]
    / "packages/core/revops/infrastructure/persistence/migrations/versions"
    / "e4f6a8c0d2b5_add_crm_attribution_schema.py"
)


def _migration_source() -> str:
    return _MIGRATION_PATH.read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    module = ast.parse(_migration_source())
    function = next(
        node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == name
    )
    return ast.unparse(function)


def test_attribution_migration_is_chained_to_the_current_head() -> None:
    source = _migration_source()

    assert 'revision: str = "e4f6a8c0d2b5"' in source
    assert 'down_revision: str | None = "b7c9d1e2f304"' in source


def test_attribution_upgrade_adds_the_approved_schema_and_backfill() -> None:
    upgrade = _function_source("upgrade")

    assert "op.create_table('campaigns'" in upgrade
    assert "op.create_table('touchpoints'" in upgrade
    assert "uq_campaigns_org_id" in upgrade
    assert "accounts.organization_id" in upgrade
    assert "contacts.organization_id" in upgrade
    assert "campaigns.organization_id" in upgrade
    assert "fk_interactions_org_contact" in upgrade
    assert "fk_opportunities_org_account" in upgrade
    assert "ix_touchpoints_org_account_occurred_at" in upgrade
    assert "ix_touchpoints_org_campaign_occurred_at" in upgrade
    assert "ix_interactions_org_contact_occurred_at" in upgrade
    assert "ix_opportunities_org_status" in upgrade
    assert "UPDATE opportunities SET status = 'open' WHERE status IS NULL" in upgrade
    assert "ck_opportunities_status" in upgrade


def test_attribution_upgrade_contains_no_destructive_operations() -> None:
    upgrade = _function_source("upgrade").upper()

    assert "OP.DROP_" not in upgrade
    assert "DROP TABLE" not in upgrade
    assert "DELETE FROM" not in upgrade
    assert "TRUNCATE" not in upgrade
