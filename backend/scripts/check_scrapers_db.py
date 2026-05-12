"""Runtime health check for all scraper connectors + DB upsert pipeline.

Usage:
  python scripts/check_scrapers_db.py

This script uses the *current* DATABASE_URL from env/.env via config.py.
So on Render/Neon it validates both scraping and persistence path end-to-end.
"""
import asyncio
from dataclasses import dataclass

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from db.database import init_db, AsyncSessionLocal, DATABASE_URL
from db.crud import batch_upsert_events
from ingestion.scraper_10times import Scraper10Times
from ingestion.scraper_allconferences import ScraperAllConferences, ScraperConfex
from ingestion.scraper_conferencealerts import ScraperConferenceAlerts
from ingestion.scraper_eventseye import ScraperEventsEye as ScraperEventsEyeLegacy
from ingestion.scraper_mice_directories import (
    ScraperEventsEye as ScraperEventsEyeDirectory,
    ScraperSACEOS as ScraperSACEOSDirectory,
    ScraperMyCEB as ScraperMyCEBDirectory,
)
from ingestion.scraper_saceos_myceb import (
    ScraperSACEOS as ScraperSACEOSLegacy,
    ScraperMyCEB as ScraperMyCEBLegacy,
)
from ingestion.scraper_techcrunch import ScraperTechCrunch
from ingestion.scraper_wikipedia_trade import ScraperWikipediaTrades


@dataclass
class CheckResult:
    source: str
    fetched: int = 0
    inserted: int = 0
    skipped: int = 0
    error: str = ""


async def main() -> None:
    print(f"DATABASE_URL: {DATABASE_URL[:90]}...")

    scrapers = [
        Scraper10Times(),
        ScraperAllConferences(),
        ScraperConfex(),
        ScraperConferenceAlerts(),
        ScraperEventsEyeLegacy(),
        ScraperEventsEyeDirectory(),
        ScraperSACEOSDirectory(),
        ScraperMyCEBDirectory(),
        ScraperSACEOSLegacy(),
        ScraperMyCEBLegacy(),
        ScraperTechCrunch(),
        ScraperWikipediaTrades(),
    ]

    await init_db()
    results: list[CheckResult] = []

    async with AsyncSessionLocal() as db:
        for scraper in scrapers:
            result = CheckResult(source=scraper.name)
            try:
                events = await scraper.run()
                result.fetched = len(events)
                inserted, skipped = await batch_upsert_events(db, events, skip_past=True)
                result.inserted = inserted
                result.skipped = skipped
            except Exception as exc:
                result.error = str(exc)
            results.append(result)

    print("\n=== SCRAPER + DB CHECK SUMMARY ===")
    for res in results:
        if res.error:
            print(f"{res.source:22} ERROR: {res.error}")
        else:
            print(
                f"{res.source:22} fetched={res.fetched:4} inserted={res.inserted:4} skipped={res.skipped:4}"
            )


if __name__ == "__main__":
    asyncio.run(main())
