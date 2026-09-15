"""Structural safeguards for the forward-only schema reconciliation."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

_VERSIONS = (
    Path(__file__).parents[4]
    / "packages/core/revops/infrastructure/persistence/migrations/versions"
)
_REPAIR = _VERSIONS / "f6a8c0d2b5e7_reconcile_legacy_deduplication_schema.py"
_PUBLISHED_DEDUPLICATION = _VERSIONS / "b7c9d1e2f304_add_deduplication_tables.py"
_PUBLISHED_DEDUPLICATION_SHA256 = "e624f89b4182b0b56c692895d82280a992274e178b3ae44383d95bcff4e19ed3"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    module = ast.parse(_source(_REPAIR))
    function = next(
        node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == name
    )
    return ast.unparse(function)


def test_repair_is_a_new_revision_after_attribution() -> None:
    source = _source(_REPAIR)

    assert 'revision: str = "f6a8c0d2b5e7"' in source
    assert 'down_revision: str | None = "e4f6a8c0d2b5"' in source


def test_repair_upgrade_is_additive_and_downgrade_is_monotonic() -> None:
    upgrade = _source(_REPAIR).split("def downgrade", maxsplit=1)[0].upper()
    downgrade = _function_source("downgrade")

    for destructive_operation in ("DROP ", "DELETE ", "TRUNCATE "):
        assert destructive_operation not in upgrade
    assert "pass" in downgrade


def test_published_deduplication_revision_is_immutable() -> None:
    normalized = _source(_PUBLISHED_DEDUPLICATION).replace("\r\n", "\n").encode()

    assert hashlib.sha256(normalized).hexdigest() == _PUBLISHED_DEDUPLICATION_SHA256


def test_thread_id_revision_is_forward_only_and_additive() -> None:
    migration = _VERSIONS / "a1b2c3d4e5f6_add_agent_run_thread_id.py"
    source = _source(migration)
    upgrade = source.split("def downgrade", maxsplit=1)[0].upper()

    assert 'revision: str = "a1b2c3d4e5f6"' in source
    assert 'down_revision: str | None = "f6a8c0d2b5e7"' in source
    for destructive_operation in ("DROP ", "DELETE ", "TRUNCATE "):
        assert destructive_operation not in upgrade
