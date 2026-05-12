"""Standalone EventsEye global seeder for manual/admin runs."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from loguru import logger

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from db.crud import upsert_event  # noqa: E402
from db.database import AsyncSessionLocal, init_db  # noqa: E402
from ingestion.scraper_eventseye import ScraperEventsEye  # noqa: E402


async def run_eventseye_seed() -> dict:
    await init_db()
    connector = ScraperEventsEye()
    events = await connector.fetch()
    inserted = 0

    async with AsyncSessionLocal() as db:
        for ev in events:
            ok = await upsert_event(db, ev)
            if ok:
                inserted += 1

    result = {
        "source": "EventsEye",
        "fetched": len(events),
        "inserted": inserted,
    }
    logger.info(f"EventsEye seed complete: {result}")
    return result


if __name__ == "__main__":
    summary = asyncio.run(run_eventseye_seed())
    print(summary)
