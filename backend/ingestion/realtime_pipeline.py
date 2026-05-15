"""
ingestion/realtime_pipeline.py  —  Real-time event discovery orchestrator (v5)

Changes from v4:
  - Uses async build_queries() (Groq LLM keyword extraction)
  - _noop() defined at top (no more asyncio.coroutine crash)
  - Individual _safe_run() wrappers with per-source 20s timeouts
  - Detailed per-source logging
"""
from __future__ import annotations

import asyncio
from datetime import date

from loguru import logger
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from db.crud import batch_upsert_events
from ingestion.icp_query_builder import build_queries
from ingestion.serpapi_events import run_serpapi_queries
from ingestion.ticketmaster_realtime import run_ticketmaster_queries
from ingestion.eventbrite_realtime import run_eventbrite_queries
from ingestion.predicthq_realtime import run_predicthq_queries
from models.event import EventCreate, EventORM
from models.icp_profile import ICPProfile

settings = get_settings()


async def _noop() -> list:
    """Placeholder for APIs with missing keys. Always defined first."""
    return []


async def _safe_run(coro, source_name: str) -> list:
    """
    Run a coroutine with individual 20s timeout.
    Returns [] on failure — never kills the overall gather.
    """
    try:
        result = await asyncio.wait_for(coro, timeout=20.0)
        return result or []
    except asyncio.TimeoutError:
        logger.warning(f"{source_name}: timed out (20s)")
        return []
    except Exception as exc:
        logger.warning(f"{source_name}: {exc}")
        return []


async def fetch_realtime_candidates(
    db:      AsyncSession,
    profile: ICPProfile,
) -> list[EventORM]:
    """
    Orchestrate all real-time APIs + DB for a given ICP profile.

    1. Groq LLM builds targeted queries from ALL ICP form fields
    2. SerpAPI + Ticketmaster + Eventbrite + PredictHQ fire in parallel
    3. New events upserted to DB
    4. DB queried for all matching events (existing + new)
    5. Returns EventORM list for scoring
    """
    today     = date.today().isoformat()
    date_from = profile.date_from or today
    date_to   = profile.date_to   or "2030-12-31"

    # ── Step 1: Groq LLM query generation ──────────────────────────
    query_bundle = await build_queries(
        industries   = profile.target_industries   or [],
        geographies  = profile.target_geographies  or [],
        personas     = profile.target_personas     or [],
        event_types  = profile.preferred_event_types or [],
        company_desc = profile.company_description  or "",
        date_from    = date_from,
        date_to      = date_to,
    )

    # ── Step 2: API key status ──────────────────────────────────────
    phq_key = getattr(settings, "predicthq_key", "")
    api_status = {
        "SerpAPI":      bool(settings.serpapi_key),
        "Ticketmaster": bool(settings.ticketmaster_key),
        "Eventbrite":   bool(settings.eventbrite_token),
        "PredictHQ":    bool(phq_key),
    }
    active  = [k for k, v in api_status.items() if v]
    missing = [k for k, v in api_status.items() if not v]

    logger.info(
        f"Real-time pipeline | company={profile.company_name!r} | "
        f"active_apis={active} | missing_keys={missing} | "
        f"keywords={query_bundle.keywords_used[:3]} | "
        f"queries: serp={len(query_bundle.serpapi)} "
        f"tm={len(query_bundle.ticketmaster)} "
        f"eb={len(query_bundle.eventbrite)} "
        f"phq={len(query_bundle.predicthq)}"
    )

    # ── Step 3: Fire all APIs in parallel ──────────────────────────
    serp_coro = (
        run_serpapi_queries(query_bundle.serpapi, settings.serpapi_key, date_from, date_to)
        if settings.serpapi_key and query_bundle.serpapi else _noop()
    )
    tm_coro = (
        run_ticketmaster_queries(query_bundle.ticketmaster, settings.ticketmaster_key, date_from, date_to)
        if settings.ticketmaster_key and query_bundle.ticketmaster else _noop()
    )
    eb_coro = (
        run_eventbrite_queries(query_bundle.eventbrite, settings.eventbrite_token, date_from, date_to)
        if settings.eventbrite_token and query_bundle.eventbrite else _noop()
    )
    phq_coro = (
        run_predicthq_queries(query_bundle.predicthq, phq_key, date_from, date_to)
        if phq_key and query_bundle.predicthq else _noop()
    )

    serp_events, tm_events, eb_events, phq_events = await asyncio.gather(
        _safe_run(serp_coro, "SerpAPI"),
        _safe_run(tm_coro,   "Ticketmaster"),
        _safe_run(eb_coro,   "Eventbrite"),
        _safe_run(phq_coro,  "PredictHQ"),
        return_exceptions=False,
    )

    # Log per-source results
    for src, evs in [("SerpAPI", serp_events), ("Ticketmaster", tm_events),
                     ("Eventbrite", eb_events), ("PredictHQ", phq_events)]:
        if evs:
            logger.info(f"  ✓ {src}: {len(evs)} events")
        elif api_status.get(src):
            logger.info(f"  ○ {src}: 0 events (API active but no results)")
        else:
            logger.debug(f"  — {src}: key not configured")

    # ── Step 4: Deduplicate across all sources ──────────────────────
    new_events: list[EventCreate] = []
    seen_hashes: set[str] = set()
    for evs in [serp_events, tm_events, eb_events, phq_events]:
        for ev in evs:
            if ev.dedup_hash not in seen_hashes:
                seen_hashes.add(ev.dedup_hash)
                new_events.append(ev)

    total_new = len(new_events)
    logger.info(f"Real-time: {total_new} unique events from {len(active)} APIs")

    # ── Step 5: Upsert to DB ────────────────────────────────────────
    if new_events:
        inserted, dupes = await batch_upsert_events(db, new_events, skip_past=True)
        logger.info(f"DB upsert: {inserted} new, {dupes} already existed")

    # ── Step 6: Query DB ────────────────────────────────────────────
    from ingestion.icp_query_builder import _expand_industry_terms

    stmt = select(EventORM).where(
        EventORM.start_date >= date_from,
        EventORM.start_date <= date_to,
    )

    is_global = any(
        g.lower().strip() in ("global", "worldwide", "international", "any")
        for g in (profile.target_geographies or [])
    )
    geo_filters = []
    if not is_global and profile.target_geographies:
        for geo in profile.target_geographies:
            for part in [geo] + (geo.split(" - ") if " - " in geo else []):
                part = part.strip()
                if len(part) > 1:
                    geo_filters.append(EventORM.country.ilike(f"%{part}%"))
                    geo_filters.append(EventORM.city.ilike(f"%{part}%"))
                    geo_filters.append(EventORM.event_cities.ilike(f"%{part}%"))
        if geo_filters:
            stmt = stmt.where(or_(*geo_filters))

    if profile.target_industries:
        expanded = _expand_industry_terms(profile.target_industries)
        ind_filters = []
        for term in expanded:
            ind_filters.append(EventORM.industry_tags.ilike(f"%{term}%"))
            ind_filters.append(EventORM.related_industries.ilike(f"%{term}%"))
            ind_filters.append(EventORM.description.ilike(f"%{term}%"))
            ind_filters.append(EventORM.name.ilike(f"%{term}%"))
        if ind_filters:
            stmt = stmt.where(or_(*ind_filters))

    result = await db.execute(stmt.limit(500))
    db_candidates = list(result.scalars().all())

    # Widen if too few results
    if len(db_candidates) < 10:
        stmt_wide = select(EventORM).where(
            EventORM.start_date >= date_from,
            EventORM.start_date <= date_to,
        )
        if geo_filters:
            stmt_wide = stmt_wide.where(or_(*geo_filters))
        result_wide = await db.execute(stmt_wide.limit(500))
        db_candidates = list(result_wide.scalars().all())
        logger.info(f"Widened DB query: {len(db_candidates)} candidates (no industry filter)")

    logger.info(
        f"Pipeline complete: {len(db_candidates)} scoring candidates "
        f"({total_new} new from APIs + existing DB)"
    )
    return db_candidates
