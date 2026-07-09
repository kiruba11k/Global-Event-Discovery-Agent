"""
Integration test for relevance/pgvector_store.py on a real Postgres.

Needs a Postgres with the pgvector extension available:

    export TEST_PG_DSN="postgresql+asyncpg://user:pass@localhost/testdb"
    pytest tests/test_pgvector_integration.py

Skipped automatically when TEST_PG_DSN is not set. Uses a deterministic
token-hash embedding provider so no model download / API key is needed -
the test exercises real schema migration, vector writes, HNSW index and
cosine ordering, not the embedding model itself.
"""
import asyncio
import hashlib
import os

import pytest

TEST_DSN = os.environ.get("TEST_PG_DSN", "")

pytestmark = pytest.mark.skipif(
    not TEST_DSN, reason="TEST_PG_DSN not set - needs Postgres with pgvector"
)


class _DeterministicProvider:
    """Bag-of-token random projections: shared tokens -> higher cosine."""
    name = "test-deterministic"

    def embed(self, texts):
        import numpy as np
        out = []
        for t in texts:
            v = np.zeros(384)
            for tok in t.lower().split():
                seed = int(hashlib.md5(tok.encode()).hexdigest()[:8], 16)
                v += np.random.RandomState(seed).randn(384)
            n = np.linalg.norm(v)
            out.append((v / n if n else v).tolist())
        return out


_EVENTS = [
    dict(id="ev-health", name="India Health Summit 2026",
         description="Healthcare technology and innovation attracting hospital CIOs and clinical IT leaders",
         industry_tags="healthcare, medtech, digital health", city="Bangalore", country="India",
         start_date="2026-08-21", end_date="2026-08-23"),
    dict(id="ev-mfg", name="India Manufacturing Summit 2026",
         description="Manufacturing technology automation and Industry 4.0 for plant operations",
         industry_tags="manufacturing, automation", city="Pune", country="India",
         start_date="2026-09-17", end_date="2026-09-18"),
    dict(id="ev-fin", name="Fintech Festival India 2026",
         description="Digital banking payments and financial technology innovation",
         industry_tags="fintech, payments, banking", city="Mumbai", country="India",
         start_date="2026-10-05", end_date="2026-10-06"),
    dict(id="ev-past", name="Old Health Expo 2020",
         description="Healthcare technology hospital innovation",
         industry_tags="healthcare", city="Delhi", country="India",
         start_date="2020-01-01", end_date="2020-01-02"),
]


class _Prof:
    buyer_description = "CISO at healthcare organisations hospital clinical security"
    company_description = "we sell security software to healthcare organisations"
    target_industries = ["Healthcare / Medtech"]
    target_personas = ["CISO"]
    extra_keywords = ["hospital", "clinical"]


def test_pgvector_end_to_end():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from models.event import Base, EventORM
    from relevance import pgvector_store

    pgvector_store._provider = _DeterministicProvider()
    pgvector_store._provider_resolved = True
    pgvector_store._schema_ready = False
    pgvector_store.settings.database_url = TEST_DSN     # force is_active() true
    pgvector_store.settings.pgvector_enabled = True      # off by default in production

    async def run():
        eng = create_async_engine(TEST_DSN)
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        SL = async_sessionmaker(eng, expire_on_commit=False)
        async with SL() as db:
            assert await pgvector_store.ensure_schema(db)

            evs = []
            for e in _EVENTS:
                orm = EventORM(dedup_hash=e["id"], source_platform="test",
                               source_url="https://x.test/" + e["id"], **e)
                db.add(orm)
                evs.append(orm)
            await db.commit()

            assert await pgvector_store.embed_missing(db, evs) == 4
            assert await pgvector_store.embed_missing(db, evs) == 0  # idempotent

            scores = await pgvector_store.semantic_scores(
                db, _Prof(), date_from="2026-01-01"
            )
            assert "ev-past" not in scores          # date filter works
            ranked = sorted(scores, key=lambda k: -scores[k])
            assert ranked[0] == "ev-health"          # healthcare ICP -> health event #1
            assert scores["ev-health"] > scores["ev-mfg"]
        await eng.dispose()

    asyncio.run(run())


def test_inert_on_sqlite():
    """pgvector must be a silent no-op on non-Postgres deployments."""
    from relevance import pgvector_store
    old = pgvector_store.settings.database_url
    try:
        pgvector_store.settings.database_url = "sqlite+aiosqlite:///./events.db"
        assert pgvector_store.is_active() is False
    finally:
        pgvector_store.settings.database_url = old
