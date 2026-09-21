# ADR-0008: Preserve the supervisor's external temporary directory

- **Status:** accepted
- **Date:** 2026-09-13
- **Context:** SPEC-005 autonomous loop

## Context

The loop must keep supervisor and child-process temporary files outside the checkout. On Windows,
passing a host-style custom `TEMP`, `TMP`, or `PYTEST_ADDOPTS` path through the launcher can cause
the Codex sandbox to reinterpret it as a relative path and recreate pytest artifacts under the
checkout.
Those artifacts can be scanned by `mypy` and reported as out-of-scope changes by the autonomous
gate.

## Decision

The supervisor selects its artifact directory from the native OS temporary root, verifies that the
resolved path is outside the repository and not a reparse point, and passes no host-style temp
overrides to Codex children. The child still runs with `workspace-write` for implementation or
`read-only` for architecture review; no dangerous full-access mode is enabled.

## Consequences

The loop preserves artifact isolation on Windows while retaining the Codex sandbox mode. Normal
project Codex sessions continue using the project default. A future CLI change to
temporary-directory handling must rerun the short pilot and verify that no generated path appears
under the checkout.
