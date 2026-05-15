"""
ingestion/realtime_pipeline.py  —  Real-time event discovery orchestrator

Combines ALL available event sources into one unified pipeline:
  1. SerpAPI google_events     — PRIMARY: real-time Google Events search
  2. Ticketmaster Discovery    — Business/tech events (5,000 calls/day free)
  3. Eventbrite                — Professional conferences (free with key)
  4. PredictHQ                 — Industry intelligence (1,000 events/month free)
  5. DB query                  — Existing stored events (always available)

Flow:
  fetch_realtime_events(profile) → List[EventORM-like objects for scoring]

  1. Build targeted queries from ICP inputs
  2. Fire all APIs concurrently (with timeouts)
  3. Batch upsert new events to DB (builds up the database over time)
  4. Query DB for all matching events (DB + newly stored real-time)
  5. Return combined deduplicated candidates

Usage in routes_events.py:
  from ingestion.realtime_pipeline import fetch_realtime_candidates
  candidates = await fetch_realtime_candidates(db, profile, settings)
"""
from __future__ import annotations

import asyncio
import hashlib
from datetime import date, datetime
from typing import Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from db.crud import batch_upsert_events, count_events, get_candidate_events
from ingestion.serpapi_events import search_events_for_profile
from models.event import EventCreate, EventORM
from models.icp_profile import ICPProfile

settings = get_settings()


# ── Ticketmaster real-time search ──────────────────────────────────

async def _fetch_ticketmaster(
    profile:  ICPProfile,
    api_key:  str,
    max_events: int = 50,
) -> list[EventCreate]:
    """
    Search Ticketmaster for B2B events matching the ICP profile.
    Uses keyword search by industry + geography with date filters.
    """
    if not api_key:
        return []

    import httpx, uuid

    BASE = "https://app.ticketmaster.com/discovery/v2/events.json"
    today = date.today().isoformat()
    date_from = profile.date_from or today
    date_to   = profile.date_to   or "2028-12-31"

    # Ticketmaster date format: 2026-06-01T00:00:00Z
    start_dt = f"{date_from}T00:00:00Z"
    end_dt   = f"{date_to}T23:59:59Z"

    # Build search keywords from industries
    keywords = _build_keyword_list(profile.target_industries, profile.company_description)

    # Country codes for Ticketmaster
    _TM_COUNTRIES = {
        "USA": "US", "UK": "GB", "United Kingdom": "GB",
        "Australia": "AU", "Canada": "CA", "Germany": "DE",
        "France": "FR", "Spain": "ES", "Netherlands": "NL",
        "Singapore": "SG", "Japan": "JP", "South Korea": "KR",
        "UAE": "AE", "New Zealand": "NZ", "Ireland": "IE",
        "Belgium": "BE", "Switzerland": "CH", "Austria": "AT",
        "Mexico": "MX", "Brazil": "BR", "Argentina": "AR",
    }

    country_codes = [
        _TM_COUNTRIES[geo]
        for geo in profile.target_geographies
        if geo in _TM_COUNTRIES
    ] or ["US", "GB", "SG", "AU"]

    all_events: list[EventCreate] = []
    seen_hashes: set[str] = set()

    async with httpx.AsyncClient(timeout=12) as client:
        for kw in keywords[:4]:
            for cc in country_codes[:3]:
                try:
                    r = await client.get(BASE, params={
                        "apikey":            api_key,
                        "keyword":           kw,
                        "countryCode":       cc,
                        "classificationName":"conference,business,technology,expo,seminar",
                        "startDateTime":     start_dt,
                        "endDateTime":       end_dt,
                        "size":              20,
                        "sort":              "date,asc",
                        "locale":            "en-us",
                    })
                    if not r.is_success:
                        logger.debug(f"Ticketmaster {kw}/{cc}: HTTP {r.status_code}")
                        continue

                    raw_events = r.json().get("_embedded", {}).get("events", []) or []

                    for ev in raw_events:
                        try:
                            ec = _ticketmaster_to_event_create(ev, kw)
                            if ec and ec.dedup_hash not in seen_hashes:
                                if ec.start_date >= today:
                                    seen_hashes.add(ec.dedup_hash)
                                    all_events.append(ec)
                        except Exception as exc:
                            logger.debug(f"Ticketmaster parse error: {exc}")

                    await asyncio.sleep(0.2)

                except Exception as exc:
                    logger.debug(f"Ticketmaster {kw}/{cc} error: {exc}")

    logger.info(f"Ticketmaster: {len(all_events)} events fetched")
    return all_events[:max_events]


def _ticketmaster_to_event_create(ev: dict, kw: str = "") -> Optional[EventCreate]:
    import uuid as _uuid
    name = (ev.get("name") or "").strip()
    if not name:
        return None

    dates = ev.get("dates", {}).get("start", {})
    start_date = dates.get("localDate", "")
    if not start_date:
        return None

    venues = ev.get("_embedded", {}).get("venues", [{}])
    venue  = venues[0] if venues else {}
    city   = venue.get("city", {}).get("name", "")
    country= venue.get("country", {}).get("name", "")
    vname  = venue.get("name", "")
    address= venue.get("address", {}).get("line1", "")

    cls    = (ev.get("classifications") or [{}])[0]
    seg    = cls.get("segment", {}).get("name", "")
    genre  = cls.get("genre", {}).get("name", "")
    ind    = f"{seg}, {genre}".strip(", ") or kw

    prices = ev.get("priceRanges", [])
    price  = prices[0].get("min", 0.0) if prices else 0.0
    price_desc = f"From ${price:.0f}" if price else ""

    link   = ev.get("url", "")
    dh     = hashlib.sha1(f"{name.lower()}|{start_date}|{city.lower()}".encode()).hexdigest()

    return EventCreate(
        id              = str(_uuid.uuid4()),
        dedup_hash      = dh,
        source_platform = "Ticketmaster",
        source_url      = link,
        name            = name,
        description     = ev.get("info", "") or f"{name} — {seg} event.",
        short_summary   = ev.get("pleaseNote", "")[:200],
        edition_number  = "",
        start_date      = start_date,
        end_date        = start_date,
        duration_days   = 1,
        venue_name      = vname,
        event_venues    = vname,
        address         = address,
        city            = city,
        country         = country,
        event_cities    = f"{city}, {country}".strip(", "),
        is_virtual      = False,
        is_hybrid       = False,
        est_attendees   = 0,
        category        = "conference",
        industry_tags   = ind,
        related_industries = ind,
        audience_personas = "executives, professionals, business leaders",
        ticket_price_usd = float(price),
        price_description = price_desc,
        registration_url = link,
        website          = link,
        sponsors = "", speakers_url = "", agenda_url = "",
    )


# ── Eventbrite real-time search ────────────────────────────────────

async def _fetch_eventbrite(
    profile:  ICPProfile,
    token:    str,
    max_events: int = 50,
) -> list[EventCreate]:
    """Search Eventbrite using lat/lon + keyword (avoids country-code 404 bug)."""
    if not token:
        return []

    import httpx, uuid

    BASE = "https://www.eventbriteapi.com/v3/events/search/"
    today = date.today().isoformat()
    date_from = profile.date_from or today

    # Geo coordinates for key cities
    _GEO_COORDS = {
        "Indonesia": [(-6.2088, 106.8456, "SG"), (-7.2575, 112.7521, "SG")],
        "Singapore": [(1.3521, 103.8198, "SG")],
        "India":     [(12.9716, 77.5946, "IN"), (19.0760, 72.8777, "IN")],
        "USA":       [(40.7128, -74.0060, "US"), (37.7749, -122.4194, "US")],
        "UK":        [(51.5074, -0.1278, "GB")],
        "UAE":       [(25.2048, 55.2708, "AE")],
        "Germany":   [(52.5200, 13.4050, "DE")],
        "Australia": [(-33.8688, 151.2093, "AU")],
        "Japan":     [(35.6762, 139.6503, "JP")],
        "Malaysia":  [(3.1390, 101.6869, "MY")],
        "Canada":    [(43.6532, -79.3832, "CA")],
        "France":    [(48.8566, 2.3522, "FR")],
        "Brazil":    [(-23.5505, -46.6333, "BR")],
        "Global":    [(1.3521, 103.8198, "SG"), (51.5074, -0.1278, "GB"), (40.7128, -74.0060, "US")],
    }

    keywords = _build_keyword_list(profile.target_industries, profile.company_description)
    coords_list: list[tuple] = []
    for geo in profile.target_geographies[:3]:
        coords_list.extend(_GEO_COORDS.get(geo, []))
    if not coords_list:
        coords_list = [(1.3521, 103.8198, "SG"), (51.5074, -0.1278, "GB")]

    all_events: list[EventCreate] = []
    seen_hashes: set[str] = set()

    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(headers=headers, timeout=12) as client:
        for kw in keywords[:3]:
            for lat, lon, _ in coords_list[:3]:
                try:
                    r = await client.get(BASE, params={
                        "q":                    kw,
                        "location.latitude":    lat,
                        "location.longitude":   lon,
                        "location.within":      "100km",
                        "start_date.range_start": f"{date_from}T00:00:00Z",
                        "expand":               "venue,ticket_availability",
                        "page_size":            20,
                        "sort_by":              "date",
                    })

                    if r.status_code == 404:
                        logger.debug("Eventbrite: endpoint 404 — skipping")
                        return all_events
                    if not r.is_success:
                        logger.debug(f"Eventbrite {kw}: HTTP {r.status_code}")
                        continue

                    raw_events = r.json().get("events", []) or []
                    for ev in raw_events:
                        try:
                            ec = _eventbrite_to_event_create(ev, kw)
                            if ec and ec.dedup_hash not in seen_hashes:
                                if ec.start_date >= today:
                                    seen_hashes.add(ec.dedup_hash)
                                    all_events.append(ec)
                        except Exception as exc:
                            logger.debug(f"Eventbrite parse error: {exc}")

                    await asyncio.sleep(0.3)

                except httpx.HTTPStatusError as exc:
                    if "404" in str(exc):
                        logger.debug("Eventbrite: 404, stopping")
                        return all_events
                    logger.debug(f"Eventbrite {kw} error: {exc}")
                except Exception as exc:
                    logger.debug(f"Eventbrite {kw} error: {exc}")

    logger.info(f"Eventbrite: {len(all_events)} events fetched")
    return all_events[:max_events]


def _eventbrite_to_event_create(ev: dict, kw: str = "") -> Optional[EventCreate]:
    import uuid as _uuid
    name = (ev.get("name", {}).get("text") or "").strip()
    if not name:
        return None

    start = ev.get("start", {}).get("local", "")[:10]
    if not start:
        return None

    venue   = ev.get("venue") or {}
    addr    = venue.get("address") or {}
    city    = addr.get("city", "")
    country = addr.get("country", "")
    vname   = venue.get("name", "")

    ticket  = ev.get("ticket_availability") or {}
    minp    = ticket.get("minimum_ticket_price") or {}
    price   = float(minp.get("major_value", 0)) if minp else 0.0
    is_free = ev.get("is_free", False)
    price_desc = "Free" if is_free else (f"From ${price:.0f}" if price else "")

    desc = (ev.get("description", {}).get("text") or "")[:600]
    link = ev.get("url", "")
    dh   = hashlib.sha1(f"{name.lower()}|{start}|{city.lower()}".encode()).hexdigest()

    return EventCreate(
        id              = str(_uuid.uuid4()),
        dedup_hash      = dh,
        source_platform = "Eventbrite",
        source_url      = link,
        name            = name,
        description     = desc or f"{name} — professional event.",
        short_summary   = (ev.get("summary") or "")[:200],
        edition_number  = "",
        start_date      = start,
        end_date        = (ev.get("end", {}).get("local") or start)[:10],
        duration_days   = 1,
        venue_name      = vname,
        event_venues    = vname,
        address         = addr.get("localized_address_display", ""),
        city            = city,
        country         = country,
        event_cities    = f"{city}, {country}".strip(", "),
        is_virtual      = ev.get("online_event", False),
        is_hybrid       = False,
        est_attendees   = int(ev.get("capacity") or 0),
        category        = "conference",
        industry_tags   = kw,
        related_industries = kw,
        audience_personas = "executives, professionals",
        ticket_price_usd = price,
        price_description = price_desc,
        registration_url = link,
        website          = link,
        sponsors = "", speakers_url = "", agenda_url = "",
    )


# ── PredictHQ wrapper ──────────────────────────────────────────────

async def _fetch_predicthq(
    profile:  ICPProfile,
    api_key:  str,
) -> list[EventCreate]:
    if not api_key:
        return []
    try:
        from ingestion.predicthq import search_predicthq
        return await search_predicthq(
            api_key     = api_key,
            industries  = profile.target_industries,
            geographies = profile.target_geographies,
            date_from   = profile.date_from or date.today().isoformat(),
            date_to     = profile.date_to   or "2028-12-31",
            limit       = 50,
        )
    except Exception as exc:
        logger.warning(f"PredictHQ fetch error: {exc}")
        return []


# ── Keyword builder helper ─────────────────────────────────────────

def _build_keyword_list(
    industries:  list[str],
    company_desc: str = "",
) -> list[str]:
    """Build a list of search keywords from profile industries."""
    _IND_KW = {
        "Technology":           ["technology conference", "tech summit"],
        "AI / Machine Learning": ["AI conference", "machine learning summit"],
        "Cloud Computing":      ["cloud computing", "cloud conference"],
        "Cybersecurity":        ["cybersecurity conference", "security summit"],
        "Manufacturing":        ["manufacturing expo", "industrial conference"],
        "Logistics / Supply Chain": ["logistics conference", "supply chain expo"],
        "Healthcare / Medtech": ["healthcare conference", "medtech summit"],
        "Fintech":              ["fintech conference", "financial technology"],
        "Retail / Ecommerce":   ["retail conference", "ecommerce summit"],
        "Energy / Cleantech":   ["energy conference", "cleantech summit"],
        "Data & Analytics":     ["data analytics conference", "big data summit"],
        "HR Tech":              ["HR technology conference", "talent management"],
        "Marketing":            ["marketing conference", "digital marketing summit"],
    }

    keywords: list[str] = []
    for ind in industries[:4]:
        kws = _IND_KW.get(ind, [f"{ind.lower()} conference"])
        keywords.extend(kws[:1])

    # Enrich from company description
    if company_desc:
        desc_lower = company_desc.lower()
        extras = [
            ("supply chain", "supply chain conference"),
            ("saas", "SaaS B2B conference"),
            ("cybersecurity", "cybersecurity conference"),
            ("analytics", "data analytics summit"),
            ("fintech", "fintech conference"),
        ]
        for kw, term in extras:
            if kw in desc_lower and term not in keywords:
                keywords.insert(0, term)

    return keywords[:6] if keywords else ["technology conference", "business summit"]


# ══════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════════════

async def fetch_realtime_candidates(
    db:       AsyncSession,
    profile:  ICPProfile,
    *,
    settings_override=None,
) -> list[EventORM]:
    """
    Orchestrate all real-time APIs + DB to get candidates for scoring.

    Steps:
      1. Fire SerpAPI google_events, Ticketmaster, Eventbrite, PredictHQ in parallel
      2. Batch upsert all new events to DB (deduped)
      3. Query DB for all events matching the profile (includes newly stored ones)
      4. Return combined candidates

    This function always returns EventORM objects (from DB) so the scorer
    and groq_ranker work unchanged with the same interface.
    """
    cfg = settings_override or settings
    today = date.today().isoformat()

    realtime_tasks = []

    # SerpAPI google_events — PRIMARY real-time source
    if cfg.serpapi_key:
        realtime_tasks.append(
            search_events_for_profile(
                serpapi_key   = cfg.serpapi_key,
                industries    = profile.target_industries,
                geographies   = profile.target_geographies,
                event_types   = profile.preferred_event_types,
                date_from     = profile.date_from or today,
                date_to       = profile.date_to   or "2028-12-31",
                company_desc  = profile.company_description,
                max_queries   = 6,    # 6 queries × 1 credit = 6 SerpAPI credits
                max_per_query = 10,
            )
        )
    else:
        realtime_tasks.append(asyncio.coroutine(lambda: [])())

    # Ticketmaster
    if cfg.ticketmaster_key:
        realtime_tasks.append(
            _fetch_ticketmaster(profile, cfg.ticketmaster_key, max_events=40)
        )
    else:
        realtime_tasks.append(_noop())

    # Eventbrite
    if cfg.eventbrite_token:
        realtime_tasks.append(
            _fetch_eventbrite(profile, cfg.eventbrite_token, max_events=40)
        )
    else:
        realtime_tasks.append(_noop())

    # PredictHQ
    predicthq_key = getattr(cfg, "predicthq_key", "")
    if predicthq_key:
        realtime_tasks.append(_fetch_predicthq(profile, predicthq_key))
    else:
        realtime_tasks.append(_noop())

    # Fire all APIs concurrently with timeout
    logger.info(
        f"Real-time pipeline: firing {sum(1 for _ in realtime_tasks)} sources in parallel "
        f"for '{profile.company_name}' | {profile.target_industries[:2]} | {profile.target_geographies[:2]}"
    )

    try:
        results = await asyncio.wait_for(
            asyncio.gather(*realtime_tasks, return_exceptions=True),
            timeout=25.0,  # 25 seconds total timeout for all APIs
        )
    except asyncio.TimeoutError:
        logger.warning("Real-time pipeline: overall timeout (25s) — using DB only")
        results = [[], [], [], []]

    # Collect new events from all sources
    new_events: list[EventCreate] = []
    source_counts = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.warning(f"Real-time source {i} error: {result}")
            source_counts.append(0)
        else:
            events = result or []
            new_events.extend(events)
            source_counts.append(len(events))

    source_names = ["SerpAPI", "Ticketmaster", "Eventbrite", "PredictHQ"]
    for name, count in zip(source_names, source_counts):
        if count > 0:
            logger.info(f"  {name}: {count} events")

    # Upsert new events to DB (dedup by name+date+city hash)
    if new_events:
        inserted, skipped = await batch_upsert_events(
            db,
            new_events,
            skip_past=True,
        )
        logger.info(
            f"Real-time upsert: {len(new_events)} new events → "
            f"inserted={inserted} dupes={skipped}"
        )
    else:
        logger.info("Real-time pipeline: no new events from APIs")

    # NOW query DB — includes both pre-existing EventsEye data AND
    # newly stored real-time events
    from sqlalchemy import or_, select
    from models.event import EventORM as _EventORM

    date_from  = profile.date_from or today
    date_to    = profile.date_to   or "2030-12-31"

    stmt = select(_EventORM).where(
        _EventORM.start_date >= date_from,
        _EventORM.start_date <= date_to,
    )

    # Geography filter
    is_global = any(
        g.lower().strip() in ("global", "worldwide", "international", "any")
        for g in profile.target_geographies
    )
    if not is_global and profile.target_geographies:
        geo_filters = []
        for geo in profile.target_geographies:
            geo_parts = [geo.lower()]
            if " - " in geo.lower():
                geo_parts.extend(p.strip() for p in geo.lower().split(" - "))
            for part in geo_parts:
                if len(part) > 1:
                    geo_filters.append(_EventORM.country.ilike(f"%{part}%"))
                    geo_filters.append(_EventORM.city.ilike(f"%{part}%"))
                    geo_filters.append(_EventORM.event_cities.ilike(f"%{part}%"))
        if geo_filters:
            stmt = stmt.where(or_(*geo_filters))

    # Industry filter using taxonomy expansion
    if profile.target_industries:
        from db.crud import _expand_industry_terms
        expanded = _expand_industry_terms(profile.target_industries)
        ind_filters = []
        for term in expanded:
            ind_filters.append(_EventORM.industry_tags.ilike(f"%{term}%"))
            ind_filters.append(_EventORM.related_industries.ilike(f"%{term}%"))
            ind_filters.append(_EventORM.description.ilike(f"%{term}%"))
            ind_filters.append(_EventORM.name.ilike(f"%{term}%"))
        if ind_filters:
            stmt = stmt.where(or_(*ind_filters))

    from sqlalchemy.ext.asyncio import AsyncSession as _AS
    result = await db.execute(stmt.limit(500))
    db_candidates = list(result.scalars().all())

    # If industry filter returned <10, also pull WITHOUT industry filter
    # (broader fallback — scorer will rank them properly)
    if len(db_candidates) < 10:
        stmt_wide = select(_EventORM).where(
            _EventORM.start_date >= date_from,
            _EventORM.start_date <= date_to,
        )
        if not is_global and profile.target_geographies:
            stmt_wide = stmt_wide.where(or_(*geo_filters))
        result_wide = await db.execute(stmt_wide.limit(500))
        db_candidates = list(result_wide.scalars().all())
        logger.info(f"Widened DB query: {len(db_candidates)} candidates (no industry filter)")

    logger.info(
        f"Real-time pipeline complete: "
        f"{len(db_candidates)} candidates from DB "
        f"(including {len(new_events)} new real-time events)"
    )
    return db_candidates


async def _noop() -> list:
    """Placeholder for missing API keys."""
    return []
