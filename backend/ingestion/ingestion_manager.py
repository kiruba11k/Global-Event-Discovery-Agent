"""
Ingestion Manager — runs all connectors in sequence and upserts to DB.
"""
import asyncio
from typing import List
from loguru import logger

from db.database import AsyncSessionLocal
from db.crud import upsert_event, count_events
from ingestion.seed_events import SeedConnector
from ingestion.ticketmaster import TicketmasterConnector
from ingestion.eventbrite import EventbriteConnector
from ingestion.meetup import MeetupConnector
from ingestion.luma import LumaConnector
from ingestion.scraper_10times import Scraper10Times
from ingestion.scraper_conferencealerts import ScraperConferenceAlerts
from ingestion.scraper_techcrunch import ScraperTechCrunch


ALL_CONNECTORS = [
    SeedConnector,
    TicketmasterConnector,
    EventbriteConnector,
    MeetupConnector,
    LumaConnector,
    Scraper10Times,
    ScraperConferenceAlerts,
    ScraperTechCrunch,
]


async def run_ingestion(connectors=None) -> dict:
    """Run all (or specified) connectors and store results."""
    if connectors is None:
        connectors = ALL_CONNECTORS

    stats = {"total_fetched": 0, "total_saved": 0, "errors": []}

    async with AsyncSessionLocal() as db:
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
