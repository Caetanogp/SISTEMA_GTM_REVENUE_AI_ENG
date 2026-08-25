# Runbook: rollback

Applies once phase 5 (cloud + CI/CD) is live. Until then this documents the intended procedure.

## When to roll back

- Smoke tests fail after a deploy
- Error rate, latency p95 or tool failure rate degrades against the previous version
- An eval score drops below threshold in online monitoring
- Any unapproved external action fires

Roll back first, diagnose after. A rollback is cheap; a bad version in production is not.

## Procedure

1. **Identify the previous good version.** Every artifact is tagged with the Git SHA and pinned by
   image digest. `agent_runs` records the versions used, so the last known-good run points at them.
2. **Redeploy the previous image by digest**, not by tag. Tags move; digests do not.
3. **Restore the previous prompt, graph and model config.** These are versioned in the repository,
   so this is part of the same rollback, not a separate manual edit in production.
4. **Do not roll back the database by default.** Migrations are backward-compatible by policy, so
   the previous image runs against the current schema. If a migration must be reverted, check the
   downgrade path first and take a snapshot before running it.
5. **Verify:** health endpoint, one read-only agent run, an audit row written, error rate returning
   to baseline.
6. **Record it:** what broke, which version, what evidence. Add the failing case to
   `evals/regression/` or `tests/adversarial/` before shipping the fix forward.

## What makes this possible

- Docker image tagged by Git SHA and deployed by digest
- Prompt, graph and model config versioned in git, never edited in production
- Backward-compatible migrations (add before remove, two-step)
- `agent_runs` recording every version used

If any of those four stops being true, rollback stops being a one-liner. That is the reason they
are non-negotiable.
