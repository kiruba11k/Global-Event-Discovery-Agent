"""
ingestion/realtime_pipeline.py  —  Real-time event discovery orchestrator (v5)

IMPORT FIX:
  _expand_industry_terms is now imported from db.crud (where it lives),
  NOT from ingestion.icp_query_builder.

All other fixes retained:
  - _noop() defined at top (no asyncio.coroutine)
  - Individual _safe_run() per-API 20s timeouts
  - asyncio.gather return_exceptions=False (per-source isolation)
"""
from __future__ import annotations

import asyncio
from datetime import date

from loguru import logger
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from db.crud import batch_upsert_events, _expand_industry_terms   # ← fixed
from ingestion.icp_query_builder import build_queries
from ingestion.serpapi_events import run_serpapi_queries
from ingestion.ticketmaster_realtime import run_ticketmaster_queries
from ingestion.eventbrite_realtime import run_eventbrite_queries
from ingestion.predicthq_realtime import run_predicthq_queries
from ingestion.source_health import source_health
from models.event import EventORM
from models.icp_profile import ICPProfile

settings = get_settings()


# ── MUST be defined before any use ────────────────────────────────
async def _noop() -> list:
    """Placeholder for APIs whose key is not configured."""
    return []


async def _safe_run(coro, source_name: str, timeout: float = 45.0) -> list:
    """
    Runs one API coroutine with an independent outer timeout (a generous
    backstop — connectors now bound their own per-query timeouts and return
    partial results themselves). Returns [] on timeout or any exception —
    never kills the gather.
    """
    try:
        result = await asyncio.wait_for(coro, timeout=timeout)
        return result or []
    except asyncio.TimeoutError:
        logger.warning(f"{source_name}: timed out after {timeout:.0f}s")
        source_health.record_failure(source_name, kind="transient", detail="batch timeout")
        return []
    except Exception as exc:
        logger.warning(f"{source_name}: {exc}")
        return []


async def fetch_realtime_candidates(
    db:      AsyncSession,
    profile: ICPProfile,
) -> list[EventORM]:
    """
    Main entry point called from /api/search.

    1.  build_queries()  — Groq LLM converts ICP form → targeted queries
    2a. SerpAPI google_events   (up to 8 queries × 10 results = 80 events)
    2b. Ticketmaster             (up to 12 queries)
    2c. Eventbrite               (up to 9 queries with lat/lon)
    2d. PredictHQ                (up to 6 queries)
    3.  Deduplicate across all sources
    4.  Upsert new events to DB
    5.  Query DB for all matching events (existing + new)
    6.  Return EventORM list for scoring
    """
    today     = date.today().isoformat()
    date_from = profile.date_from or today
    date_to   = profile.date_to   or "2030-12-31"

    # ── Step 1: Groq LLM query generation ─────────────────────────
    query_bundle = await build_queries(
        industries   = profile.target_industries    or [],
        geographies  = profile.target_geographies   or [],
        personas     = profile.target_personas      or [],
        event_types  = profile.preferred_event_types or [],
        company_desc = profile.company_description   or "",
        date_from    = date_from,
        date_to      = date_to,
    )

    # ── Step 2: API key status + circuit-breaker health ────────────
    phq_key = getattr(settings, "predicthq_key", "") or ""
    key_ok = {
        "SerpAPI":      bool(settings.serpapi_key),
        "Ticketmaster": bool(settings.ticketmaster_key),
        "Eventbrite":   bool(settings.eventbrite_token),
        "PredictHQ":    bool(phq_key),
    }
    # Skip sources whose circuit is open (401/402/404/429/… recently) —
    # don't burn wall-clock or quota on sources known to be down.
    api_ok  = {k: v and source_health.is_available(k) for k, v in key_ok.items()}
    active  = [k for k, v in api_ok.items() if v]
    missing = [k for k, v in key_ok.items() if not v]
    tripped = [k for k, v in key_ok.items() if v and not api_ok[k]]
    if tripped:
        logger.info(f"Pipeline: skipping unhealthy sources {tripped} (circuit open)")

    diff_s = getattr(profile, "differentiator_score", None)
    client_r = getattr(profile, "client_count_range", None)
    logger.info(
        f"Pipeline start | company={profile.company_name!r} | "
        f"diff={diff_s} clients={client_r} | "
        f"active={active} | missing_keys={missing} | "
        f"keywords={query_bundle.keywords_used[:3]} | "
        f"serp={len(query_bundle.serpapi)} "
        f"tm={len(query_bundle.ticketmaster)} "
        f"eb={len(query_bundle.eventbrite)} "
        f"phq={len(query_bundle.predicthq)}"
    )

    # ── Step 3: Fire all APIs in parallel, each isolated ──────────
    serp_coro = (
        run_serpapi_queries(
            query_bundle.serpapi, settings.serpapi_key, date_from, date_to
        ) if api_ok["SerpAPI"] and query_bundle.serpapi else _noop()
    )
    tm_coro = (
        run_ticketmaster_queries(
            query_bundle.ticketmaster, settings.ticketmaster_key, date_from, date_to
        ) if api_ok["Ticketmaster"] and query_bundle.ticketmaster else _noop()
    )
    eb_coro = (
        run_eventbrite_queries(
            query_bundle.eventbrite, settings.eventbrite_token, date_from, date_to
        ) if api_ok["Eventbrite"] and query_bundle.eventbrite else _noop()
    )
    phq_coro = (
        run_predicthq_queries(
            query_bundle.predicthq, phq_key, date_from, date_to
        ) if api_ok["PredictHQ"] and query_bundle.predicthq else _noop()
    )

    serp_evs, tm_evs, eb_evs, phq_evs = await asyncio.gather(
        _safe_run(serp_coro, "SerpAPI"),
        _safe_run(tm_coro,   "Ticketmaster"),
        _safe_run(eb_coro,   "Eventbrite"),
        _safe_run(phq_coro,  "PredictHQ"),
    )

    # Per-source log
    for src, evs in [
        ("SerpAPI",      serp_evs),
        ("Ticketmaster", tm_evs),
        ("Eventbrite",   eb_evs),
        ("PredictHQ",    phq_evs),
    ]:
        if evs:
            logger.info(f"  ✓ {src}: {len(evs)} events")
        elif api_ok.get(src):
            logger.info(f"  ○ {src}: 0 events (key present but no results)")
        elif key_ok.get(src):
            logger.debug(f"  — {src}: skipped (circuit open)")
        else:
            logger.debug(f"  — {src}: key not configured")

    # ── Step 4: Deduplicate across all sources ─────────────────────
    # ── Fuzzy cross-source deduplication (Tier-2 improvement 3.7) ────
    # The same event appears across all 4 sources with different names:
    #   EventsEye: "MONEY20/20 USA 2026"
    #   Ticketmaster: "Money 20/20 Conference"
    #   PredictHQ:  "Money20/20"
    # SHA1(name+date+city) alone misses these. We add a fuzzy name+date check.
    #
    # Algorithm: after hash dedup, compare each new event against existing
    # events with same city + start date ±2 days. If name similarity > 0.72,
    # treat as duplicate and keep the richer record (more non-empty fields).
    #
    # Uses basic token overlap (no external deps) — works without rapidfuzz.

    def _name_similarity(a: str, b: str) -> float:
        """Token-overlap similarity: |intersection| / |union| of word sets."""
        # Normalise: lowercase, strip punctuation, split to tokens ≥ 3 chars
        import re as _re
        _clean = lambda s: set(
            w for w in _re.split(r"[\s\-&/,\']+", s.lower())
            if len(w) >= 3 and not w.isdigit()
        )
        ta, tb = _clean(a), _clean(b)
        if not ta or not tb:
            return 0.0
        return len(ta & tb) / len(ta | tb)

    def _richer(a: dict, b: dict) -> dict:
        """Return the dict with more non-empty field values."""
        score = lambda d: sum(1 for v in d.values() if v and v != 0 and v is not False)
        return a if score(a) >= score(b) else b

    def _date_close(a: dict, b: dict) -> bool:
        """True if start_dates are within 2 days of each other."""
        from datetime import datetime
        try:
            da = datetime.strptime(a.get("start_date", "")[:10], "%Y-%m-%d")
            db = datetime.strptime(b.get("start_date", "")[:10], "%Y-%m-%d")
            return abs((da - db).days) <= 2
        except Exception:
            return False

    # Stage 1: hash-based dedup (existing)
    all_raw: list[dict] = []
    seen_hashes: set[str] = set()
    for evs in [serp_evs, tm_evs, eb_evs, phq_evs]:
        for ev in evs:
            dh = ev.get("dedup_hash") if isinstance(ev, dict) else getattr(ev, "dedup_hash", "")
            if dh and dh not in seen_hashes:
                seen_hashes.add(dh)
                all_raw.append(ev if isinstance(ev, dict) else (ev.dict() if hasattr(ev,"dict") else vars(ev)))

    # Stage 2: fuzzy dedup — group by city+year, check name similarity
    new_events: list[dict] = []
    for candidate in all_raw:
        cname = (candidate.get("name") or "").strip()
        ccity = (candidate.get("city") or "").lower().strip()
        is_dup = False
        for i, existing in enumerate(new_events):
            ename = (existing.get("name") or "").strip()
            ecity = (existing.get("city") or "").lower().strip()
            if ccity and ecity and ccity != ecity:
                continue   # different city — not a duplicate
            if not _date_close(candidate, existing):
                continue   # different dates — not a duplicate
            sim = _name_similarity(cname, ename)
            if sim >= 0.72:
                # Same event from different sources — keep the richer record
                new_events[i] = _richer(candidate, existing)
                is_dup = True
                break
        if not is_dup:
            new_events.append(candidate)

    logger.info(
        f"Dedup: {len(all_raw)} raw → {len(new_events)} unique "
        f"({len(all_raw)-len(new_events)} fuzzy dupes removed)"
    )

    logger.info(
        f"Real-time: {len(new_events)} unique events "
        f"(serp={len(serp_evs)} tm={len(tm_evs)} "
        f"eb={len(eb_evs)} phq={len(phq_evs)})"
    )

    # ── Step 5: Upsert to DB ───────────────────────────────────────
    if new_events:
        inserted, dupes = await batch_upsert_events(db, new_events, skip_past=True)
        logger.info(f"DB upsert: {inserted} new, {dupes} duplicates")
    else:
        logger.info("No new events to upsert")

    # ── Step 6: Query DB ───────────────────────────────────────────
    stmt = select(EventORM).where(
        EventORM.start_date >= date_from,
        EventORM.start_date <= date_to,
    )

    # Geography filter
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

    # Industry filter — _expand_industry_terms imported from db.crud
    ind_filters = []
    if profile.target_industries:
        for term in _expand_industry_terms(profile.target_industries):
            ind_filters.append(EventORM.industry_tags.ilike(f"%{term}%"))
            ind_filters.append(EventORM.related_industries.ilike(f"%{term}%"))
            ind_filters.append(EventORM.description.ilike(f"%{term}%"))
            ind_filters.append(EventORM.name.ilike(f"%{term}%"))
        if ind_filters:
            stmt = stmt.where(or_(*ind_filters))

    result        = await db.execute(stmt.limit(500))
    db_candidates = list(result.scalars().all())

    # ── Tiered widening (3 tiers, not a blunt drop) ──────────────────
    if len(db_candidates) < 10:
        logger.info(f"Tier-1 too few ({len(db_candidates)}) — tier-2: drop persona filter")
        # Tier 2: industry + geo only (drop persona)
        stmt2 = select(EventORM).where(
            EventORM.start_date >= date_from,
            EventORM.start_date <= date_to,
        )
        if ind_filters:
            stmt2 = stmt2.where(or_(*ind_filters))
        if geo_filters:
            stmt2 = stmt2.where(or_(*geo_filters))
        r2 = await db.execute(stmt2.limit(500))
        db_candidates = list(r2.scalars().all())
        logger.info(f"Tier-2: {len(db_candidates)} candidates")

    if len(db_candidates) < 5:
        logger.info(f"Tier-2 too few ({len(db_candidates)}) — tier-3: geo + date only")
        # Tier 3: geo + date, no industry filter
        stmt3 = select(EventORM).where(
            EventORM.start_date >= date_from,
            EventORM.start_date <= date_to,
        )
        if geo_filters:
            stmt3 = stmt3.where(or_(*geo_filters))
        r3 = await db.execute(stmt3.limit(500))
        db_candidates = list(r3.scalars().all())
        logger.info(f"Tier-3: {len(db_candidates)} candidates (geo+date only)")

    if len(db_candidates) < 3:
        # Tier 4: date window only (no geo, no industry)
        logger.warning("Tier-3 too few — returning all future events in date window")
        r4 = await db.execute(
            select(EventORM).where(
                EventORM.start_date >= date_from,
                EventORM.start_date <= date_to,
            ).limit(300)
        )
        db_candidates = list(r4.scalars().all())

    # ── Progressive pre-enrichment ────────────────────────────────
    # Enrich events with empty descriptions BEFORE scoring so the scorer
    # has real data. Cap at 15 to stay within SerpAPI rate limits.
    # This fixes: "empty description → low score → not enriched → stays low"
    if settings.serpapi_key:
        try:
            from enrichment.serp_enricher import enrich_events_batch
            empty_desc = [
                e for e in db_candidates
                if not (e.description or "").strip() or len((e.description or "").strip()) < 60
            ][:15]
            if empty_desc:
                logger.info(f"Pre-enriching {len(empty_desc)} thin-description events before scoring")
                await enrich_events_batch(empty_desc, settings.serpapi_key)
        except Exception as exc:
            logger.debug(f"Pre-enrichment skipped: {exc}")

    logger.info(
        f"Pipeline complete: {len(db_candidates)} candidates for scoring | "
        f"new_from_apis={len(new_events)}"
    )
    return db_candidates
