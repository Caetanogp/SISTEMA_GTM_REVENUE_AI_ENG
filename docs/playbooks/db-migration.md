# Playbook: model change and migration

Migrations run against a database that already holds state. Backward-compatible or nothing.

## Steps

1. Change the domain entity first, if the change has business meaning. The SQLAlchemy model in
   `infrastructure/persistence/models.py` follows the domain — not the other way round.
2. Generate and then **read** the migration:
   ```bash
   alembic revision --autogenerate -m "add risk_level to agent_actions"
   ```
   Autogenerate misses constraint changes, index intent and data moves. Review every line.
3. Test both directions against a real database:
   ```bash
   alembic upgrade head && alembic downgrade -1 && alembic upgrade head
   ```

## Backward-compatible pattern

Never drop or rename in one step. Two deploys:

1. add the new nullable column → backfill → start writing both → switch reads
2. (next release) stop writing the old column → drop it

A rename is an add + backfill + drop, never an `ALTER ... RENAME` while the old code is running.

## Rules

- New column on a populated table: nullable, or with a server default. A `NOT NULL` without a
  default locks and fails.
- Index anything you filter or join on — `organization_id` on every tenant-scoped table, foreign
  keys, and the columns behind the pipeline queries.
- pgvector: the embedding column is versioned alongside the model that produced it. Changing the
  embedding model means a new column or a re-index, never silently mixed vectors.
- Audit tables (`agent_runs`, `agent_actions`, `approvals`) are append-only: no `ON UPDATE`, no
  destructive migration, ever.
- Data migrations go in the migration file, are idempotent, and are batched for large tables.

## Checklist

- [ ] Domain changed first when the change has business meaning
- [ ] Migration read line by line, not trusted from autogenerate
- [ ] `upgrade` → `downgrade` → `upgrade` verified locally
- [ ] Backward-compatible (add before remove)
- [ ] Indexes for new filters/joins, `organization_id` included
- [ ] Integration test covering the new shape
