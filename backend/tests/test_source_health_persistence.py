"""
Integration test: source_health circuit-breaker state must survive a
simulated process restart via DB persistence.

This is the fix for a real production issue: Render's free tier spins
idle instances down, wiping any purely in-memory circuit breaker. A
permanently-dead endpoint (e.g. Eventbrite's retired public search API,
which 404s on every call) was being re-probed on every cold start
instead of staying suppressed for its cool-off window.

Needs Postgres (TEST_PG_DSN); skips cleanly otherwise, same convention
as test_pgvector_integration.py.
"""
import asyncio
import os

import pytest

TEST_DSN = os.environ.get("TEST_PG_DSN", "")

pytestmark = pytest.mark.skipif(
    not TEST_DSN, reason="TEST_PG_DSN not set - needs Postgres"
)


def test_circuit_breaker_survives_restart():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import db.database as dbmod
    import ingestion.source_health as sh

    async def run():
        eng = create_async_engine(TEST_DSN)
        SL = async_sessionmaker(eng, expire_on_commit=False)
        async with eng.begin() as conn:
            await conn.execute(text("DROP TABLE IF EXISTS source_health"))
            await sh.ensure_table(conn)

        dbmod.AsyncSessionLocal = SL

        # Fresh registry per test run to avoid cross-test state leakage
        sh.source_health = sh.SourceHealthRegistry()

        # A permanently-dead endpoint fails with 404 ("gone")
        sh.source_health.record_failure("Eventbrite", status=404, detail="endpoint retired")
        await asyncio.sleep(0.3)  # let the fire-and-forget persist land

        async with eng.connect() as conn:
            row = (await conn.execute(text(
                "SELECT open_until, reason FROM source_health WHERE source='Eventbrite'"
            ))).fetchone()
        assert row is not None and row[0] > 0, "failure state was not persisted"

        # Simulate a process restart: brand new registry, nothing in memory
        sh.source_health = sh.SourceHealthRegistry()
        assert sh.source_health.is_available("Eventbrite") is True  # optimistic before load

        await sh.load_from_db(SL)
        assert sh.source_health.is_available("Eventbrite") is False, \
            "circuit breaker did not survive simulated restart"

        # Recovery clears the circuit and persists that too
        sh.source_health.record_success("Eventbrite")
        await asyncio.sleep(0.3)
        async with eng.connect() as conn:
            row2 = (await conn.execute(text(
                "SELECT open_until FROM source_health WHERE source='Eventbrite'"
            ))).fetchone()
        assert row2[0] == 0.0, "recovery was not persisted"

        await eng.dispose()

    asyncio.run(run())
