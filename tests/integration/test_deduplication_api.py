"""Integration-boundary checks that do not require a live broker."""

from __future__ import annotations

from fastapi.routing import APIRoute

from apps.api.main import app


def test_deduplication_routes_are_registered_at_admin_boundary() -> None:
    routes = {
        (method, route.path)
        for route in app.routes
        if isinstance(route, APIRoute)
        for method in route.methods
        if route.path.startswith("/admin/deduplication")
    }
    assert ("POST", "/admin/deduplication/scans") in routes
    assert ("GET", "/admin/deduplication/scans/{scan_id}") in routes
    assert ("GET", "/admin/deduplication/merges") in routes
    assert ("POST", "/admin/deduplication/merges/{merge_event_id}/revert") in routes
