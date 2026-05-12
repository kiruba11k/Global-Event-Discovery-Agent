"""Standalone ConferenceAlerts advanced-search seeder."""
from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from db.crud import upsert_event  # noqa: E402
from db.database import AsyncSessionLocal, init_db  # noqa: E402
from ingestion.scraper_conferencealerts import ScraperConferenceAlerts  # noqa: E402


@dataclass(frozen=True)
class ConferenceAlertsSeedConfig:
    limit_events: int | None
    dry_run: bool


async def seed_database(events):
    await init_db()
    inserted = 0
    async with AsyncSessionLocal() as db:
        for e in events:
            created = await upsert_event(db, e)
            if created:
                inserted += 1
    return inserted


async def run_conferencealerts_seed(config: ConferenceAlertsSeedConfig) -> dict:
    started = datetime.now(UTC)
    scraper = ScraperConferenceAlerts()
    events = await scraper.fetch()

    if config.limit_events:
        events = events[: config.limit_events]

    saved = 0
    if not config.dry_run:
        saved = await seed_database(events)

    result = {
        "source": "conferencealerts",
        "started_at": started.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "parsed_events": len(events),
        "inserted_events": saved,
        "dry_run": config.dry_run,
    }
    logger.info(f"ConferenceAlerts seed result: {result}")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed ConferenceAlerts advanced-search events into DB.")
    parser.add_argument("--limit-events", type=int, default=1000)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


async def _main():
    args = parse_args()
    config = ConferenceAlertsSeedConfig(limit_events=args.limit_events, dry_run=args.dry_run)
    await run_conferencealerts_seed(config)


if __name__ == "__main__":
    asyncio.run(_main())
