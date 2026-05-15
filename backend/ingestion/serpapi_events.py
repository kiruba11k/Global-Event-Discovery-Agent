"""
ingestion/serpapi_events.py  —  Real-time event discovery via SerpAPI google_events

This is the PRIMARY real-time source.  It calls the SerpAPI `google_events`
engine which mirrors what you see when you Google "technology conference Jakarta".
Returns fully-structured event data including dates, venue, description, and link.

Engine: google_events (included in all SerpAPI plans, uses 1 credit per call)
Key: SERPAPI_KEY (already in env)
Docs: https://serpapi.com/google-events-api

Typical result per event:
  {
    "title": "Indonesia Tech Week 2026",
    "date": {"start_date": "Oct 14", "when": "Oct 14 – 16, 2026"},
    "address": ["Jakarta Convention Centre", "Jakarta, Indonesia"],
    "link": "https://...",
    "description": "...",
    "ticket_info": [{"source": "Official Site", "link": "..."}],
  }
"""
from __future__ import annotations

import asyncio
import hashlib
import re
import uuid
from datetime import date, datetime
from typing import Optional

from loguru import logger

try:
    import serpapi as _serpapi
    _SERPAPI_OK = True
except ImportError:
    _SERPAPI_OK = False
    logger.warning("serpapi not installed — run: pip install serpapi")

from models.event import EventCreate

# ── Month parsing ──────────────────────────────────────────────────
_MONTHS = {
    "jan": "01", "january": "01", "feb": "02", "february": "02",
    "mar": "03", "march": "03", "apr": "04", "april": "04",
    "may": "05", "jun": "06", "june": "06", "jul": "07", "july": "07",
    "aug": "08", "august": "08", "sep": "09", "sept": "09", "september": "09",
    "oct": "10", "october": "10", "nov": "11", "november": "11",
    "dec": "12", "december": "12",
}


def _parse_google_events_date(date_info: dict) -> tuple[str, str]:
    """
    Parse Google Events date dict → (start_date, end_date) as ISO strings.
    Handles: "Oct 14 – 16, 2026", "Oct 14, 2026", "Oct 14 – Nov 2, 2026"
    """
    when = date_info.get("when", "") or date_info.get("start_date", "") or ""
    when = str(when).strip()
    if not when:
        return "", ""

    # Try to extract year
    year_match = re.search(r"\b(202\d|203\d)\b", when)
    year = year_match.group(1) if year_match else str(date.today().year + 1)

    # "Oct 14 – 16, 2026" → start Oct 14, end Oct 16
    m1 = re.match(
        r"(\w+)\s+(\d{1,2})\s*[–\-]\s*(\d{1,2}),?\s*(202\d|203\d)?", when, re.I
    )
    if m1:
        mon  = _MONTHS.get(m1.group(1).lower()[:3], "01")
        sd   = m1.group(2).zfill(2)
        ed   = m1.group(3).zfill(2)
        yr   = m1.group(4) or year
        return f"{yr}-{mon}-{sd}", f"{yr}-{mon}-{ed}"

    # "Oct 14 – Nov 2, 2026" → different months
    m2 = re.match(
        r"(\w+)\s+(\d{1,2})\s*[–\-]\s*(\w+)\s+(\d{1,2}),?\s*(202\d|203\d)?", when, re.I
    )
    if m2:
        smon = _MONTHS.get(m2.group(1).lower()[:3], "01")
        sd   = m2.group(2).zfill(2)
        emon = _MONTHS.get(m2.group(3).lower()[:3], smon)
        ed   = m2.group(4).zfill(2)
        yr   = m2.group(5) or year
        return f"{yr}-{smon}-{sd}", f"{yr}-{emon}-{ed}"

    # "Oct 14, 2026" single day
    m3 = re.match(r"(\w+)\s+(\d{1,2}),?\s*(202\d|203\d)?", when, re.I)
    if m3:
        mon = _MONTHS.get(m3.group(1).lower()[:3], "01")
        sd  = m3.group(2).zfill(2)
        yr  = m3.group(3) or year
        return f"{yr}-{mon}-{sd}", f"{yr}-{mon}-{sd}"

    return "", ""


def _dedup_hash(name: str, start_date: str, city: str) -> str:
    raw = f"{name.lower().strip()}|{start_date}|{city.lower().strip()}"
    return hashlib.sha1(raw.encode()).hexdigest()


def _extract_city_country(address: list[str]) -> tuple[str, str]:
    """
    Google Events address is usually:
      ["Venue Name", "City, Country"] or ["City, Country"] or ["Venue, City, Country"]
    """
    if not address:
        return "", ""
    # Last element usually has city/country
    last = address[-1] if address else ""
    parts = [p.strip() for p in last.split(",") if p.strip()]
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    if len(parts) == 1:
        return parts[0], ""
    return "", ""


def _best_link(event_data: dict) -> str:
    """Extract the best official event link from google_events result."""
    # ticket_info often has the official site link
    for ti in (event_data.get("ticket_info") or []):
        link = ti.get("link", "")
        if link and "google.com" not in link.lower():
            return link
    # Fallback: main link
    return event_data.get("link", "") or ""


def _google_event_to_event_create(
    event_data: dict,
    query_industry: str = "",
    query_geo: str = "",
) -> Optional[EventCreate]:
    """Convert a google_events result dict to EventCreate."""
    title = (event_data.get("title") or "").strip()
    if not title or len(title) < 4:
        return None

    date_info = event_data.get("date") or {}
    start_date, end_date = _parse_google_events_date(date_info)

    # Skip past events
    today = date.today().isoformat()
    if start_date and start_date < today:
        return None

    # If no parseable date, skip — we need at least a year
    if not start_date:
        # Try extracting year from title or description
        desc = event_data.get("description", "") or ""
        yr_m = re.search(r"\b(202\d|203\d)\b", title + " " + desc)
        if yr_m:
            start_date = f"{yr_m.group(1)}-01-01"
            end_date   = start_date
        else:
            return None

    address  = event_data.get("address") or []
    venue_name = address[0].strip() if address else ""
    city, country = _extract_city_country(address)

    # If city not found from address, try query geo
    if not city and query_geo:
        city = query_geo

    description = (event_data.get("description") or "").strip()[:800]
    link = _best_link(event_data)
    thumbnail = event_data.get("thumbnail", "") or ""

    # Infer industry tags from title + description
    industry_tags = _infer_industry_tags(title + " " + description, query_industry)

    event_id = str(uuid.uuid4())
    dh = _dedup_hash(title, start_date, city)

    return EventCreate(
        id              = event_id,
        dedup_hash      = dh,
        source_platform = "SerpAPI_GoogleEvents",
        source_url      = link or f"https://www.google.com/search?q={title.replace(' ', '+')}",
        name            = title,
        description     = description or f"Event sourced from Google Events for query: {query_industry} {query_geo}",
        short_summary   = description[:200] if description else "",
        edition_number  = "",
        start_date      = start_date,
        end_date        = end_date or start_date,
        duration_days   = max(1, (
            (datetime.strptime(end_date, "%Y-%m-%d") - datetime.strptime(start_date, "%Y-%m-%d")).days + 1
            if end_date and end_date != start_date else 1
        )),
        venue_name      = venue_name,
        event_venues    = venue_name,
        address         = ", ".join(address),
        city            = city,
        country         = country,
        event_cities    = f"{city}, {country}".strip(", "),
        is_virtual      = any(v in title.lower() + description.lower() for v in ["virtual", "online", "webinar"]),
        is_hybrid       = "hybrid" in title.lower() + description.lower(),
        est_attendees   = 0,   # filled by SerpAPI enricher
        category        = _infer_category(title + " " + description),
        industry_tags   = industry_tags,
        related_industries = industry_tags,
        audience_personas = "",  # filled by enricher
        ticket_price_usd = 0.0,
        price_description = "",  # filled by enricher
        registration_url = link,
        website         = link,
        sponsors        = "",
        speakers_url    = "",
        agenda_url      = "",
    )


def _infer_industry_tags(text: str, query_industry: str) -> str:
    """Infer industry tags from event text + original search query."""
    tags: list[str] = []
    t = text.lower()
    if query_industry:
        tags.append(query_industry)
    kw_map = [
        (["ai", "artificial intelligence", "machine learning", "deep learning"], "AI / Machine Learning"),
        (["cloud", "saas", "paas", "devops", "kubernetes"], "Cloud Computing"),
        (["cybersecurity", "security", "infosec", "cyber"], "Cybersecurity"),
        (["fintech", "banking", "finance", "payment", "blockchain"], "Finance / Fintech"),
        (["health", "medical", "pharma", "biotech", "medtech"], "Healthcare / Medtech"),
        (["manufactur", "industrial", "factory", "automation", "robotics"], "Manufacturing"),
        (["logistics", "supply chain", "freight", "warehouse"], "Logistics"),
        (["retail", "ecommerce", "consumer"], "Retail / Ecommerce"),
        (["marketing", "advertising", "martech"], "Marketing"),
        (["hr", "talent", "workforce", "recruitment"], "HR Tech"),
        (["startup", "venture", "entrepreneur", "founder"], "Startup / VC"),
        (["tech", "technology", "digital", "software", "developer"], "Technology"),
        (["energy", "renewable", "solar", "green", "climate"], "Energy / Cleantech"),
        (["data", "analytics", "big data", "business intelligence"], "Data & Analytics"),
    ]
    for keywords, tag in kw_map:
        if any(kw in t for kw in keywords):
            if tag not in tags:
                tags.append(tag)
    return ", ".join(tags[:5]) if tags else "Business Events"


def _infer_category(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ["trade show", "expo", "exhibition", "tradeshow"]):
        return "trade show"
    if any(w in t for w in ["summit", "symposium"]):
        return "summit"
    if any(w in t for w in ["workshop", "bootcamp", "training"]):
        return "workshop"
    if any(w in t for w in ["hackathon"]):
        return "hackathon"
    if any(w in t for w in ["meetup", "networking", "mixer"]):
        return "meetup"
    return "conference"


# ── Core search function ───────────────────────────────────────────

async def search_google_events(
    query:       str,
    location:    str,
    serpapi_key: str,
    *,
    date_from:   str = "",
    date_to:     str = "",
    max_results: int = 20,
) -> list[EventCreate]:
    """
    Search Google Events via SerpAPI for a specific query + location.

    Args:
        query:       Search query, e.g. "technology conference"
        location:    Location, e.g. "Jakarta, Indonesia"
        serpapi_key: SerpAPI API key
        date_from:   ISO date string, optional filter
        date_to:     ISO date string, optional filter
        max_results: Max events to return per query
    """
    if not serpapi_key or not _SERPAPI_OK:
        return []

    # Build params
    params: dict = {
        "engine": "google_events",
        "q":      f"{query} {location}".strip(),
        "hl":     "en",
        "gl":     "us",
    }

    # Google Events supports "date:today", "date:week", "date:month", "date:next_week"
    # For broader ranges we use the 'htichips' parameter
    if date_from:
        # Parse year from date_from to add to query for better filtering
        yr = date_from[:4]
        if yr not in params["q"]:
            params["q"] += f" {yr}"

    try:
        client = _serpapi.Client(api_key=serpapi_key)
        raw = await asyncio.to_thread(client.search, params)
    except Exception as exc:
        logger.debug(f"SerpAPI google_events error for '{query} {location}': {exc}")
        return []

    events_raw = raw.get("events_results", []) or []
    if not events_raw:
        logger.debug(f"SerpAPI google_events: 0 results for '{query} {location}'")
        return []

    today = date.today().isoformat()
    results: list[EventCreate] = []
    seen: set[str] = set()

    for ev in events_raw[:max_results]:
        try:
            event_create = _google_event_to_event_create(
                ev,
                query_industry = query,
                query_geo      = location,
            )
            if event_create is None:
                continue
            # Date range filter
            if date_from and event_create.start_date < date_from:
                continue
            if date_to and event_create.start_date > date_to:
                continue
            # Future events only
            if event_create.start_date < today:
                continue
            # Dedup
            if event_create.dedup_hash in seen:
                continue
            seen.add(event_create.dedup_hash)
            results.append(event_create)
        except Exception as exc:
            logger.debug(f"SerpAPI google_events parse error: {exc}")

    logger.info(f"SerpAPI google_events: {len(results)} events for '{query} {location}'")
    return results


# ── Batch search from ICP profile ─────────────────────────────────

async def search_events_for_profile(
    serpapi_key:     str,
    industries:      list[str],
    geographies:     list[str],
    event_types:     list[str],
    date_from:       str = "",
    date_to:         str = "",
    company_desc:    str = "",
    max_queries:     int = 8,
    max_per_query:   int = 10,
) -> list[EventCreate]:
    """
    Generate targeted queries from ICP inputs and call google_events for each.
    Returns combined, deduplicated list of EventCreate objects.
    """
    if not serpapi_key or not _SERPAPI_OK:
        return []

    # Build industry search terms
    _IND_TERMS: dict[str, list[str]] = {
        "Technology":           ["technology conference", "tech summit", "digital innovation"],
        "AI / Machine Learning": ["AI conference", "machine learning summit", "artificial intelligence"],
        "Cloud Computing":      ["cloud computing conference", "cloud summit", "SaaS conference"],
        "Cybersecurity":        ["cybersecurity conference", "infosec summit", "security expo"],
        "Manufacturing":        ["manufacturing expo", "industrial trade show", "factory automation"],
        "Logistics / Supply Chain": ["logistics conference", "supply chain summit", "transport expo"],
        "Healthcare / Medtech": ["healthcare conference", "medtech summit", "health innovation"],
        "Fintech":              ["fintech conference", "financial technology summit", "payments expo"],
        "Retail / Ecommerce":   ["retail conference", "ecommerce summit", "retail technology"],
        "Energy / Cleantech":   ["energy conference", "cleantech summit", "renewable energy expo"],
        "Data & Analytics":     ["data analytics conference", "big data summit", "BI conference"],
        "HR Tech":              ["HR technology conference", "talent summit", "workforce expo"],
        "Marketing":            ["marketing conference", "martech summit", "digital marketing"],
        "Startup / VC":         ["startup conference", "venture capital summit", "founder expo"],
    }

    # Geo normalisation
    _GEO_TERMS: dict[str, list[str]] = {
        "Global":     ["Asia", "Europe", "USA", "Singapore", "UAE"],
        "Indonesia":  ["Jakarta Indonesia", "Surabaya Indonesia", "Indonesia"],
        "Singapore":  ["Singapore"],
        "India":      ["Bangalore India", "Mumbai India", "New Delhi India"],
        "USA":        ["New York USA", "San Francisco USA", "Chicago USA"],
        "UK":         ["London UK", "London United Kingdom"],
        "UAE":        ["Dubai UAE", "Abu Dhabi UAE"],
        "Germany":    ["Frankfurt Germany", "Berlin Germany", "Munich Germany"],
        "Australia":  ["Sydney Australia", "Melbourne Australia"],
        "Japan":      ["Tokyo Japan"],
        "Malaysia":   ["Kuala Lumpur Malaysia"],
        "South Korea":["Seoul South Korea"],
        "Brazil":     ["Sao Paulo Brazil"],
        "Canada":     ["Toronto Canada", "Vancouver Canada"],
        "France":     ["Paris France"],
    }

    # Extract year for queries
    year = date_from[:4] if date_from else str(date.today().year)

    # Build query combinations
    query_list: list[tuple[str, str]] = []  # (search_term, location)

    ind_terms: list[str] = []
    for ind in industries[:4]:
        terms = _IND_TERMS.get(ind, [f"{ind.lower()} conference"])
        ind_terms.extend(terms[:2])

    # If company description has useful keywords, extract them
    if company_desc:
        desc_lower = company_desc.lower()
        extra_terms = []
        kws = [
            ("supply chain", "supply chain conference"),
            ("erp", "ERP technology conference"),
            ("data pipeline", "data engineering summit"),
            ("fintech", "fintech conference"),
            ("saas", "SaaS conference"),
            ("cybersecurity", "cybersecurity summit"),
        ]
        for kw, term in kws:
            if kw in desc_lower:
                extra_terms.append(term)
        ind_terms = (extra_terms + ind_terms)[:6]

    if not ind_terms:
        ind_terms = ["technology conference", "business summit", "trade show"]

    geo_terms_all: list[str] = []
    for geo in geographies[:4]:
        terms = _GEO_TERMS.get(geo, [geo])
        geo_terms_all.extend(terms[:2])

    if not geo_terms_all:
        geo_terms_all = ["Global", "Asia", "USA"]

    # Build combos with year
    for term in ind_terms[:4]:
        for geo in geo_terms_all[:4]:
            q = f"{term} {year}"
            query_list.append((q, geo))
            if len(query_list) >= max_queries:
                break
        if len(query_list) >= max_queries:
            break

    # Execute queries sequentially (rate limit: 100/month free tier)
    all_events: list[EventCreate] = []
    seen_hashes: set[str] = set()

    logger.info(f"SerpAPI google_events: running {len(query_list)} targeted queries")

    for i, (query, location) in enumerate(query_list[:max_queries]):
        try:
            events = await search_google_events(
                query       = query,
                location    = location,
                serpapi_key = serpapi_key,
                date_from   = date_from,
                date_to     = date_to,
                max_results = max_per_query,
            )
            for ev in events:
                if ev.dedup_hash not in seen_hashes:
                    seen_hashes.add(ev.dedup_hash)
                    all_events.append(ev)
            # Small delay between calls
            if i < len(query_list) - 1:
                await asyncio.sleep(0.5)
        except Exception as exc:
            logger.warning(f"SerpAPI google_events batch error [{query}]: {exc}")

    logger.info(
        f"SerpAPI google_events total: {len(all_events)} unique events "
        f"from {min(len(query_list), max_queries)} queries"
    )
    return all_events
