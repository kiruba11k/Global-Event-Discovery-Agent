"""Standalone EventsEye global seeder for manual/admin runs."""
from __future__ import annotations

import asyncio
import sys
from datetime import date
from pathlib import Path

from loguru import logger

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from db.crud import upsert_event  # noqa: E402
from db.database import AsyncSessionLocal, init_db  # noqa: E402
from ingestion.scraper_eventseye import ScraperEventsEye  # noqa: E402


async def run_eventseye_seed(dry_run: bool = False) -> dict:
    await init_db()
    connector = ScraperEventsEye()
    events = await connector.fetch()
    today = date.today().isoformat()
    upcoming_events = [e for e in events if getattr(e, "start_date", "") and e.start_date >= today]
    inserted = 0

    if not dry_run:
        async with AsyncSessionLocal() as db:
            for ev in upcoming_events:
                ok = await upsert_event(db, ev)
                if ok:
                    inserted += 1

    result = {
        "source": "EventsEye",
        "fetched": len(events),
        "upcoming_events": len(upcoming_events),
        "inserted": inserted,
        "dry_run": dry_run,
    }
    logger.info(f"EventsEye seed complete: {result}")
    return result


if __name__ == "__main__":
    summary = asyncio.run(run_eventseye_seed())
    print(summary)
