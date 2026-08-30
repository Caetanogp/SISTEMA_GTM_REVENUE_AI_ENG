---
agent: claude-code
updated_at: 2026-08-30
branch: feature/SPEC-001-persistence
spec: SPEC-001-vertical-slice-account-prioritization
phase: "1 blocked - Item 4 integration tests surfaced a real, systemic timezone-storage gap in the already-committed schema (Items 1-2); fixing it needs a design decision outside Item 4's declared file scope"
status: persistence-item4-blocked-on-naive-datetime-columns
---

# Current state

## Goal

Ship the SPEC-001 vertical slice end to end: natural-language request -> CRM context -> read tool ->
reasoning -> proposed action -> HITL approval -> write tool -> audit trail.

## Now

On `feature/SPEC-001-persistence`, working tree clean except this file and the queue/gate fixes
below, about to be committed together. `docker compose ps` shows `revops-postgres` and
`revops-redis` both `healthy`.

**Item 1 (SQLAlchemy models)** — done, verified, ticked, committed (`ea2b9b4`), after the
worktree/editable-install blocker documented there and fully retracted in `0581bd2`: **never call
`EnterWorktree` for this project** (`revops` resolves through a PEP 660 editable install pinned to
absolute paths baked in at `pip install -e` time; a worktree silently runs stale code). Unattended
runs are always a plain foreground interactive session in the main checkout from now on.

**Item 2 (first Alembic migration)** — done, verified, ticked. Sequence of events, condensed (full
narrative in commits `18d7ce1`, `8e4eab2` if needed):
1. The `spec001-persistence-loop-2` session generated
   `packages/core/revops/infrastructure/persistence/migrations/versions/bcc6f6ed88c4_create_core_schema_and_audit_tables.py`
   via `alembic revision --autogenerate`, read it line by line per `docs/playbooks/db-migration.md`
   (all 10 tables, `organization_id` indexed everywhere, the two unique constraints, `run_id`
   nullable per ADR-0002, no LangGraph checkpoint tables, no `onupdate`/cascade-delete, correct
   FK-reverse drop order), and proved `alembic upgrade head` cleanly. It then hit `alembic
   downgrade -1` — genuinely denied by the tool permission layer: `.claude/settings.json` puts
   `"Bash(alembic downgrade:*)"` in the `ask` list (next to `git push`/`git merge`), and this
   session runs `--permission-mode dontAsk`, which auto-denies everything in `ask` rather than
   waiting for a human who isn't there. It correctly refused to route around this (no direct
   Alembic API call, no raw `DROP TABLE`) and halted, explaining exactly why in `8e4eab2` and
   committing the migration file itself as WIP in `18d7ce1`.
2. The main session (not `dontAsk`) ran the missing half by hand, with the user's explicit
   approval after an explanation of what upgrade/downgrade/round-trip mean and why they matter:
   ```
   $ alembic current
   bcc6f6ed88c4 (head)
   $ alembic downgrade -1
   INFO  [alembic.runtime.migration] Running downgrade bcc6f6ed88c4 -> , create core schema and audit tables
   $ alembic current
   (empty - back to base)
   $ psql ... SELECT tablename FROM pg_tables WHERE schemaname='public'
   alembic_version, checkpoint_blobs, checkpoint_migrations, checkpoint_writes, checkpoints
   (all 10 business tables genuinely gone - only alembic_version + the LangGraph-owned checkpoint
   tables, which ADR-0002 says live outside this migration entirely, remained)
   $ alembic upgrade head
   INFO  [alembic.runtime.migration] Running upgrade  -> bcc6f6ed88c4, create core schema and audit tables
   $ alembic current
   bcc6f6ed88c4 (head)
   $ psql ... SELECT tablename FROM pg_tables WHERE schemaname='public'
   accounts, agent_actions, agent_runs, alembic_version, approvals, checkpoint_*, contacts,
   interactions, opportunities, organizations, tasks, users
   (all 10 business tables genuinely back)
   ```
   Also independently re-verified the indexes/constraints against the live database (not just the
   migration file's text): `ix_accounts_organization_id`, `ix_agent_actions_organization_id`,
   `ix_agent_runs_organization_id`, `ix_approvals_organization_id`,
   `ix_contacts_organization_id`, `ix_interactions_organization_id`,
   `ix_opportunities_organization_id`, `ix_tasks_organization_id`, `ix_users_organization_id`,
   `uq_accounts_org_domain`, `uq_contacts_org_email` — all 9 indexes and both unique constraints
   present for real via `SELECT indexname FROM pg_indexes`.
   Also fixed one real `ruff` `E501` (line 146, 105 > 100 chars) in the migration file with
   `ruff check --fix` + `ruff format` — cosmetic only, confirmed `def upgrade`/`def downgrade`
   both still present after.
   `.claude/settings.json`'s `ask` list was **not** changed — `alembic downgrade` stays
   human-reviewed on purpose. This does not set a precedent for a `dontAsk` session to route
   around an `ask`-listed command; it is the one thing only a human can do here.
3. Ticked both `tasks.md` §3 checkboxes Item 2 closes (the round-trip line, and the indexes line —
   both verified together against the live database in step 2).

**A real gate-script bug found and fixed in the process**: `scripts/autonomous_gate.py` indexed
the queue directly by `done_count` (`items[done_count]`), assuming one tasks.md checkbox per queue
item. Item 2 closes *two* checkboxes (the migration round-trip line and the indexes line, verified
together), so the moment both were ticked, `done_count` jumped past Item 3 entirely and the gate
would have told the next session to start Item 4 (integration tests) - skipping Item 3
(repositories) completely, silently. Fixed by adding an explicit `QueueItem.closes: int = 1` field
(parsed from an optional `- **Closes:** N tasks.md checkboxes` line in the item's body) and
`item_for_done_count()`, which walks the cumulative sum instead of indexing directly. Verified:
`sum(item.closes for item in items[:4]) == 5 == total_count`, and the gate now correctly points at
Item 3 with `done_count=3`. Item 2 in `AUTONOMOUS_QUEUE.md` now declares `- **Closes:** 2 tasks.md
checkboxes` explicitly.

**Item 3 (repositories and `SqlAlchemyUnitOfWork`)** — done, verified, ticked, committed
(`64e3621`). `packages/core/revops/infrastructure/persistence/repositories.py`:
`SqlAlchemyAccountRepository` (read-only — `get`, `list_for_organization`, `list_interactions`,
`list_open_opportunities`, no write method), `SqlAlchemyTaskRepository` (`add`, `get`, `update`),
`SqlAlchemyAuditTrail` (`record`, always writes `run_id=None` per ADR-0002). All implement
`application/ports.py`'s Protocols structurally — no inheritance, matching the convention
`tests/unit/application/test_ports.py` already established for the fakes. `organization_id` is
filtered inside every method's `WHERE` clause, never left to the caller. `CompanyDomain` is
reidrated from the stored primitive at the repository boundary; `OpportunityStage`/`TaskStatus`
round-trip through their `.value`.
`unit_of_work.py`: `SqlAlchemyUnitOfWork` takes an already-constructed `AsyncSession` in its
constructor (not a session factory — the composition root owns session lifecycle) and builds
`self.accounts`/`self.tasks`/`self.audit` from it immediately, so `isinstance(uow, UnitOfWork)`
holds right after construction without needing `__aenter__` first (matches the
`_FakeUnitOfWork` convention in `test_ports.py`). `commit`/`rollback` delegate to the shared
session; `__aexit__` rolls back only if the `async with` block raised. `DecideApproval`'s
constructor and call signature are untouched, per ADR-0002.
`tests/unit/infrastructure/persistence/test_repositories.py` (12 tests, no database): isinstance
against each Protocol, `SqlAlchemyAccountRepository` has no write methods, the three ports share
one session object, commit/rollback delegate correctly, rollback fires on exception but not on
clean exit, `record()` writes `run_id=None`, `add()` stores `TaskStatus.OPEN` as `"open"`. Mocked
the session with `MagicMock(spec=AsyncSession)`, not a bare `AsyncMock()` — a bare `AsyncMock`
makes `session.add()` (genuinely synchronous on `AsyncSession`) into a coroutine mock too, which
passes silently but leaves an unawaited-coroutine warning; `spec=` catches the same class of
sync/async mismatch the real database would catch in Item 4, one layer earlier.
Gate green at this point: `ruff: OK, mypy: OK, lint-imports: OK, pytest: OK, check_agent_docs: OK`.
One exploration worth recording so a future session doesn't repeat it: running `mypy` on
`repositories.py`/`models.py` **in isolation** (`mypy packages/.../repositories.py`) reported two
spurious `Numeric` generic/arg-type errors that do **not** reproduce when `mypy .` (the gate's own
invocation, whole project) runs — confirmed not a stale-cache artifact via `mypy --no-incremental
.` too. Trust `mypy .` (what the gate actually runs), not a single-file invocation, for this repo.

**Item 4 (integration tests against Docker Postgres) — blocked, not ticked.** Wrote
`tests/integration/test_persistence_repositories.py` (scope-correct: only this file, reusing
`tests/integration/conftest.py`'s `database_url` fixture, no second conftest). Each test runs
inside its own connection-bound transaction with a SAVEPOINT
(`AsyncSession(connection, join_transaction_mode="create_savepoint")`, rolled back at teardown) so
nothing pollutes the shared dev database. Also had to add a session-scoped `event_loop_policy`
fixture forcing `WindowsSelectorEventLoopPolicy` on `sys.platform == "win32"` — the same psycopg
async/`ProactorEventLoop` issue ADR-0002 and `migrations/env.py` already hit, now hitting
pytest-asyncio's own loop too; this fixture lives inside the test file itself, not a new/edited
conftest, so it stays in scope.

12 tests written, covering every method on all three repositories, `SqlAlchemyAuditTrail`, both
value-object round-trips the queue names (`CompanyDomain` via `AccountRepository.get`,
`EmailAddress` via a directly-seeded `Contact` row — there is no `ContactRepository` port to go
through, ports.py never defines one), a `Score` computed from persisted `Interaction`/
`Opportunity` rows, `Task.mark_done` persisted and reloaded, an illegal transition
(`InvalidTransitionError`) still raised after a real save/reload, and the explicit tenant-isolation
test (`TestTenantIsolation::test_repository_calls_never_return_or_mutate_another_organizations_rows`
— two orgs, `get`/`update` scoped to the wrong org both raise `NoResultFound`, the right org's row
is provably untouched afterward).

**Result: 10 passed, 2 failed — for a real reason, not a test bug.**
```
FAILED ...TestTaskRepository::test_add_then_get_round_trips_the_task
  AssertionError: due_at: datetime.datetime(2026, 2, 1, 0, 0) != datetime.datetime(2026, 2, 1, 0, 0, tzinfo=datetime.timezone.utc)
FAILED ...TestValueObjectRoundTrips::test_score_computes_correctly_from_persisted_interactions_and_opportunities
  TypeError: can't subtract offset-naive and offset-aware datetimes
    (packages/core/revops/domain/policies/prioritization.py:52, recency_signal: `now - last.occurred_at`)
```
**Root cause, confirmed by inspection, not guessed:** every `Mapped[datetime]` column in
`packages/core/revops/infrastructure/persistence/models.py` (`Account.created_at`,
`Interaction.occurred_at`, `Task.due_at`, `AgentRun.started_at`/`completed_at`,
`AgentAction.occurred_at`/`executed_at`, `Approval.decided_at` — 6 distinct columns, checked via
`grep -n "Mapped\[datetime\]" models.py`) maps to a plain `sa.DateTime()`, which Postgres stores
and returns as `TIMESTAMP WITHOUT TIME ZONE`. Every domain entity is reidrated with a **naive**
datetime regardless of what was written in. Every other timestamp in this codebase is
timezone-aware by convention — `Clock.now()`'s only real implementation would return
`datetime.now(UTC)`, `_FakeClock` in `tests/unit/application/test_ports.py` returns
`datetime(2026, 1, 1, tzinfo=UTC)`, `docs/decisions/` and the checkpoint spike are UTC throughout.
The moment a real `Clock` adapter and this persistence layer meet (exactly what Item 4 is supposed
to prove happens safely), `domain/policies/prioritization.py`'s `recency_signal` — and by
extension `PrioritizeAccounts`, SPEC-001's actual vertical slice — crashes on `now -
last.occurred_at` with real data. This is not cosmetic and not a false alarm from an unrealistic
test: it is what the real DB genuinely does today.

**Why I stopped instead of fixing it inline:** two real, differently-costed, defensible fixes
exist, and both require touching files outside Item 4's declared scope
(`tests/integration/test_persistence_repositories.py` only):
1. **Fix the schema**: change every `Mapped[datetime]` column to `DateTime(timezone=True)`
   (`TIMESTAMPTZ`) in `models.py` — the textbook-correct fix for storing instants in Postgres — but
   that means amending Item 1's already-ticked, already-committed file and writing a **second**
   Alembic migration (an `ALTER COLUMN ... TYPE timestamptz` across 6 columns in 6 tables) on top
   of Item 2's already-ticked, already-committed migration. Bigger blast radius than "add a test
   file."
2. **Normalize at the repository boundary**: have `repositories.py`'s `_to_account`/`_to_task`/
   `_to_interaction`/`_to_opportunity` attach `tzinfo=UTC` when reidrating (`row.due_at.replace(
   tzinfo=UTC)`), on the assumption "everything this schema stores is implicitly UTC." Cheaper,
   no new migration, but it is an implicit convention nowhere written down, it only covers what
   Item 3's repositories already read (not `AgentRun`/`Approval`, which have no adapter yet per
   ADR-0002), and it means editing Item 3's already-ticked, already-committed `repositories.py`.
   This is also technically outside Item 4's declared scope.
Both are real architectural decisions with tradeoffs, discovered mid-implementation of a
downstream item, on a question ADR-0002 never addressed (it covers checkpoint-table ownership,
`run_id` nullability, and the async story — not column timezone-awareness). This is exactly the
class of thing `AGENTS.md`'s standing complexity-flagging rule requires stopping for: *"a new
component shape... anything with more than one defensible approach... stop and say so explicitly
before writing code."* Making the test pass by comparing naive-vs-naive, or by hand-normalizing
inside the test file only, was rejected too — it would hide a defect Item 4's own purpose is to
surface, not paper over it (`AGENTS.md` golden rule 8: never weaken a check to make it pass).

**State left behind:** `tests/integration/test_persistence_repositories.py` is written and
committed as-is (10/12 passing, the 2 failures are the finding, not noise) —
`docs/specs/.../tasks.md`'s Item 4 checkbox is **not** ticked. Nothing in `models.py`,
`repositories.py`, or the migration was touched to work around this.

## Done (prior sessions — condensed; full detail in git history and `.handoff/log/`)

- Domain layer, application layer (all 6 SPEC-001 tasks.md section 2 items, merged to `develop` at
  `adce03d`).
- SPEC-001 persistence Phase 0 (Alembic scaffolding, checkpoint-restart spike, ADR-0002, queue
  rewrite) — `.handoff/log/2026-08-29-1929-claude.md`.
- Item 1 (SQLAlchemy models) — see "Now" above.
- Item 2 (first Alembic migration, indexes) — see "Now" above.
- Item 3 (repositories, `SqlAlchemyUnitOfWork`) — see "Now" above.

## Next

1. **A human needs to pick between the two options above** (schema fix + new migration, vs.
   repository-boundary normalization) for the naive-datetime-column finding, or propose a third —
   this is a real design decision, not something to default on. Whichever is chosen will touch
   files outside every currently-open item's declared scope (`models.py` and/or a new migration
   file, and/or `repositories.py`), so it likely wants its own small queue item /
   `AUTONOMOUS_QUEUE.md` entry, or the user doing it directly in a plan-mode session, rather than
   an unattended `dontAsk` session picking it unilaterally.
2. Once fixed, re-run `pytest tests/integration/test_persistence_repositories.py -q` — the file
   itself does not need to change, only the schema/repository fix underneath it — confirm all 12
   tests pass, then tick Item 4's `tasks.md` box with that as evidence, `python
   scripts/autonomous_gate.py` should then report `GOAL ACHIEVED` (all 5 tasks.md §3 boxes ticked,
   full gate green — `pytest tests/unit tests/architecture -q`, note the gate itself does not run
   `tests/integration`, so re-confirming the integration suite by hand each time is on the human/
   session doing this, not automatic).
3. Item 5 (LangGraph) is still untouched and still needs a fresh session, Opus, plan mode —
   unchanged from before this run. It is reached via the gate's `exit 0` "GOAL ACHIEVED" path once
   all 5 tasks.md §3 checkboxes are ticked (same functional-equivalence reasoning as the
   application-layer run before it), not an explicit `exit 2` HALT — `completed_task_count()` only
   reads tasks.md §3, and Item 5's own `closes` value is never reached by `item_for_done_count`
   since items 1-4 already cover all 5 checkboxes.

## Gotchas

- **`.claude/settings.json`'s `ask` list is auto-denied, not auto-approved, under `dontAsk`
  permission mode.** Correct and by design, but it silently blocks any queue item whose *done
  criterion itself* requires an `ask`-listed command — `alembic downgrade` for Item 2 was the first
  concrete case, resolved by a human running it once, by hand, outside `dontAsk`. Check any
  remaining queue item's done criterion against the `ask` list before assuming a `dontAsk` session
  can complete it fully unattended; if it can't, that is a "pause and let the main session run one
  command" case, not a bug and not something to route around.
- Compound/chained Bash commands (`cmd1 && cmd2`) are matched and denied as a whole if any part
  falls outside the allow-list — do not try to sneak an ask/deny-listed command through by
  chaining it after an allowed one.
- `docker compose ps` can report an empty table (no error) when containers exist but are stopped —
  check `docker ps -a` / `docker compose ps -a` for `Exited` containers before concluding Docker
  "isn't running"; `docker compose up -d` restarts already-created containers without recreating
  them.
- **`AUTONOMOUS_QUEUE.md` items must declare `- **Closes:** N tasks.md checkboxes` whenever an
  item's own completion ticks more than one line in tasks.md** — `autonomous_gate.py`'s
  `item_for_done_count()` depends on every item's `closes` summing to the section's total checkbox
  count. Get this wrong and the gate silently points the next session at the wrong item.
- All gotchas from `.handoff/log/2026-08-29-1929-claude.md` (OneDrive/Defender git & filesystem
  interference, psycopg's Windows event-loop policy requirement, the checkpoint-table autogenerate
  trap, pre-commit unreliability, missing `__init__.py` in declared scope) still apply unchanged.
- **Never call `EnterWorktree` for this project** — see `AUTONOMOUS_QUEUE.md`'s "Rules for the
  loop" and `docs/playbooks/autonomous-loop.md`; always run unattended work as a plain foreground
  session in the main checkout.

## Resume

```bash
cd "SISTEMA_PORTFOLIO_AI_ENG"
git status                                  # confirm branch and clean tree first
git rev-parse --abbrev-ref HEAD             # should be feature/SPEC-001-persistence
docker compose ps                           # confirm revops-postgres, revops-redis healthy
python scripts/autonomous_gate.py           # still points at Item 4 - it doesn't know about the finding
pytest tests/integration/test_persistence_repositories.py -q   # 10 passed, 2 failed - see ## Now
```
Read `## Now` above before doing anything else — the finding and both real fix options are there.

## Open questions

- **Should datetime columns be `TIMESTAMPTZ` (schema + new migration) or should the repository
  boundary normalize to UTC on read (edit `repositories.py`)?** New, from this session — see
  `## Now`'s Item 4 entry for the full finding and both options' tradeoffs. Blocks Item 4.
- Should `"Bash(alembic downgrade:*)"` move from `.claude/settings.json`'s `ask` list to `allow`
  for this project, given that every migration's done criterion needs the round-trip run? Still
  open, deliberately not decided inside a loop session — real security-policy tradeoff (grouped
  with `git push`/`git merge` on purpose). Current working pattern (a human runs it once per
  migration, outside `dontAsk`) is fine for this project's pace; revisit only if it becomes
  friction.
- Same open questions as `.handoff/log/2026-08-29-1929-claude.md`: OneDrive/Defender exclusion,
  provider keys not configured, `docs/tooling/RESEARCH.md` items still just-in-time.
