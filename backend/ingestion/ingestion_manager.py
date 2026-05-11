"""
Ingestion Manager — fixed version.

Root-cause fixes vs old version:
  1. Uses batch_upsert_events() instead of per-event upsert → faster + accurate counts
  2. Skips events with start_date < today BEFORE hitting the DB
  3. purge_past_events() is NOT called during seed-only runs
  4. purge_past_events() uses a 7-day grace window + never deletes Seed events
  5. Stats now show accurate inserted vs duplicate-skipped counts

Daily scraping coverage:
  Seed          →  80+ curated events (guaranteed baseline, never purged)
  Ticketmaster  →  300+ via free API
  Eventbrite    →  800+ via expanded 30-query × 16-country matrix
  Meetup        →  200+ via GraphQL (no key)
  Luma          →  150+ via free API
  EventsEye     →  800+ global trade shows (22 categories + 20 countries)
  Wikipedia     →  700+ trade fair list
  SACEOS        →  80+  Singapore official MICE
  MyCEB         →  80+  Malaysia official MICE
  10Times       →  200+
  ConferenceAlerts → 200+
  AllConferences → 300+
  Confex        →  200+
  TechCrunch    →  20+
  ─────────────────────────────────
  TARGET        →  4,100+ unique events (5,000+ with API keys)
"""
import asyncio
from datetime import date
from typing import List, Optional
from loguru import logger

from db.database import AsyncSessionLocal
from db.crud import batch_upsert_events, count_events, purge_past_events
from ingestion.seed_events import SeedConnector
from ingestion.ticketmaster import TicketmasterConnector
from ingestion.eventbrite import EventbriteConnector
from ingestion.meetup import MeetupConnector
from ingestion.luma import LumaConnector
from ingestion.scraper_eventseye import ScraperEventsEye
from ingestion.scraper_wikipedia_trade import ScraperWikipediaTrades
from ingestion.scraper_saceos_myceb import ScraperSACEOS, ScraperMyCEB
from ingestion.scraper_10times import Scraper10Times
from ingestion.scraper_conferencealerts import ScraperConferenceAlerts
from ingestion.scraper_allconferences import ScraperAllConferences, ScraperConfex
from ingestion.scraper_techcrunch import ScraperTechCrunch


ALL_CONNECTORS = [
    SeedConnector,            # always first — guaranteed baseline
    MeetupConnector,          # free GraphQL API
    LumaConnector,            # free API
    TicketmasterConnector,    # free tier API
    EventbriteConnector,      # free tier API (expanded)
    ScraperEventsEye,         # largest free scrape source
    ScraperWikipediaTrades,   # Wikipedia trade fair lists
    ScraperAllConferences,    # allconferences.com
    ScraperConfex,            # confex.com
    Scraper10Times,           # 10times.com
    ScraperConferenceAlerts,  # conferencealerts.com
    ScraperSACEOS,            # Singapore official MICE
    ScraperMyCEB,             # Malaysia official MICE
    ScraperTechCrunch,        # TechCrunch flagship
]

FAST_CONNECTORS = [SeedConnector, MeetupConnector, LumaConnector]
SEED_ONLY       = [SeedConnector]


async def run_ingestion(
    connectors=None,
    do_purge: bool = True,
    skip_past: bool = True,
) -> dict:
    """
    Run connectors, insert new events, return detailed stats.

    Args:
        connectors: list of connector classes to run (default: ALL_CONNECTORS)
        do_purge:   if True, purge events older than 7 days first
        skip_past:  if True, silently skip events whose start_date < today
    """
    if connectors is None:
        connectors = ALL_CONNECTORS

    today = date.today().isoformat()
    stats = {
        "total_fetched":   0,
        "total_inserted":  0,   # actually new rows
        "total_skipped":   0,   # past-dated or duplicate
        "errors":          [],
        "by_source":       {},
        "total_in_db":     0,
        "run_date":        today,
    }

    async with AsyncSessionLocal() as db:

        # ── Purge stale past events (never purges Seed events) ──────
        if do_purge:
            purged = await purge_past_events(db, grace_days=7)
            stats["purged"] = purged

        # ── Run each connector ──────────────────────────────────────
        for connector_class in connectors:
            connector = connector_class()
            source    = connector.name
            try:
                events = await connector.run()
                fetched = len(events)
                stats["total_fetched"] += fetched

                inserted, skipped = await batch_upsert_events(
                    db, events, skip_past=skip_past
                )

                stats["total_inserted"] += inserted
                stats["total_skipped"]  += skipped
                stats["by_source"][source] = {
                    "fetched":  fetched,
                    "inserted": inserted,
                    "skipped":  skipped,
                }
                logger.info(
                    f"[{source}] fetched={fetched} "
                    f"inserted={inserted} skipped(past/dup)={skipped}"
                )

            except Exception as e:
                msg = f"[{source}] Error: {e}"
                logger.error(msg)
                stats["errors"].append(msg)
                stats["by_source"][source] = {"error": str(e)}

        stats["total_in_db"] = await count_events(db)

    logger.info(
        f"Ingestion complete — "
        f"fetched={stats['total_fetched']} "
        f"inserted={stats['total_inserted']} "
        f"total_in_db={stats['total_in_db']}"
    )
    return stats


async def run_seed_only() -> dict:
    """
    Insert curated seed events only.
    Never purges existing events.
    Fast — completes in < 1 second.
    """
    return await run_ingestion(
        connectors=SEED_ONLY,
        do_purge=False,   # ← critical: do NOT purge on seed runs
        skip_past=False,  # ← seed events might have near-past dates; keep them
    )


async def run_fast() -> dict:
    """Fast refresh — seed + free APIs, no heavy scrapers."""
    return await run_ingestion(connectors=FAST_CONNECTORS, do_purge=True)


async def run_deep() -> dict:
    """Full refresh — all connectors."""
    return await run_ingestion(connectors=ALL_CONNECTORS, do_purge=True)
