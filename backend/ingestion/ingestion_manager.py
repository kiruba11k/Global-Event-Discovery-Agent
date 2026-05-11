"""
Ingestion Manager — v3 (final).

Critical fixes vs previous versions:
  1. run_seed_only() passes do_purge=False AND skip_past=False
     → seeds are never immediately deleted
  2. run_ingestion() defaults skip_past=True
     → events with start_date < today are silently dropped BEFORE DB write
     → they never accumulate as "past" events waiting to be purged
  3. do_purge=True uses 30-day grace (not 7) and never touches future events
  4. Per-source stats logged after every run
"""
from datetime import date
from typing import List, Optional
from loguru import logger

from db.database import AsyncSessionLocal
from db.crud import batch_upsert_events, count_events, purge_past_events, count_by_source
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
    SeedConnector,            # 53+ curated events — guaranteed baseline
    MeetupConnector,          # free, no key — 100-200 events/run
    LumaConnector,            # free API — 80-150 events/run
    TicketmasterConnector,    # needs TICKETMASTER_KEY
    EventbriteConnector,      # needs EVENTBRITE_TOKEN (fixed lat/lon search)
    ScraperWikipediaTrades,   # curated 30+ global events + dynamic scrape
    ScraperEventsEye,         # 25+ curated + dynamic scrape
    ScraperAllConferences,    # allconferences.com
    Scraper10Times,           # 10times.com (may 403, skip gracefully)
    ScraperConferenceAlerts,  # conferencealerts.com
    ScraperSACEOS,            # Singapore MICE official
    ScraperMyCEB,             # Malaysia MICE official
    ScraperTechCrunch,        # 6 flagship tech events
]

SEED_ONLY   = [SeedConnector]
FAST        = [SeedConnector, MeetupConnector, LumaConnector, ScraperTechCrunch]


async def run_ingestion(
    connectors=None,
    do_purge: bool = True,
    skip_past: bool = True,
) -> dict:
    """
    Run all connectors, persist new events, return detailed stats.

    Args:
        connectors:  list of connector classes (default ALL_CONNECTORS)
        do_purge:    delete events 30+ days old (default True)
        skip_past:   drop events with start_date < today before DB write (default True)
    """
    if connectors is None:
        connectors = ALL_CONNECTORS

    today = date.today().isoformat()
    stats = {
        "total_fetched":  0,
        "total_inserted": 0,
        "total_skipped":  0,
        "errors":         [],
        "by_source":      {},
        "total_in_db":    0,
        "run_date":       today,
    }

    async with AsyncSessionLocal() as db:

        # ── Optional purge of very old events ──────────────────
        # grace_days=30 means only events that ended 30+ days ago
        # AND whose start_date is also in the past are removed.
        # Seed events are never purged.
        if do_purge:
            purged = await purge_past_events(db, grace_days=30)
            stats["purged"] = purged

        before = await count_events(db)
        stats["events_before_run"] = before

        # ── Run each connector ──────────────────────────────────
        for connector_class in connectors:
            connector = connector_class()
            source    = connector.name
            try:
                events  = await connector.run()
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

                if fetched > 0:
                    logger.info(
                        f"[{source:<22}] "
                        f"fetched={fetched:<5} "
                        f"inserted={inserted:<5} "
                        f"skipped={skipped}"
                    )
                else:
                    logger.debug(f"[{source}] fetched=0")

            except Exception as e:
                msg = f"[{source}] {e}"
                logger.error(msg)
                stats["errors"].append(msg)
                stats["by_source"][source] = {"error": str(e)}

        stats["total_in_db"] = await count_events(db)
        by_src = await count_by_source(db)
        stats["breakdown"] = by_src

    logger.info(
        f"Ingestion complete — "
        f"fetched={stats['total_fetched']} "
        f"inserted={stats['total_inserted']} "
        f"total_in_db={stats['total_in_db']} "
        f"(+{stats['total_in_db'] - before} net new)"
    )
    for src, cnt in sorted(stats.get("breakdown", {}).items(), key=lambda x: -x[1]):
        logger.info(f"  {src:<22} {cnt:>5} events in DB")

    return stats


async def run_seed_only() -> dict:
    """
    Insert curated seed events — fast, no purge, keeps past-dated seeds.
    Call this ONLY when DB is completely empty.
    """
    return await run_ingestion(
        connectors=SEED_ONLY,
        do_purge=False,    # never purge on seed run
        skip_past=False,   # keep seeds even if dates are borderline
    )


async def run_fast() -> dict:
    """Quick refresh: seed + free APIs + TechCrunch. ~30 seconds."""
    return await run_ingestion(connectors=FAST, do_purge=False)


async def run_deep() -> dict:
    """Full deep scan — all connectors. Takes 3-10 minutes."""
    return await run_ingestion(connectors=ALL_CONNECTORS, do_purge=True)
