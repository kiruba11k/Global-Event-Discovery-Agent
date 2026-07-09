"""
scripts/backfill_embeddings.py - bulk-embed all events into pgvector.

Run once after enabling pgvector (and after big ingestion runs):

    cd backend && python -m scripts.backfill_embeddings

Safe to re-run: only events with embedding IS NULL are processed.
"""
import asyncio

from loguru import logger
from sqlalchemy import select, text

from db.database import AsyncSessionLocal
from models.event import EventORM
from relevance import pgvector_store

BATCH = 128


async def main() -> None:
    if not pgvector_store.is_active():
        logger.error("pgvector inactive (need Postgres database_url + an embedding provider)")
        return
    async with AsyncSessionLocal() as db:
        if not await pgvector_store.ensure_schema(db):
            return
        total = 0
        while True:
            ids = (await db.execute(text(
                "SELECT id FROM events WHERE embedding IS NULL LIMIT :n"
            ), {"n": BATCH})).scalars().all()
            if not ids:
                break
            events = (await db.execute(
                select(EventORM).where(EventORM.id.in_(list(ids)))
            )).scalars().all()
            done = await pgvector_store.embed_missing(db, events, limit=BATCH)
            if done == 0:
                break
            total += done
            logger.info(f"backfill: {total} embedded so far")
        logger.info(f"backfill complete: {total} events embedded")


if __name__ == "__main__":
    asyncio.run(main())
