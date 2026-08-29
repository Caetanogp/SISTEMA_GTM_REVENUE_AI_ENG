import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from revops.infrastructure.persistence.models import Base
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# DATABASE_URL is the same env var every other adapter and CI use
# (postgresql+psycopg://... - the SQLAlchemy dialect form). Falls back to the local
# docker-compose default so migrations work out of the box in dev.
_DEFAULT_DATABASE_URL = "postgresql+psycopg://revops:revops@localhost:5432/revops"
config.set_main_option("sqlalchemy.url", os.environ.get("DATABASE_URL", _DEFAULT_DATABASE_URL))

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# The LangGraph checkpointer (AsyncPostgresSaver.setup(), see the checkpoint-restart spike)
# owns its own tables (checkpoints, checkpoint_blobs, checkpoint_writes,
# checkpoint_migrations) - deliberately outside this schema (see the persistence ADR: chasing
# a third-party library's internal schema on every upgrade is the wrong ownership model).
# Without this filter, autogenerate sees them as "removed" relative to our metadata and
# `alembic upgrade head` would DROP them - confirmed live during bootstrap, not theoretical.
_LANGGRAPH_CHECKPOINT_TABLES = frozenset(
    {"checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations"}
)


def include_name(name: str | None, type_: str, parent_names: dict[str, str | None]) -> bool:
    return not (type_ == "table" and name in _LANGGRAPH_CHECKPOINT_TABLES)


# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_name=include_name,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection, target_metadata=target_metadata, include_name=include_name
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    if sys.platform == "win32":
        # psycopg's async driver cannot run on Windows' default ProactorEventLoop - see the
        # same issue proven and documented in the checkpoint-restart spike
        # (tests/integration/_checkpoint_restart_fixtures/). Any async psycopg code on
        # Windows needs this, not just this one call site.
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
