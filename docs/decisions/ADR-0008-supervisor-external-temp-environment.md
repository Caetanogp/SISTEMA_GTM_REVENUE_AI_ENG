# ADR-0008: Preserve the supervisor's external temporary directory

- **Status:** accepted
- **Date:** 2026-09-13
- **Context:** SPEC-005 autonomous loop

## Context

The launcher creates a temporary directory outside the checkout and passes it through `TEMP`,
`TMP` and `PYTEST_ADDOPTS`. The project Codex configuration sets
`sandbox_workspace_write.exclude_tmpdir_env_var = true`; on Windows, that causes child Codex
processes to discard the external values and create pytest artifacts under the checkout instead.
Those artifacts can be scanned by `mypy` and reported as out-of-scope changes by the autonomous
gate.

## Decision

The supervisor passes the narrow CLI override
`sandbox_workspace_write.exclude_tmpdir_env_var=false` to every child Codex process. The child
still runs with `workspace-write` for implementation or `read-only` for architecture review; no
dangerous full-access mode is enabled. The launcher-owned temporary directory remains external to
the checkout and is used only for pytest and structured supervisor artifacts.

## Consequences

The loop preserves its intended artifact isolation on Windows while retaining the Codex sandbox
mode. The override is explicit, test-covered and limited to supervisor children; normal project
Codex sessions continue using the project default. A future CLI change to temporary-directory
handling must rerun the short pilot and verify that no generated path appears under the checkout.
