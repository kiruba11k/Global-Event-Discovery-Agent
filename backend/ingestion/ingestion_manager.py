"""
Ingestion Manager — runs all connectors in sequence and upserts to DB.
Includes Wikipedia + AllConferences + Confex for ~5000-event target.

Free-tier strategy:
  - Connectors run in sequence to stay within 512MB RAM
  - Scrapers with delays to be respectful to sites
  - New events are deduped via dedup_hash (MD5 of name|date|city)
  - Target: 5,000+ events in DB covering next 6 months globally
"""
import asyncio
from typing import List
from loguru import logger

from db.database import AsyncSessionLocal
from db.crud import upsert_event, count_events, purge_past_events
from ingestion.seed_events import SeedConnector
from ingestion.ticketmaster import TicketmasterConnector
from ingestion.eventbrite import EventbriteConnector
from ingestion.meetup import MeetupConnector
from ingestion.luma import LumaConnector
from ingestion.scraper_10times import Scraper10Times
from ingestion.scraper_conferencealerts import ScraperConferenceAlerts
from ingestion.scraper_techcrunch import ScraperTechCrunch
from ingestion.scraper_wikipedia_trade import ScraperWikipediaTrades
from ingestion.scraper_allconferences import ScraperAllConferences, ScraperConfex


# Ordered: seed first (always fast), then APIs, then scrapers
ALL_CONNECTORS = [
    SeedConnector,           # 35 curated events, always runs
    TicketmasterConnector,   # API — 5000 req/day free
    EventbriteConnector,     # API — 2000 req/hr free
    MeetupConnector,         # GraphQL — no key needed
    LumaConnector,           # API — free tier
    ScraperWikipediaTrades,  # Wikipedia — ~600-800 global trade fairs
    ScraperAllConferences,   # allconferences.com — ~300 events
    ScraperConfex,           # confex.com — ~200 events
    Scraper10Times,          # 10times.com — ~200 events
    ScraperConferenceAlerts, # conferencealerts.com — ~200 events
    ScraperTechCrunch,       # TechCrunch flagship events
]

# Lightweight connectors only — no heavy scrapers
FAST_CONNECTORS = [
    SeedConnector,
    MeetupConnector,
    LumaConnector,
]


async def run_ingestion(connectors=None) -> dict:
    """Run all (or specified) connectors and store results."""
    if connectors is None:
        connectors = ALL_CONNECTORS

    stats = {"total_fetched": 0, "total_saved": 0, "errors": []}

    async with AsyncSessionLocal() as db:
        # Purge events that have already passed — keep DB lean
        purged = await purge_past_events(db)
        if purged:
            logger.info(f"Purged {purged} past events from DB.")

        for connector_class in connectors:
            connector = connector_class()
            try:
                events = await connector.run()
                stats["total_fetched"] += len(events)

                saved = 0
                for event in events:
                    ok = await upsert_event(db, event)
                    if ok:
                        saved += 1

                stats["total_saved"] += saved
                logger.info(f"[{connector.name}] Saved {saved}/{len(events)} events.")

            except Exception as e:
                msg = f"[{connector.name}] Error: {e}"
                logger.error(msg)
                stats["errors"].append(msg)

        total_in_db = await count_events(db)
        stats["total_in_db"] = total_in_db

    logger.info(f"Ingestion complete. DB now has {stats['total_in_db']} events.")
    return stats


async def run_seed_only() -> dict:
    """Quick seed with curated events only — for fast startup."""
    return await run_ingestion(connectors=[SeedConnector])


async def run_fast() -> dict:
    """Fast refresh — seed + APIs only, no heavy scrapers. Good for frequent runs."""
    return await run_ingestion(connectors=FAST_CONNECTORS)
