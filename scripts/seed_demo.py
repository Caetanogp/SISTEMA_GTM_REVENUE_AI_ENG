"""Command-line entrypoint for the deterministic synthetic demo seed."""

from __future__ import annotations

import asyncio

from revops.infrastructure.persistence.demo_seed import seed_database
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.api.settings import ApiSettings


async def _run(database_url: str) -> None:
    engine = create_async_engine(database_url)
    try:
        rows = await seed_database(async_sessionmaker(engine, expire_on_commit=False))
    finally:
        await engine.dispose()
    print(
        "Seeded synthetic demo tenant: "
        f"organization={rows.organization.id}, accounts={len(rows.accounts)}, "
        f"contacts={len(rows.contacts)}, opportunities={len(rows.opportunities)}, "
        f"interactions={len(rows.interactions)}"
    )


if __name__ == "__main__":
    asyncio.run(_run(ApiSettings().database_url))
