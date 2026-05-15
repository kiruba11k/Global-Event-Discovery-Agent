"""
ingestion/serpapi_events.py

Real-time event discovery using SerpAPI google_events engine.

google_events searches Google's live event index — the same results you'd
see when googling "Tech conference Singapore 2026". Updated in real-time.
Returns events from Eventbrite, Meetup, LinkedIn Events, official sites, etc.

Strategy:
  Build targeted queries from ICP (industry × geography × event type).
  Fire up to 12 queries per search request.
  Each query returns up to 10 events.
  Total: up to 120 fresh real-time events per search.
"""
import asyncio
import hashlib
import uuid
import re
from datetime import date, datetime
from typing import List, Optional

from models.event import EventCreate
from loguru import logger


# ── Geography → Google country code mapping ────────────────
GEO_TO_GL: dict = {
    "singapore":      "sg",
    "india":          "in",
    "usa":            "us",
    "united states":  "us",
    "uk":             "gb",
    "united kingdom": "gb",
    "australia":      "au",
    "germany":        "de",
    "uae":            "ae",
    "dubai":          "ae",
    "malaysia":       "my",
    "japan":          "jp",
    "canada":         "ca",
    "france":         "fr",
    "netherlands":    "nl",
    "spain":          "es",
    "brazil":         "br",
    "south korea":    "kr",
    "korea":          "kr",
    "china":          "cn",
    "indonesia":      "id",
    "thailand":       "th",
    "vietnam":        "vn",
    "hong kong":      "hk",
    "south africa":   "za",
}

MONTHS_SHORT: dict = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}


def _parse_google_date(text: str) -> Optional[str]:
    """
    Parse Google Events date strings into YYYY-MM-DD.
    Handles: "Oct 14", "Oct 14, 2026", "Wed, Oct 14", "2026-10-14"
    """
    if not text:
        return None
    t = text.strip()

    # ISO already
    m = re.search(r"(\d{4}-\d{2}-\d{2})", t)
    if m:
        return m.group(1)

    # "Month DD, YYYY"
    m = re.search(
        r"(\w{3,9})\s+(\d{1,2}),?\s+(\d{4})", t, re.IGNORECASE
    )
    if m:
        mon = MONTHS_SHORT.get(m.group(1)[:3].lower(), "01")
        return f"{m.group(3)}-{mon}-{m.group(2).zfill(2)}"

    # "Month DD" (no year — assume current or next year)
    m = re.search(r"(\w{3,9})\s+(\d{1,2})", t, re.IGNORECASE)
    if m:
        mon = MONTHS_SHORT.get(m.group(1)[:3].lower())
        if mon:
            day  = m.group(2).zfill(2)
            year = date.today().year
            candidate = f"{year}-{mon}-{day}"
            if candidate < date.today().isoformat():
                candidate = f"{year + 1}-{mon}-{day}"
            return candidate

    return None


def _clean_industry(industry: str) -> str:
    """'AI / Machine Learning' → 'AI Machine Learning'"""
    return re.sub(r"[/|]", " ", industry).strip()


def _build_queries(profile) -> list:
    """
    Build targeted google_events search queries from ICP profile.
    Returns list of {q, gl, location} dicts.
    Max 12 queries to stay within SerpAPI free tier.
    """
    queries    = []
    industries = profile.target_industries[:3]
    geos       = profile.target_geographies[:4]
    evt_types  = profile.preferred_event_types[:2] or ["conference", "summit"]
    year       = date.today().year

    for geo in geos:
        geo_lower = geo.lower()
        is_global = geo_lower in ("global", "worldwide", "international", "any")
        gl        = GEO_TO_GL.get(geo_lower, "us")

        for industry in industries:
            ind_clean = _clean_industry(industry)
            evt_type  = evt_types[0] if evt_types else "conference"

            if is_global:
                q = f"{ind_clean} {evt_type} {year}"
                queries.append({"q": q, "gl": "us", "location": ""})
            else:
                q = f"{ind_clean} {evt_type} {geo} {year}"
                queries.append({"q": q, "gl": gl, "location": geo})

    # Additional persona-based queries (catches niche C-suite events)
    for persona in profile.target_personas[:2]:
        persona_clean = persona.split("(")[0].strip()
        if persona_clean:
            q = f"{persona_clean} conference summit {year}"
            queries.append({"q": q, "gl": "us", "location": ""})

    # Deduplicate and cap
    seen = set()
    unique = []
    for qd in queries:
        if qd["q"] not in seen:
            seen.add(qd["q"])
            unique.append(qd)
    return unique[:12]


def _parse_one_event(result: dict) -> Optional[EventCreate]:
    """Parse a single google_events result into EventCreate."""
    title = (result.get("title") or "").strip()
    if not title or len(title) < 4:
        return None

    # Date
    date_info  = result.get("date", {})
    start_raw  = date_info.get("start_date", "") or date_info.get("when", "")
    start_date = _parse_google_date(start_raw)
    if not start_date:
        return None
    if start_date < date.today().isoformat():
        return None   # skip past events

    # End date (optional)
    end_raw  = date_info.get("end_date", "")
    end_date = _parse_google_date(end_raw) or start_date

    # Location
    address    = result.get("address", [])
    venue_info = result.get("venue", {})
    venue_name = (venue_info.get("name") or "").strip()
    city       = address[0].strip() if address else ""
    country    = address[-1].strip() if len(address) > 1 else ""

    # Link
    link = result.get("link", "") or ""

    # Ticket info
    ticket_info   = result.get("ticket_info", [])
    price_desc    = "See website"
    registration  = link
    if ticket_info:
        first = ticket_info[0]
        src   = (first.get("source") or "").lower()
        tlink = first.get("link") or link
        if tlink:
            registration = tlink
        if "free" in src or "free" in title.lower():
            price_desc = "Free"

    description = (result.get("description") or "").strip()[:1000]

    # Industry from event type / description (rough tagger)
    industry = _infer_industry(title + " " + description)

    # Dedup hash
    dh = hashlib.md5(
        f"{title.lower().strip()}|{start_date}|{city.lower().strip()}".encode()
    ).hexdigest()

    return EventCreate(
        id=str(uuid.uuid4()),
        source_platform="Google Events",
        source_url=link,
        dedup_hash=dh,
        name=title,
        description=description,
        short_summary="",
        edition_number="",
        start_date=start_date,
        end_date=end_date,
        duration_days=1,
        venue_name=venue_name,
        address=", ".join(address),
        city=city,
        country=country,
        is_virtual=False,
        is_hybrid=False,
        est_attendees=0,
        category="conference",
        industry_tags=industry,
        related_industries=industry,
        audience_personas="executives,professionals,business leaders",
        ticket_price_usd=0.0,
        price_description=price_desc,
        registration_url=registration,
        website=link,
        sponsors="",
        speakers_url="",
        agenda_url="",
    )


_INDUSTRY_KEYWORDS: dict = {
    "tech,software,AI":          ["tech", "technology", "software", "digital", "ai", "artificial intelligence", "cloud", "saas", "devops", "data"],
    "fintech,banking,finance":   ["fintech", "banking", "finance", "financial", "payments", "lending", "insurance", "blockchain", "crypto"],
    "healthcare,medtech":        ["health", "medical", "healthcare", "medtech", "pharma", "biotech", "clinical", "hospital"],
    "logistics,supply chain":    ["logistics", "supply chain", "freight", "shipping", "warehousing", "transport"],
    "manufacturing,industrial":  ["manufacturing", "industrial", "factory", "automation", "robotics", "industry 4.0"],
    "retail,ecommerce":          ["retail", "ecommerce", "e-commerce", "consumer", "omnichannel", "d2c"],
    "energy,cleantech":          ["energy", "solar", "renewable", "cleantech", "sustainability", "climate", "esg"],
    "marketing,advertising":     ["marketing", "advertising", "martech", "brand", "content", "seo", "media"],
    "HR tech,talent":            ["hr", "human resources", "talent", "workforce", "people ops", "recruitment"],
    "cybersecurity,infosec":     ["security", "cybersecurity", "infosec", "ciso", "threat"],
    "real estate,construction":  ["real estate", "property", "construction", "architecture"],
    "education,edtech":          ["education", "edtech", "learning", "academic", "university"],
}


def _infer_industry(text: str) -> str:
    t = text.lower()
    for industry, keywords in _INDUSTRY_KEYWORDS.items():
        if any(k in t for k in keywords):
            return industry
    return "conference,business"


# ── Main async search ──────────────────────────────────────

async def search_google_events(
    profile,
    serpapi_key: str,
) -> List[EventCreate]:
    """
    Query SerpAPI google_events for real-time events matching the ICP.
    Returns a list of EventCreate objects ready to store in DB.
    """
    if not serpapi_key:
        logger.warning("SerpAPI key not set — skipping google_events search.")
        return []

    queries = _build_queries(profile)
    logger.info(
        f"Google Events: firing {len(queries)} queries for "
        f"{profile.company_name}"
    )

    events: List[EventCreate] = []
    seen:   set               = set()

    for qd in queries:
        try:
            result = await asyncio.to_thread(_call_google_events, qd, serpapi_key, profile)
            for ev in result:
                if ev.dedup_hash not in seen:
                    seen.add(ev.dedup_hash)
                    events.append(ev)
            # Small delay to be polite to SerpAPI
            await asyncio.sleep(0.4)
        except Exception as e:
            logger.debug(f"Google Events [{qd['q'][:40]}]: {e}")

    logger.info(
        f"Google Events: {len(events)} unique real-time events from "
        f"{len(queries)} queries."
    )
    return events


def _call_google_events(qd: dict, serpapi_key: str, profile) -> List[EventCreate]:
    """Synchronous SerpAPI call — runs in a thread pool."""
    import serpapi as _serpapi

    params: dict = {
        "engine": "google_events",
        "q":      qd["q"],
        "hl":     "en",
        "gl":     qd.get("gl", "us"),
    }
    if qd.get("location"):
        params["location"] = qd["location"]

    # Date filter: start from ICP date_from or today
    start_from = getattr(profile, "date_from", None) or date.today().isoformat()
    # SerpAPI google_events supports htichips for date filtering
    # but results must be post-filtered since htichips is coarse
    params["htichips"] = "event_type:Event"

    client      = _serpapi.Client(api_key=serpapi_key)
    raw_results = client.search(params)
    events_data = raw_results.get("events_results", [])

    parsed = []
    for item in events_data:
        ev = _parse_one_event(item)
        if ev:
            # Post-filter by date range
            if profile.date_from and ev.start_date < profile.date_from:
                continue
            if profile.date_to and ev.start_date > profile.date_to:
                continue
            parsed.append(ev)

    logger.debug(
        f"Google Events [{qd['q'][:40]}]: {len(parsed)}/{len(events_data)} events."
    )
    return parsed
