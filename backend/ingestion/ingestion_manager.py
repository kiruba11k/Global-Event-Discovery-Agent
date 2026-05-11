"""
Ingestion Manager — all connectors including new sources.

Target: 5,000+ global events in DB, refreshed daily.

Source coverage:
  Seed          →  35  curated flagship events (always fast)
  Ticketmaster  →  300 events via free API (5,000 req/day)
  Eventbrite    →  800 events via expanded API (20 industries × 16 countries)
  Meetup        →  200 events via GraphQL (no key needed)
  Luma          →  150 events via API (free tier)
  EventsEye     →  800 events scraped (22 categories + 20 country pages)
  Wikipedia     →  700 events scraped (trade fairs list)
  SACEOS        →  80  Singapore official MICE events
  MyCEB         →  80  Malaysia official MICE events
  10Times       →  200 events scraped
  ConferenceAlerts → 200 events scraped
  AllConferences → 300 events scraped
  Confex        →  200 events scraped
  TechCrunch    →  20  flagship tech events
  ──────────────────────────────────────────────────────────
  TOTAL TARGET  → 4,065+ events (5,000+ with API keys active)

Deduplication: MD5 hash of (name.lower | start_date | city.lower)
               applied via ON CONFLICT DO NOTHING in SQLite/Postgres
"""
import asyncio
from typing import List
from loguru import logger

from db.database import AsyncSessionLocal
from db.crud import upsert_event, count_events, purge_past_events
from ingestion.seed_events import SeedConnector
from ingestion.ticketmaster import TicketmasterConnector
from ingestion.eventbrite import EventbriteConnector           # use expanded version
from ingestion.meetup import MeetupConnector
from ingestion.luma import LumaConnector
from ingestion.scraper_eventseye import ScraperEventsEye
from ingestion.scraper_wikipedia_trade import ScraperWikipediaTrades
from ingestion.scraper_saceos_myceb import ScraperSACEOS, ScraperMyCEB
from ingestion.scraper_10times import Scraper10Times
from ingestion.scraper_conferencealerts import ScraperConferenceAlerts
from ingestion.scraper_allconferences import ScraperAllConferences, ScraperConfex
from ingestion.scraper_techcrunch import ScraperTechCrunch


# ── Full connector list — ordered for optimal rate limit usage ──
ALL_CONNECTORS = [
    # 1. Always runs first — zero latency, zero network calls
    SeedConnector,

    # 2. Free APIs (fastest, most reliable)
    MeetupConnector,
    LumaConnector,

    # 3. Paid free-tier APIs (need env vars)
    TicketmasterConnector,
    EventbriteConnector,

    # 4. Scrapers — largest sources first
    ScraperEventsEye,        # 800+ global trade shows across all industries
    ScraperWikipediaTrades,  # 700+ from Wikipedia trade fair lists
    ScraperAllConferences,   # 300+ from AllConferences.com
    ScraperConfex,           # 200+ from Confex.com
    Scraper10Times,          # 200+ from 10times.com
    ScraperConferenceAlerts, # 200+ from ConferenceAlerts.com

    # 5. Official MICE directories (SE Asia)
    ScraperSACEOS,           # 80+ Singapore official events
    ScraperMyCEB,            # 80+ Malaysia official events

    # 6. Niche high-quality sources
    ScraperTechCrunch,       # Flagship tech events
]

# For quick restarts — skip heavy scrapers
FAST_CONNECTORS = [
    SeedConnector,
    MeetupConnector,
    LumaConnector,
    ScraperTechCrunch,
]

# For a thorough weekly deep-scan
DEEP_CONNECTORS = ALL_CONNECTORS


async def run_ingestion(connectors=None) -> dict:
    """Run connectors in sequence, upsert events, return stats."""
    if connectors is None:
        connectors = ALL_CONNECTORS

    stats = {
        "total_fetched": 0,
        "total_saved":   0,
        "errors":        [],
        "by_source":     {},
    }

    async with AsyncSessionLocal() as db:
        # Purge events that have already passed — keep DB lean
        purged = await purge_past_events(db)
        if purged:
            logger.info(f"Purged {purged} past events.")

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
                stats["by_source"][connector.name] = {"fetched": len(events), "saved": saved}
                logger.info(f"[{connector.name}] {saved}/{len(events)} saved.")

            except Exception as e:
                msg = f"[{connector.name}] Error: {e}"
                logger.error(msg)
                stats["errors"].append(msg)
                stats["by_source"][connector.name] = {"fetched": 0, "saved": 0, "error": str(e)}

        total_in_db = await count_events(db)
        stats["total_in_db"] = total_in_db

    logger.info(
        f"Ingestion done — fetched={stats['total_fetched']} "
        f"saved={stats['total_saved']} "
        f"total_in_db={stats['total_in_db']}"
    )
    return stats


async def run_seed_only() -> dict:
    """Instant seed — for first startup with empty DB."""
    return await run_ingestion(connectors=[SeedConnector])


async def run_fast() -> dict:
    """Fast refresh — seed + APIs only, no heavy scrapers."""
    return await run_ingestion(connectors=FAST_CONNECTORS)


async def run_deep() -> dict:
    """Deep scan — all connectors. Run weekly via cron."""
    return await run_ingestion(connectors=DEEP_CONNECTORS)
