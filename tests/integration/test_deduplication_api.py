"""Integration-boundary checks that do not require a live broker."""

from __future__ import annotations

from apps.api.main import app


def test_deduplication_routes_are_registered_at_admin_boundary() -> None:
    paths = app.openapi()["paths"]
    assert "post" in paths["/admin/deduplication/scans"]
    assert "get" in paths["/admin/deduplication/scans/{scan_id}"]
    assert "get" in paths["/admin/deduplication/merges"]
    assert "post" in paths["/admin/deduplication/merges/{merge_event_id}/revert"]
