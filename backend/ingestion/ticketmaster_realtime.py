"""
ingestion/ticketmaster_realtime.py  —  Ticketmaster Discovery API v2

Flow when ICP form submits:
    build_queries() → TicketmasterQuery list
    → run_ticketmaster_queries()
        → _fetch_page()           GET /discovery/v2/events.json
        → _fetch_event_detail()   GET /discovery/v2/events/{id}  (optional)
        → _parse_event()
        → normalise(raw, "Ticketmaster")
        → crud.upsert_event()

Rate limits: 5,000 calls/day · 5 req/sec

Real API response field mapping (verified against live samples):
  SEARCH /events.json response:
    .name                             → name
    .url                              → source_url + registration_url
    .id                               → used for detail fetch
    .dates.start.localDate            → start_date
    .dates.end.localDate              → end_date (often absent in search)
    .dates.status.code                → skip if "cancelled"
    ._embedded.venues[0].name         → venue_name
    ._embedded.venues[0].city.name    → city
    ._embedded.venues[0].state.name   → fallback city for US events
    ._embedded.venues[0].country.name → country
    .classifications[0].segment.name  → industry_tags (primary)
    .classifications[0].genre.name    → industry_tags (secondary)
    .classifications[0].subGenre.name → industry_tags (tertiary)
    .priceRanges[0].min/max/currency  → price_description
    .description / .info / .pleaseNote / .additionalInfo → description

  DETAIL /events/{id} response:
    All of the above, plus:
    .description                      → description (richest, highest priority)
    .dates.end.localDate              → end_date (more often present)
    ._embedded.venues / attractions   → same fields, usually identical
"""
from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import date
from typing import Optional

import httpx
from loguru import logger

from ingestion.icp_query_builder import TicketmasterQuery
from ingestion.platform_normaliser import normalise
from ingestion.source_health import source_health

SOURCE = "Ticketmaster"

SEARCH_URL = "https://app.ticketmaster.com/discovery/v2/events.json"
DETAIL_URL = "https://app.ticketmaster.com/discovery/v2/events/{tm_id}"

TM_B2B_CLASSIFICATIONS = ["Conference", "Seminar", "Expo", "Trade Show"]

# Consumer-only segments: skip unless keyword suggests B2B angle
NON_B2B_SEGMENTS = frozenset({
    "Music", "Sports", "Arts & Theatre", "Film", "Miscellaneous", "Undefined",
})

# Segments where detail fetch is worth the extra API call
DETAIL_FETCH_SEGMENTS = frozenset({
    "Conference", "Business", "Technology", "Seminar",
    "Expo", "Trade Show", "Education",
})

MAX_EVENTS_PER_SEARCH = 200
MAX_DETAIL_FETCHES    = 20
_HEADERS = {"User-Agent": "LeadStrategus-ICP-Agent/2.0", "Accept": "application/json"}


# ── Field extraction helpers ──────────────────────────────────────

def _venue(ev: dict) -> dict:
    venues = ((ev.get("_embedded") or {}).get("venues", []) or [])
    return venues[0] if venues else {}


def _city(v: dict) -> str:
    return (v.get("city", {}) or {}).get("name", "") or (v.get("state", {}) or {}).get("name", "") or ""


def _country(v: dict) -> str:
    return (v.get("country", {}) or {}).get("name", "") or ""


def _start_date(ev: dict) -> str:
    return ((ev.get("dates", {}) or {}).get("start", {}) or {}).get("localDate", "") or ""


def _end_date(ev: dict) -> str:
    return ((ev.get("dates", {}) or {}).get("end", {}) or {}).get("localDate", "") or ""


def _is_cancelled(ev: dict) -> bool:
    code = ((ev.get("dates", {}) or {}).get("status", {}) or {}).get("code", "") or ""
    return code.lower() in ("cancelled", "offsale", "postponed")


def _classifications(ev: dict) -> tuple:
    cls_list = ev.get("classifications", []) or []
    if not cls_list:
        return ("", "", "")
    c = cls_list[0] or {}
    def _name(key):
        val = (c.get(key, {}) or {}).get("name", "") or ""
        return val if val.lower() not in ("undefined", "miscellaneous", "") else ""
    return _name("segment"), _name("genre"), _name("subGenre")


def _price_desc(ev: dict) -> str:
    ranges = ev.get("priceRanges", []) or []
    if not ranges:
        return "See website"
    pr = ranges[0] or {}
    cur = pr.get("currency", "USD") or "USD"
    lo  = pr.get("min")
    hi  = pr.get("max")
    if lo is None:
        return "See website"
    try:
        lo, hi = float(lo), float(hi) if hi else float(lo)
        if lo == 0 and hi == 0:
            return "Free"
        if lo == hi:
            return f"{cur} {lo:,.0f}"
        return f"From {cur} {lo:,.0f} – {hi:,.0f}"
    except (TypeError, ValueError):
        return "See website"


def _build_description(merged: dict, keyword: str,
                        segment: str, city: str, country: str) -> str:
    """
    Build description from TM fields in priority order:
      description  (richest — only in detail response)
      info         (event-specific notes)
      additionalInfo
      pleaseNote   (logistics/bag-policy — use only as last resort)
    """
    parts = []
    for field in ("description", "info", "additionalInfo"):
        val = (merged.get(field) or "").strip()
        if val and val not in parts:
            parts.append(val)
    # pleaseNote only if we have nothing better
    note = (merged.get("pleaseNote") or "").strip()
    if note and not parts:
        parts.append(note)

    if parts:
        return " | ".join(parts)[:600]

    # Generated fallback
    name = (merged.get("name", "") or keyword or "").strip()
    gen  = name
    if segment: gen += f" — {segment}"
    if city:    gen += f" in {city}"
    if country: gen += f", {country}"
    return gen[:600]


def _industry_tags(keyword: str, segment: str, genre: str, subgenre: str) -> str:
    parts = [keyword] if keyword else []
    for t in (segment, genre, subgenre):
        if t and t not in parts:
            parts.append(t)
    return ", ".join(parts)


def _is_b2b_relevant(segment: str, genre: str, keyword: str) -> bool:
    if segment not in NON_B2B_SEGMENTS:
        return True
    kl = keyword.lower()
    sl = segment.lower()
    if sl == "sports" and any(t in kl for t in ("sports business", "sports tech",
                                                 "esports", "sports analytics")):
        return True
    if sl == "music" and any(t in kl for t in ("music business", "music industry",
                                                "music tech", "music technology")):
        return True
    return False


# ── HTTP helpers ──────────────────────────────────────────────────

async def _check_error(resp: httpx.Response, ctx: str) -> Optional[str]:
    """
    Returns:
      "fatal"  → abort all further queries (auth failure, quota)
      "skip"   → skip this query/page (bad params, not found)
      None     → success, caller processes body
    """
    c = resp.status_code
    if c == 200:
        source_health.record_success(SOURCE)
        return None
    if c == 204:                     return "skip"   # empty result set
    if c == 400:
        logger.debug(f"TM 400 {ctx}: {resp.text[:80]}")
        return "skip"
    if c == 401:
        logger.error("TM 401 — TM_API_KEY invalid or missing")
        source_health.record_failure(SOURCE, status=401, detail="TM_API_KEY invalid")
        return "fatal"
    if c == 402:
        logger.warning("TM 402 — payment required")
        source_health.record_failure(SOURCE, status=402, detail="payment required")
        return "fatal"
    if c == 403:
        logger.warning("TM 403 — daily quota exceeded")
        source_health.record_failure(SOURCE, status=403, detail="daily quota exceeded")
        return "fatal"
    if c in (404, 410):
        # Detail 404s are per-event, not endpoint death — only trip on search endpoint
        if ctx.startswith("search"):
            source_health.record_failure(SOURCE, status=c, detail="search endpoint gone")
            logger.warning(f"TM {c} {ctx} — endpoint gone")
            return "fatal"
        logger.debug(f"TM {c} {ctx}")
        return "skip"
    if c == 429:
        source_health.record_failure(SOURCE, status=429, detail="rate limited")
        logger.warning("TM 429 rate-limited — stopping remaining queries")
        return "fatal"
    if c >= 500:
        source_health.record_failure(SOURCE, kind="transient", detail=f"HTTP {c}")
    logger.debug(f"TM HTTP {c} {ctx}")
    return "skip"


async def _fetch_page(client: httpx.AsyncClient, api_key: str,
                      keyword: str, country_code: str,
                      start_dt: str, end_dt: str,
                      classification: str, page: int) -> tuple:
    """
    Returns (events: list[dict], has_more: bool, fatal: bool)
    """
    params = {
        "apikey":             api_key,
        "keyword":            keyword,
        "countryCode":        country_code,
        "startDateTime":      start_dt,
        "endDateTime":        end_dt,
        "classificationName": classification,
        "size":               "50",
        "page":               str(page),
        "sort":               "date,asc",
        "locale":             "en-us,en,*",
        "includeTest":        "no",
        "includeTBA":         "no",
        "includeTBD":         "no",
    }
    try:
        resp  = await client.get(SEARCH_URL, params=params)
        error = await _check_error(resp, f"search '{keyword}/{country_code}' p{page}")
        if error == "fatal": return [], False, True
        if error == "skip":  return [], False, False
        if resp.status_code != 200: return [], False, False

        body       = resp.json()
        events     = (body.get("_embedded") or {}).get("events", []) or []
        page_info  = body.get("page", {}) or {}
        total_pgs  = int(page_info.get("totalPages", 1))
        has_more   = page < total_pgs - 1
        return events, has_more, False

    except httpx.TimeoutException:
        logger.debug(f"TM timeout search '{keyword}/{country_code}' p{page}")
        source_health.record_failure(SOURCE, kind="transient", detail="timeout")
        return [], False, False
    except Exception as exc:
        logger.debug(f"TM search error: {exc}")
        source_health.record_failure(SOURCE, kind="transient", detail=str(exc)[:80])
        return [], False, False


async def _fetch_event_detail(client: httpx.AsyncClient,
                               api_key: str, tm_id: str) -> dict:
    """
    GET /discovery/v2/events/{id}
    Returns full event dict or {} on error.
    Called only for B2B events lacking a description.
    """
    url = DETAIL_URL.format(tm_id=tm_id)
    try:
        resp  = await client.get(url, params={"apikey": api_key, "locale": "en-us,en,*"})
        error = await _check_error(resp, f"detail '{tm_id}'")
        if error or resp.status_code != 200:
            return {}
        return resp.json() or {}
    except httpx.TimeoutException:
        logger.debug(f"TM timeout detail '{tm_id}'")
        return {}
    except Exception as exc:
        logger.debug(f"TM detail error '{tm_id}': {exc}")
        return {}


# ── Parser ────────────────────────────────────────────────────────

def _parse_event(ev: dict, detail: dict, keyword: str) -> Optional[dict]:
    """
    Merge search result + detail into a 28-column-compatible dict.
    Returns None if the event should be skipped.
    """
    name = (ev.get("name") or "").strip()
    if not name:
        return None

    start = _start_date(ev)
    if not start or start < date.today().isoformat():
        return None

    if _is_cancelled(ev):
        return None

    # Detail fields override search fields when present
    merged = {**ev}
    if detail:
        for k, v in detail.items():
            if v and k not in ("_links", "images", "sales", "promoter",
                                "promoters", "outlets", "seatmap",
                                "accessibility", "ticketLimit", "products",
                                "externalLinks", "aliases", "localizedAliases"):
                merged[k] = v

    end        = _end_date(merged) or start
    venue_data = _venue(detail) or _venue(ev)
    city       = _city(venue_data)
    country    = _country(venue_data)
    venue_name = (venue_data.get("name", "") or "").strip()

    # Use detail classifications when available (more reliable)
    segment, genre, subgenre = _classifications(detail) if detail else ("", "", "")
    if not segment:
        segment, genre, subgenre = _classifications(ev)

    if not _is_b2b_relevant(segment, genre, keyword):
        return None

    tm_url     = merged.get("url", "") or ev.get("url", "") or ""
    description = _build_description(merged, keyword, segment, city, country)
    industry    = _industry_tags(keyword, segment, genre, subgenre)
    price       = _price_desc(detail) if detail else "" or _price_desc(ev)
    category    = (segment.lower()
                   if segment and segment.lower() != "undefined"
                   else "conference")

    return {
        "source_platform":   "Ticketmaster",
        "source_url":        tm_url,
        "name":              name,
        "description":       description,
        "category":          category,
        "start_date":        start,
        "end_date":          end,
        "venue_name":        venue_name,
        "city":              city,
        "country":           country,
        "industry_tags":     industry,
        "audience_personas": "",
        "est_attendees":     int(merged.get("capacity") or 0),
        "price_description": price or "See website",
        "registration_url":  tm_url,
        "website":           "",
        "sponsors":          "",
        "speakers_url":      "",
        "agenda_url":        "",
        "confidence_score":  0.9,
    }


# ── Public entry point ────────────────────────────────────────────

async def run_ticketmaster_queries(
    queries:             list[TicketmasterQuery],
    api_key:             str,
    date_from:           str = "",
    date_to:             str = "",
    max_pages_per_query: int = 2,
) -> list[dict]:
    """
    Execute ICP-driven Ticketmaster queries.

    1. Fetch pages from /events.json (50 events each, up to max_pages_per_query)
    2. For B2B events without descriptions, call /events/{id} (detail endpoint)
    3. Parse + normalise to 28-column schema
    4. Dedup by dedup_hash
    5. Return list for crud.batch_upsert_events()
    """
    if not api_key:
        logger.warning("Ticketmaster: TM_API_KEY not set — skipping")
        return []

    today          = date.today().isoformat()
    seen_hash:     set[str]  = set()
    results:       list[dict]= []
    detail_count:  int       = 0
    abort:         bool      = False

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(15.0, connect=5.0),
        headers=_HEADERS,
        follow_redirects=True,
    ) as client:

        for q_idx, q in enumerate(queries):
            if abort or len(results) >= MAX_EVENTS_PER_SEARCH:
                break

            # Rotate B2B classification each query for breadth
            classification = TM_B2B_CLASSIFICATIONS[q_idx % len(TM_B2B_CLASSIFICATIONS)]

            for page in range(max_pages_per_query):
                if abort or len(results) >= MAX_EVENTS_PER_SEARCH:
                    break

                events, has_more, fatal = await _fetch_page(
                    client, api_key, q.keyword, q.country_code,
                    q.start_dt, q.end_dt, classification, page,
                )

                if fatal:
                    abort = True
                    break

                if not events:
                    break   # no events this page → stop paging

                for ev in events:
                    if not isinstance(ev, dict) or len(results) >= MAX_EVENTS_PER_SEARCH:
                        break

                    # ── Date window pre-filter ────────────────────────
                    start = _start_date(ev)
                    if not start or start < today:
                        continue
                    if date_from and start < date_from: continue
                    if date_to   and start > date_to:   continue

                    # ── B2B segment pre-filter ────────────────────────
                    seg, genre, _ = _classifications(ev)
                    if not _is_b2b_relevant(seg, genre, q.keyword):
                        continue

                    # ── Detail fetch for B2B events without description ─
                    detail: dict = {}
                    has_desc = bool((ev.get("description") or "").strip() or
                                    (ev.get("info") or "").strip() or
                                    (ev.get("additionalInfo") or "").strip())
                    if (not has_desc and
                            detail_count < MAX_DETAIL_FETCHES and
                            seg in DETAIL_FETCH_SEGMENTS):
                        tm_id = ev.get("id", "")
                        if tm_id:
                            detail = await _fetch_event_detail(client, api_key, tm_id)
                            detail_count += 1
                            await asyncio.sleep(0.2)

                    # ── Parse → normalise → dedup ─────────────────────
                    try:
                        raw = _parse_event(ev, detail, q.keyword)
                        if raw is None:
                            continue
                        clean = normalise(raw, "Ticketmaster")
                        dh    = clean["dedup_hash"]
                        if dh in seen_hash:
                            continue
                        seen_hash.add(dh)
                        results.append(clean)
                    except Exception as exc:
                        logger.debug(f"TM parse: {exc}")

                if not has_more:
                    break   # no further pages for this query

                await asyncio.sleep(0.25)   # 5 req/sec limit

            await asyncio.sleep(0.25)

    logger.info(
        f"Ticketmaster: {len(results)} events | "
        f"{len(queries)} queries | {detail_count} detail fetches"
    )
    return results
