"""
ingestion/predicthq_realtime.py  —  PredictHQ Events API v1

Triggered live when the ICP form submits (4 fields: buyer, geography,
deal size, email). Searches only B2B-relevant categories, maps the
API response to the clean 28-column EventORM schema via platform_normaliser.

API:  GET https://api.predicthq.com/v1/events/
Auth: Authorization: Bearer {PREDICTHQ_KEY}
Docs: https://docs.predicthq.com/api/events/search-events
Free tier: 1,000 events/month (no credit card required)

Real API response fields used (verified against live sample):
    .id                      → dedup_hash suffix (internal PredictHQ ID)
    .title                   → name
    .description             → description (present in some events)
    .category                → category (conferences, expos, community, etc.)
    .labels[]                → raw PHQ labels (music, concert, etc.) — used for B2B filter
    .phq_labels[].label      → AI-generated PHQ labels — richer, used for industry_tags
    .phq_attendance          → est_attendees (most reliable field — PredictHQ's specialty)
    .rank                    → PHQ global rank 0-100 (confidence_score proxy)
    .local_rank              → local rank 0-100
    .start                   → start_date (UTC ISO, take first 10 chars for date)
    .start_local             → preferred: local date (YYYY-MM-DDThh:mm:ss)
    .end / .end_local        → end_date
    .geo.address.locality    → city (best — specific neighbourhood/suburb level)
    .geo.address.region      → state/region fallback for city
    .geo.address.country_code→ country (2-letter ISO code → we store as-is)
    .entities[].type==venue  → venue_name
    .state                   → skip if "deleted" or "cancelled"
    .country                 → 2-letter ISO fallback for country

Fields NOT used (not in 28-col schema or not relevant to agent):
    location[], place_hierarchies, scope, brand_safe,
    predicted_event_spend*, impact_patterns, phq_labels[].weight,
    first_seen, updated, predicted_end, duration, private, overflow

B2B category mapping (PredictHQ → our schema):
    conferences  → "conference"
    expos        → "expo"
    community    → "meetup"
    sports       → filtered out (unless keyword targets sports business)
    concerts     → filtered out
    festivals    → filtered out (unless keyword matches)
    politics     → filtered out
    school-holidays, daylight-savings → always filtered

PHQ label → industry_tags:
    PHQ labels are AI-generated and much richer than the legacy .labels field.
    Examples: "business-services", "technology", "finance-and-investment",
    "healthcare-and-medical", "manufacturing", "retail-and-consumer-goods"
    We join the top labels into industry_tags for Groq scoring context.

B2B phq_label filter (include list):
    Any event with at least one of these PHQ labels passes through.
    Events with NO matching label AND a non-B2B category are skipped.
"""
from __future__ import annotations

import asyncio
from datetime import date
from typing import Optional

import httpx
from loguru import logger

from ingestion.icp_query_builder import PredictHQQuery
from ingestion.platform_normaliser import normalise

BASE_URL = "https://api.predicthq.com/v1/events/"

# ── B2B category filter ───────────────────────────────────────────
# PredictHQ categories: conferences, expos, community, concerts, sports,
# festivals, performing-arts, politics, school-holidays, daylight-savings,
# academic, airport-delays, disasters, severe-weather, terror, health-warnings
B2B_CATEGORIES = "conferences,expos,community"

# Non-B2B categories that we always skip
SKIP_CATEGORIES = frozenset({
    "concerts", "sports", "festivals", "performing-arts", "politics",
    "school-holidays", "daylight-savings", "academic", "airport-delays",
    "disasters", "severe-weather", "terror", "health-warnings",
})

# PHQ AI labels that indicate B2B relevance
# If an event has ANY of these labels it's kept regardless of category
B2B_PHQ_LABELS = frozenset({
    "business-services", "technology", "finance-and-investment",
    "healthcare-and-medical", "manufacturing", "retail-and-consumer-goods",
    "logistics-and-transportation", "energy-and-utilities",
    "agriculture-forestry-and-fisheries", "science-and-research",
    "education-and-training", "marketing-and-advertising",
    "real-estate", "legal-and-compliance", "human-resources",
    "cybersecurity", "artificial-intelligence", "cloud-computing",
    "data-and-analytics", "software-and-saas", "fintech",
    "medtech", "edtech", "proptech", "cleantech",
    "ecommerce", "supply-chain", "procurement",
    "food-and-beverage",          # keep for F&B industry clients
    "trade-show", "conference", "summit", "expo", "seminar",
})

# Legacy .labels values (less precise than phq_labels) to skip
SKIP_LABELS = frozenset({
    "concert", "music", "sport", "festival", "holiday",
    "performing-arts", "politics", "weather", "terror",
})

# Map PredictHQ category → our clean category value
CATEGORY_MAP = {
    "conferences":     "conference",
    "expos":           "expo",
    "community":       "meetup",
    "performing-arts": "arts",
    "sports":          "sports",
    "concerts":        "concert",
    "festivals":       "festival",
}

# Minimum PHQ attendance to consider (filters out tiny/personal events)
MIN_ATTENDANCE = 100

# Max events per ICP search
MAX_EVENTS_PER_SEARCH = 200


# ─────────────────────────────────────────────────────────────────
# Field extraction helpers
# ─────────────────────────────────────────────────────────────────

def _local_date(ev: dict, field_local: str, field_utc: str) -> str:
    """
    Prefer the *_local field (YYYY-MM-DDThh:mm:ss) over UTC
    because trade shows and conferences are local-time events.
    Returns the date part only: YYYY-MM-DD.
    """
    val = (ev.get(field_local) or ev.get(field_utc) or "")
    return str(val)[:10] if val else ""


def _city(ev: dict) -> str:
    """
    Extract city from geo.address.locality (most specific),
    falling back through region → entities.
    """
    geo  = ev.get("geo", {}) or {}
    addr = geo.get("address", {}) or {}
    city = addr.get("locality", "") or addr.get("region", "") or ""
    if city:
        return city
    # Fallback: entity of type "city"
    for ent in (ev.get("entities", []) or []):
        if ent.get("type") == "city":
            return ent.get("name", "")
    return ""


def _country(ev: dict) -> str:
    """
    geo.address.country_code (2-letter ISO) is the most reliable.
    Fall back to .country field.
    """
    geo  = ev.get("geo", {}) or {}
    addr = geo.get("address", {}) or {}
    return addr.get("country_code", "") or ev.get("country", "") or ""


def _venue_name(ev: dict) -> str:
    """Extract venue name from entities list."""
    for ent in (ev.get("entities", []) or []):
        if ent.get("type") == "venue":
            return (ent.get("name", "") or "").strip()
    # Fallback: formatted_address from geo
    geo  = ev.get("geo", {}) or {}
    addr = geo.get("address", {}) or {}
    return ""


def _phq_labels(ev: dict) -> list[str]:
    """
    Extract AI-generated PHQ label strings (higher quality than legacy .labels).
    Returns list of label strings sorted by weight descending.
    """
    raw = ev.get("phq_labels", []) or []
    # Sort by weight descending so most-relevant label is first
    sorted_labels = sorted(raw, key=lambda x: x.get("weight", 0), reverse=True)
    return [item["label"] for item in sorted_labels if item.get("label")]


def _legacy_labels(ev: dict) -> list[str]:
    """Legacy .labels field — less precise, used for skip-filtering."""
    return [str(l).lower() for l in (ev.get("labels", []) or [])]


def _industry_tags(keyword: str, phq_labels: list[str], category: str) -> str:
    """
    Build industry_tags from:
    1. ICP keyword (most relevant — comes from Groq ICP parsing)
    2. PHQ AI labels (top 4, space-separated into readable form)
    3. Category as fallback
    """
    parts = []
    if keyword:
        parts.append(keyword)
    for label in phq_labels[:4]:
        # Convert "business-services" → "Business Services"
        readable = label.replace("-", " ").title()
        if readable not in parts:
            parts.append(readable)
    if not parts:
        parts.append(CATEGORY_MAP.get(category, category).title())
    return ", ".join(parts)


def _description(ev: dict, keyword: str, category: str,
                 city: str, country: str) -> str:
    """
    Build description from available PredictHQ fields.
    PredictHQ rarely provides rich descriptions for B2B events,
    so we compose from available data.
    """
    desc = (ev.get("description") or "").strip()
    if desc:
        return desc[:600]

    # Composed description from structured fields
    title    = (ev.get("title", "") or "").strip()
    cat_name = CATEGORY_MAP.get(category, category).title()
    parts    = []
    if title:
        parts.append(title)
    parts.append(f"{cat_name} in {city}" if city else cat_name)
    if country:
        parts.append(country)
    if keyword:
        parts.append(f"Topics: {keyword}")
    return " — ".join(parts)[:600]


def _is_b2b_relevant(ev: dict, keyword: str) -> bool:
    """
    True if this event is relevant for B2B sales intelligence.

    Rules:
    1. state != deleted/cancelled/postponed
    2. category NOT in SKIP_CATEGORIES, OR has a B2B phq_label
    3. NOT purely a consumer event (concert, sport) unless keyword matches
    4. phq_attendance >= MIN_ATTENDANCE (filters personal/tiny events)
    """
    # Skip deleted/cancelled
    state = (ev.get("state", "active") or "active").lower()
    if state in ("deleted", "cancelled", "postponed"):
        return False

    category    = (ev.get("category", "") or "").lower()
    phq_labels  = _phq_labels(ev)
    leg_labels  = _legacy_labels(ev)
    keyword_l   = keyword.lower()

    # If it has a B2B phq_label, always include regardless of category
    if any(lbl in B2B_PHQ_LABELS for lbl in phq_labels):
        return True

    # Skip purely non-B2B categories
    if category in SKIP_CATEGORIES:
        # Exception: if keyword explicitly targets sports/music business
        if category == "sports" and any(
            t in keyword_l for t in ("sports business", "sports tech",
                                     "esports", "sports analytics")
        ):
            return True
        if category == "concerts" and any(
            t in keyword_l for t in ("music business", "music industry",
                                     "music technology")
        ):
            return True
        return False

    # Skip events with non-B2B legacy labels (and no B2B phq_label)
    if all(l in SKIP_LABELS for l in leg_labels) and leg_labels:
        return False

    # Attendance filter: too small to be worth a sales trip
    att = int(ev.get("phq_attendance") or 0)
    if att > 0 and att < MIN_ATTENDANCE:
        return False

    return True


def _parse_event(ev: dict, keyword: str) -> Optional[dict]:
    """
    Map a single PredictHQ API event dict → 28-column normaliser dict.
    Returns None if the event should be skipped.
    """
    title = (ev.get("title") or "").strip()
    if not title or len(title) < 3:
        return None

    # ── Dates ────────────────────────────────────────────────────
    start = _local_date(ev, "start_local", "start")
    end   = _local_date(ev, "end_local",   "end") or start

    if not start or start < date.today().isoformat():
        return None

    # ── B2B relevance ─────────────────────────────────────────────
    if not _is_b2b_relevant(ev, keyword):
        return None

    # ── Location ──────────────────────────────────────────────────
    city       = _city(ev)
    country    = _country(ev)
    venue_name = _venue_name(ev)

    # ── Classification ────────────────────────────────────────────
    category   = CATEGORY_MAP.get((ev.get("category") or "").lower(), "conference")
    phq_labels = _phq_labels(ev)
    industry   = _industry_tags(keyword, phq_labels, ev.get("category", ""))

    # ── Attendance ────────────────────────────────────────────────
    # phq_attendance is PredictHQ's core value-add — most accurate estimate
    est_att = int(ev.get("phq_attendance") or 0)

    # ── Description ───────────────────────────────────────────────
    desc = _description(ev, keyword, ev.get("category", ""), city, country)

    # ── Confidence from PHQ rank ──────────────────────────────────
    # PHQ rank 0–100; map to 0.5–0.95 confidence range
    rank = int(ev.get("rank") or 50)
    confidence = round(0.5 + (rank / 100) * 0.45, 2)

    # ── source_url ────────────────────────────────────────────────
    # PredictHQ has NO public event page URLs.
    # We store a clean empty source_url so _is_platform_event_url()
    # doesn't return it, and SerpAPI enrichment fills a real link.
    # The PredictHQ event ID is preserved in dedup_hash for dedup only.

    return {
        "source_platform":   "PredictHQ",
        "source_url":        "",          # no public URL — SerpAPI enriches
        "name":              title,
        "description":       desc,
        "category":          category,
        "start_date":        start,
        "end_date":          end,
        "venue_name":        venue_name,
        "city":              city,
        "country":           country,
        "industry_tags":     industry,
        "audience_personas": "",          # PHQ doesn't provide buyer personas
        "est_attendees":     est_att,
        "price_description": "",          # PHQ doesn't provide pricing
        "registration_url":  "",          # SerpAPI enriches this
        "website":           "",
        "sponsors":          "",
        "speakers_url":      "",
        "agenda_url":        "",
        "confidence_score":  confidence,
        # Internal PHQ ID used in dedup_hash generation (via normalise())
        "_phq_id":           ev.get("id", ""),
    }


# ─────────────────────────────────────────────────────────────────
# HTTP helpers
# ─────────────────────────────────────────────────────────────────

async def _check_error(resp: httpx.Response, ctx: str) -> Optional[str]:
    """Returns "fatal", "skip", or None (success)."""
    c = resp.status_code
    if c == 200:   return None
    if c == 400:
        logger.debug(f"PHQ 400 {ctx}: {resp.text[:100]}")
        return "skip"
    if c == 401:
        logger.error("PredictHQ 401 — check PREDICTHQ_KEY")
        return "fatal"
    if c == 403:
        logger.warning("PredictHQ 403 — quota exceeded or plan limit")
        return "fatal"
    if c == 429:
        wait = int(resp.headers.get("Retry-After", "3"))
        logger.warning(f"PredictHQ rate-limited — sleeping {wait}s")
        await asyncio.sleep(wait)
        return "skip"
    logger.debug(f"PHQ HTTP {c} {ctx}")
    return "skip"


async def _fetch_page(
    client:       httpx.AsyncClient,
    api_key:      str,
    q:            str,
    country_code: str,
    start_gte:    str,
    end_lte:      str,
    offset:       int,
    limit:        int = 50,
    within:       str = "",
) -> tuple:
    """
    GET /v1/events/ — one page of results.

    Key parameters (from official docs):
      q            full-text search (ICP keyword)
      category     comma-separated B2B categories
      country      2-letter ISO code (optional — overridden by within)
      start.gte    ISO date — events starting on/after
      start.lte    ISO date — events starting on/before
      sort         phq_attendance (highest attendance = most relevant)
      state        active (skip deleted/cancelled)
      phq_attendance.gte  MIN_ATTENDANCE filter
      limit        max 50 per page (PredictHQ free tier)
      offset       pagination offset

    Returns (results: list, total: int, next_url: str, fatal: bool)
    """
    params: dict = {
        "q":                   q,
        "category":            B2B_CATEGORIES,
        "start.gte":           start_gte,
        "start.lte":           end_lte,
        "sort":                "-phq_attendance",   # highest attendance first
        "state":               "active",
        "phq_attendance.gte":  str(MIN_ATTENDANCE),
        "limit":               str(limit),
        "offset":              str(offset),
    }
    # Use country filter when no geo bounding box
    if country_code and not within:
        params["country"] = country_code
    # Geo bounding box (more precise — e.g. "100km@1.352,103.820" for Singapore)
    if within:
        params["within"] = within

    try:
        resp  = await client.get(BASE_URL, params=params)
        error = await _check_error(resp, f"'{q}/{country_code}' offset={offset}")
        if error == "fatal": return [], 0, "", True
        if error == "skip":  return [], 0, "", False
        if resp.status_code != 200: return [], 0, "", False

        body     = resp.json()
        results  = body.get("results", []) or []
        total    = int(body.get("count", 0))
        next_url = body.get("next", "") or ""
        return results, total, next_url, False

    except httpx.TimeoutException:
        logger.debug(f"PHQ timeout '{q}/{country_code}'")
        return [], 0, "", False
    except Exception as exc:
        logger.debug(f"PHQ search error '{q}': {exc}")
        return [], 0, "", False


# ─────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────

async def run_predicthq_queries(
    queries:      list[PredictHQQuery],
    api_key:      str,
    date_from:    str = "",
    date_to:      str = "",
    max_pages:    int = 2,
) -> list[dict]:
    """
    Execute ICP-driven PredictHQ queries.

    PredictHQ's value-add over Ticketmaster/Eventbrite:
      - phq_attendance: AI-predicted attendance (most accurate estimate)
      - Covers events not on mainstream ticketing platforms
      - B2B conferences, expos, trade shows globally
      - PHQ AI labels: richer industry classification than TM/EB

    Steps:
      1. Page through /v1/events/ sorted by -phq_attendance
         (most attended = most worth a sales trip)
      2. Filter: B2B categories + PHQ label check + attendance threshold
      3. Parse → normalise() → 28-column dict
      4. Dedup by dedup_hash

    Args:
        queries:   PredictHQQuery objects from icp_query_builder
        api_key:   PREDICTHQ_KEY env var (Bearer token)
        date_from: ISO date lower bound (ICP form window start)
        date_to:   ISO date upper bound (ICP form window end)
        max_pages: Max pages per query (50 events/page, default 2 = 100/query)

    Returns:
        List of normalised 28-column dicts for crud.batch_upsert_events()
    """
    if not api_key:
        logger.warning("PredictHQ: PREDICTHQ_KEY not set — skipping")
        return []

    today      = date.today().isoformat()
    seen_hash: set[str]  = set()
    results:   list[dict]= []
    abort:     bool      = False

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept":        "application/json",
    }

    async with httpx.AsyncClient(
        headers          = headers,
        timeout          = httpx.Timeout(20.0, connect=5.0),
        follow_redirects = True,
    ) as client:

        for q in queries:
            if abort or len(results) >= MAX_EVENTS_PER_SEARCH:
                break

            start_bound = q.start_gte or date_from or today
            end_bound   = q.end_lte   or date_to   or "2028-12-31"

            for page in range(max_pages):
                if abort or len(results) >= MAX_EVENTS_PER_SEARCH:
                    break

                offset = page * 50
                evs, total, next_url, fatal = await _fetch_page(
                    client       = client,
                    api_key      = api_key,
                    q            = q.q,
                    country_code = q.country_code,
                    start_gte    = start_bound,
                    end_lte      = end_bound,
                    offset       = offset,
                )

                if fatal:
                    abort = True
                    break

                if not evs:
                    break   # no more results for this query

                for ev in evs:
                    if not isinstance(ev, dict) or len(results) >= MAX_EVENTS_PER_SEARCH:
                        break

                    # ── Date window pre-filter ────────────────────────
                    start = str(ev.get("start_local") or ev.get("start") or "")[:10]
                    if not start or start < today:
                        continue
                    if date_from and start < date_from: continue
                    if date_to   and start > date_to:   continue

                    # ── Parse → normalise → dedup ─────────────────────
                    try:
                        raw = _parse_event(ev, q.q)
                        if raw is None:
                            continue

                        # Pass the PredictHQ ID into dedup_hash generation.
                        # PHQ events have stable IDs — we use them for dedup
                        # rather than the name+date+city hash which can collide
                        # for recurring events.
                        phq_id = raw.pop("_phq_id", "")
                        if phq_id:
                            import hashlib
                            raw["dedup_hash"] = hashlib.sha1(
                                f"phq:{phq_id}".encode()
                            ).hexdigest()

                        clean = normalise(raw, "PredictHQ")
                        dh    = clean["dedup_hash"]
                        if dh in seen_hash:
                            continue
                        seen_hash.add(dh)
                        results.append(clean)

                    except Exception as exc:
                        logger.debug(f"PHQ parse '{ev.get('title','?')[:40]}': {exc}")

                # No next page or we have enough
                if not next_url or len(results) >= MAX_EVENTS_PER_SEARCH:
                    break

                await asyncio.sleep(0.3)   # polite pause between pages

            await asyncio.sleep(0.3)       # polite pause between queries

    logger.info(
        f"PredictHQ: {len(results)} B2B events from {len(queries)} queries"
    )
    return results
