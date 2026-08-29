# ADR-0002: Persistence layer — checkpoint ownership, audit atomicity, and the async story

- **Status:** accepted
- **Date:** 2026-08-29
- **Context spec:** SPEC-001

## Context

SPEC-001's application layer (ports, DTOs, three use cases, context builder) is complete and
merged. The next item in the queue was Item 7 — the LangGraph node/checkpoint/interrupt wiring —
but it was halted (`AUTONOMOUS_QUEUE.md`) pending a deliberate plan, because it sits on persistence
that does not exist yet: `execute_action` calls `DecideApproval`, which writes through
`TaskRepository` and `AuditTrail`, and only fakes of those exist today. `plan.md`'s own order of
work puts persistence before the graph for exactly this reason.

Mapping the code before planning surfaced four concrete gaps, not theoretical ones:

1. `DecideApproval`'s once-only guard (`PendingApproval.decided`) lives on a plain, mutable
   Python object — it does not survive a process restart, which is acceptance criterion 7's whole
   point.
2. Acceptance criterion 9 (`graph_version`, `prompt_version`, cost) has no table to write to.
3. The checkpointer needs a live Postgres — the same database this layer stands up.
4. `AuditTrail.record()` (`application/ports.py`, already committed and tested) has no `run_id`
   parameter, because no `agent_run` exists yet to reference.

This ADR records the decisions needed to build the persistence layer without reopening the
application layer, plus two real findings hit while implementing it.

## Options considered

### Where do `agent_runs` / `agent_actions` / `approvals` live?

1. **Domain entities**, mirroring `Account`/`Task`/etc. Consistent with the rest of the domain,
   but the domain models business rules the system reasons about — nothing in `domain/policies/`
   or any use case asks a question about an `AgentRun`'s shape. It would be a type nothing acts on.
2. **Infrastructure-only, behind the `AuditTrail` port** (chosen). The audit trail is already a
   cross-cutting concern abstracted by a port; the tables are what that port's adapter writes to,
   not business objects with behaviour.

### How does `agent_actions.run_id` get populated before a graph exists?

1. **Block persistence on the graph** — do nothing here until `agent_runs` exists for real.
   Rejected: it inverts `plan.md`'s own ordering and leaves `DecideApproval` un-backed indefinitely.
2. **Add `run_id` to the `AuditTrail.record()` port now**, as `UUID | None`. Rejected: it reopens
   a port signature `verify-before-done` already passed and 118 tests already cover, for a
   parameter this layer cannot legitimately populate yet.
3. **`agent_actions.run_id` nullable now, `NOT NULL` later** (chosen). Exactly the two-step pattern
   `docs/playbooks/db-migration.md` prescribes for a column that isn't ready for a full constraint:
   add nullable → backfill → tighten, across two migrations instead of one.

### Who owns the LangGraph checkpoint tables?

1. **A migration in this repo**, generated once from `AsyncPostgresSaver`'s current schema.
   Rejected: it means chasing the library's internal schema by hand on every LangGraph upgrade,
   and there is no guarantee the internal shape stays stable across versions.
2. **`AsyncPostgresSaver.setup()` owns them, Alembic ignores them** (chosen). `spec.md` only ever
   says "plus the LangGraph checkpoint tables" — it never assigns ownership. Treating them as a
   fully external, third-party-owned schema is the honest description of what they are: they carry
   no `organization_id`, follow none of this project's append-only conventions, and are not
   business or audit data by our own definition (see the memory-separation table in
   `docs/architecture/overview.md`: "Thread / short-term → LangGraph checkpoint" is explicitly a
   different kind of memory than "Business state → PostgreSQL").

### How does `DecideApproval`'s two independent writes (`tasks.add`, `audit.record`) become atomic?

1. **Change `DecideApproval` to take `UnitOfWork` instead of three separate ports.** Rejected for
   now: it is an application-layer signature change to code that is done, tested and merged,
   for a caller (the graph's `execute_action` node) that does not exist yet.
2. **`SqlAlchemyUnitOfWork` exposes `accounts`/`tasks`/`audit` on one shared session; the caller
   composes atomicity** (chosen): `async with uow: await decide_approval.approve(...); await
   uow.commit()`. The use case is untouched; the transaction boundary is the composition root's
   job, which is where it belongs once the graph (or, later, the API) exists to be that caller.

## Decision

- **`agent_runs`, `agent_actions`, `approvals` are infrastructure tables with no domain entity.**
  Only `agent_actions` gets a repository adapter now (`SqlAlchemyAuditTrail`, backing the
  `AuditTrail` port that already exists). `agent_runs` and `approvals` get adapters when the graph
  and API phases have a writer for them.
- **`agent_actions.run_id` is nullable in this migration.** Tightening it to `NOT NULL` is a second,
  explicit migration once a real `agent_run` exists to backfill against — not a note-to-self, an
  actual future step. Until then, an audit row cannot be traced back to the run that produced it,
  which is a real, temporary violation of `AGENTS.md`'s "a failure must be reproducible from the
  row alone." Accepted as a bounded-duration cost, not a permanent one.
- **The LangGraph checkpoint tables (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`,
  `checkpoint_migrations`) are excluded from Alembic's autogenerate** via an `include_name` filter
  in `migrations/env.py`. Confirmed necessary live, not in theory: the first autogenerate run
  against a database that already had `AsyncPostgresSaver.setup()` applied (from the checkpoint
  spike) detected all four tables as "removed" and would have dropped them on `upgrade`.
- **`SqlAlchemyUnitOfWork` shares one `AsyncSession` across `accounts`/`tasks`/`audit`.**
  `DecideApproval`'s signature does not change.
- **SQLAlchemy is async throughout** (`create_async_engine`, `AsyncSession`), matching every port
  in `application/ports.py` already being `async def` except `Clock.now`. DSN stays
  `postgresql+psycopg://` (SQLAlchemy's dialect form, same as CI's `DATABASE_URL`) for the ORM;
  adapters needing the raw libpq form (LangGraph's checkpointer) strip the `+psycopg` segment.

## Real findings from building this (not decisions, but load-bearing)

- **psycopg's async driver cannot run on Windows' default `ProactorEventLoop`.** Every async
  entry point that touches Postgres on this machine — the checkpoint-restart spike's two
  subprocess scripts and Alembic's `env.py` — needs
  `asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())` set before
  `asyncio.run(...)`, guarded by `sys.platform == "win32"`. This will bite again the moment a
  composition root (API, worker) is built on this machine — it is not a one-off spike quirk.
- **The checkpoint-table drop above is real, reproducible risk, not a hypothetical one.** Anyone
  running `alembic revision --autogenerate` against a database that already has LangGraph's tables,
  without the `include_name` filter, generates a migration that drops them.

## Consequences

**Easier:** the application layer stays untouched and still 118-tests-green · the persistence layer
can be built and verified (including the checkpoint-restart proof) entirely independent of the
graph · `SqlAlchemyUnitOfWork` gives the eventual composition root one clean seam for atomicity
instead of ad-hoc transaction handling per caller.

**Harder:** an audit row written during this phase cannot be traced to a run until the graph phase
backfills `run_id` · two migrations instead of one for that column · the checkpoint tables are a
schema this project does not control or version, which the next person touching persistence needs
to know before they "helpfully" add them to a migration.

**Cost accepted:** the `run_id`-nullable window is real and temporary, not indefinite — it closes
in the graph phase, and this ADR is what makes that a tracked decision instead of a silently
loosened invariant.

**Revisit if:** `agent_runs`/`approvals` need a repository before the graph phase (would mean this
ADR's phasing was wrong), or LangGraph ships a documented, stable checkpoint schema worth vendoring
into a real migration (would remove the reason for `include_name`).
