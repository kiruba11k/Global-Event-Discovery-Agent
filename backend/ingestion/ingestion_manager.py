"""
ingestion/ingestion_manager.py

FIX: every optional connector import is wrapped in try/except ImportError.
If ticketmaster.py / eventbrite.py / meetup.py / luma.py are missing,
the app still starts and the missing connector is simply excluded.

Real-time search uses ticketmaster_realtime.py / eventbrite_realtime.py /
predicthq_realtime.py instead — those are NOT imported here.
"""
from datetime import date
from loguru import logger

from db.database import AsyncSessionLocal
from db.crud import batch_upsert_events, count_events, count_by_source

try:
    from db.crud import purge_past_events
except ImportError:
    async def purge_past_events(db, grace_days=30): return 0

# ── Always-required connectors ─────────────────────────────────────
from ingestion.seed_events import SeedConnector

# ── Scrapers — wrap each in try/except ────────────────────────────

try:
    from ingestion.scraper_eventseye import ScraperEventsEye
    _HAS_EVENTSEYE = True
except ImportError:
    logger.warning("ingestion_manager: scraper_eventseye not found — skipped")
    _HAS_EVENTSEYE = False

try:
    from ingestion.scraper_wikipedia_trade import ScraperWikipediaTrades
    _HAS_WIKI = True
except ImportError:
    logger.warning("ingestion_manager: scraper_wikipedia_trade not found — skipped")
    _HAS_WIKI = False

try:
    from ingestion.scraper_10times import Scraper10Times
    _HAS_10TIMES = True
except ImportError:
    logger.warning("ingestion_manager: scraper_10times not found — skipped")
    _HAS_10TIMES = False

try:
    from ingestion.scraper_conferencealerts import ScraperConferenceAlerts
    _HAS_CA = True
except ImportError:
    logger.warning("ingestion_manager: scraper_conferencealerts not found — skipped")
    _HAS_CA = False

try:
    from ingestion.scraper_allconferences import ScraperAllConferences, ScraperConfex
    _HAS_ALL = True
except ImportError:
    logger.warning("ingestion_manager: scraper_allconferences not found — skipped")
    _HAS_ALL = False

try:
    from ingestion.scraper_techcrunch import ScraperTechCrunch
    _HAS_TC = True
except ImportError:
    logger.warning("ingestion_manager: scraper_techcrunch not found — skipped")
    _HAS_TC = False

try:
    from ingestion.scraper_saceos_myceb import ScraperSACEOS, ScraperMyCEB
    _HAS_SACEOS = True
except ImportError:
    try:
        from ingestion.scraper_mice_directories import ScraperSACEOS, ScraperMyCEB
        _HAS_SACEOS = True
    except ImportError:
        logger.warning("ingestion_manager: scraper_saceos_myceb not found — skipped")
        _HAS_SACEOS = False

# ── API-based connectors — all optional ───────────────────────────

try:
    from ingestion.ticketmaster import TicketmasterConnector
    _HAS_TM = True
except ImportError:
    logger.warning(
        "ingestion_manager: ingestion/ticketmaster.py not found — "
        "background Ticketmaster seeding skipped. "
        "Real-time search still uses ticketmaster_realtime.py."
    )
    _HAS_TM = False

try:
    from ingestion.eventbrite import EventbriteConnector
    _HAS_EB = True
except ImportError:
    logger.warning(
        "ingestion_manager: ingestion/eventbrite.py not found — "
        "background Eventbrite seeding skipped. "
        "Real-time search still uses eventbrite_realtime.py."
    )
    _HAS_EB = False

try:
    from ingestion.meetup import MeetupConnector
    _HAS_MEETUP = True
except ImportError:
    logger.warning("ingestion_manager: ingestion/meetup.py not found — skipped")
    _HAS_MEETUP = False

try:
    from ingestion.luma import LumaConnector
    _HAS_LUMA = True
except ImportError:
    logger.warning("ingestion_manager: ingestion/luma.py not found — skipped")
    _HAS_LUMA = False


# ── Build connector list from whatever is available ───────────────

def _build_connectors() -> list:
    c = [SeedConnector]
    if _HAS_EVENTSEYE:  c.append(ScraperEventsEye)
    if _HAS_WIKI:       c.append(ScraperWikipediaTrades)
    if _HAS_10TIMES:    c.append(Scraper10Times)
    if _HAS_CA:         c.append(ScraperConferenceAlerts)
    if _HAS_ALL:        c.extend([ScraperAllConferences, ScraperConfex])
    if _HAS_TC:         c.append(ScraperTechCrunch)
    if _HAS_SACEOS:     c.extend([ScraperSACEOS, ScraperMyCEB])
    if _HAS_TM:         c.append(TicketmasterConnector)
    if _HAS_EB:         c.append(EventbriteConnector)
    if _HAS_MEETUP:     c.append(MeetupConnector)
    if _HAS_LUMA:       c.append(LumaConnector)
    return c


ALL_CONNECTORS = _build_connectors()
SEED_ONLY      = [SeedConnector]
FAST_CONNECTORS = [c for c in [
    SeedConnector,
    ScraperTechCrunch if _HAS_TC else None,
    MeetupConnector   if _HAS_MEETUP else None,
    LumaConnector     if _HAS_LUMA else None,
] if c is not None]

logger.info(
    f"ingestion_manager: {len(ALL_CONNECTORS)} connectors active — "
    + ", ".join(c.__name__ if hasattr(c, '__name__') else str(c) for c in ALL_CONNECTORS)
)


# ── Core ingestion runner ─────────────────────────────────────────

async def run_ingestion(
    connectors=None,
    do_purge: bool = True,
    skip_past: bool = True,
) -> dict:
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
        if do_purge:
            try:
                purged = await purge_past_events(db, grace_days=30)
                stats["purged"] = purged
            except Exception as e:
                logger.warning(f"purge_past_events: {e}")

        try:
            before = await count_events(db)
        except Exception:
            before = 0
        stats["events_before_run"] = before

        for connector_class in connectors:
            connector = connector_class()
            source    = getattr(connector, "name", connector_class.__name__)
            try:
                events   = await connector.run()
                fetched  = len(events)
                stats["total_fetched"] += fetched

                inserted, skipped = await batch_upsert_events(
                    db, events, skip_past=skip_past
                )
                stats["total_inserted"] += inserted
                stats["total_skipped"]  += skipped
                stats["by_source"][source] = {
                    "fetched": fetched, "inserted": inserted, "skipped": skipped,
                }
                if fetched:
                    logger.info(
                        f"[{source:<26}] fetched={fetched:<5} "
                        f"inserted={inserted:<5} skipped={skipped}"
                    )
                else:
                    logger.debug(f"[{source}] fetched=0")

            except Exception as exc:
                msg = f"[{source}] {exc}"
                logger.error(msg)
                stats["errors"].append(msg)
                stats["by_source"][source] = {"error": str(exc)}

        try:
            stats["total_in_db"] = await count_events(db)
            stats["breakdown"]   = await count_by_source(db)
        except Exception:
            pass

    net = stats.get("total_in_db", 0) - before
    logger.info(
        f"Ingestion done — "
        f"fetched={stats['total_fetched']} "
        f"inserted={stats['total_inserted']} "
        f"total_in_db={stats.get('total_in_db', '?')} "
        f"(net +{net})"
    )
    return stats


async def run_seed_only() -> dict:
    return await run_ingestion(connectors=SEED_ONLY, do_purge=False, skip_past=False)


async def run_fast() -> dict:
    return await run_ingestion(connectors=FAST_CONNECTORS, do_purge=False)


async def run_deep() -> dict:
    return await run_ingestion(connectors=ALL_CONNECTORS, do_purge=True)
