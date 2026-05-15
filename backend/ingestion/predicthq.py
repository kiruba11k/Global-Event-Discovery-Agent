"""
ingestion/predicthq.py  —  PredictHQ real-time event intelligence

PredictHQ provides high-quality event intelligence including:
  - Conferences, expos, trade shows, summits
  - Industry categorisation
  - Attendance predictions
  - 200+ countries coverage

Free tier: 1,000 events/month
Sign up:   https://www.predicthq.com/signup  (no credit card)
API docs:  https://docs.predicthq.com/

Key env var: PREDICTHQ_KEY

Example search:
  GET /v1/events/?q=technology+conference&country=SG&start.gte=2026-06-01
  Returns events with predicted_event_spend, phq_attendance (predicted), category
"""
from __future__ import annotations

import asyncio
import hashlib
import re
import uuid
from datetime import date, datetime
from typing import Optional

import httpx
from loguru import logger

from models.event import EventCreate

BASE_URL = "https://api.predicthq.com/v1/events/"

# PredictHQ event categories that map to B2B events
B2B_CATEGORIES = [
    "conferences",
    "expos",
    "community",
]

# Country code mapping for PredictHQ
_COUNTRY_CODES: dict[str, str] = {
    "Indonesia": "ID", "Singapore": "SG", "India": "IN",
    "USA": "US", "United States": "US", "UK": "GB", "United Kingdom": "GB",
    "Germany": "DE", "France": "FR", "Australia": "AU", "Japan": "JP",
    "UAE": "AE", "United Arab Emirates": "AE", "Malaysia": "MY",
    "South Korea": "KR", "Canada": "CA", "Brazil": "BR",
    "Netherlands": "NL", "Spain": "ES", "Italy": "IT", "China": "CN",
    "Thailand": "TH", "Philippines": "PH", "Vietnam": "VN",
    "South Africa": "ZA", "Kenya": "KE", "Nigeria": "NG",
    "Saudi Arabia": "SA", "Turkey": "TR", "Mexico": "MX",
    "Argentina": "AR", "Colombia": "CO", "Poland": "PL",
    "Sweden": "SE", "Norway": "NO", "Denmark": "DK", "Finland": "FI",
    "Switzerland": "CH", "Belgium": "BE", "Austria": "AT",
}

# Industry keyword → PredictHQ search terms
_IND_TO_QUERY: dict[str, list[str]] = {
    "Technology":           ["technology", "digital", "software", "IT"],
    "AI / Machine Learning": ["artificial intelligence", "machine learning", "AI"],
    "Cloud Computing":      ["cloud computing", "SaaS", "cloud"],
    "Cybersecurity":        ["cybersecurity", "security", "infosec"],
    "Manufacturing":        ["manufacturing", "industrial", "factory"],
    "Logistics / Supply Chain": ["logistics", "supply chain", "procurement"],
    "Healthcare / Medtech": ["healthcare", "medical", "health", "pharma"],
    "Fintech":              ["fintech", "finance", "banking", "payments"],
    "Retail / Ecommerce":   ["retail", "ecommerce", "consumer"],
    "Energy / Cleantech":   ["energy", "renewable", "climate"],
    "Data & Analytics":     ["data analytics", "big data", "analytics"],
    "HR Tech":              ["HR technology", "talent", "workforce"],
    "Marketing":            ["marketing", "advertising", "martech"],
}


def _dedup_hash(name: str, start_date: str, city: str) -> str:
    raw = f"{name.lower().strip()}|{start_date}|{city.lower().strip()}"
    return hashlib.sha1(raw.encode()).hexdigest()


def _phq_to_event_create(event: dict) -> Optional[EventCreate]:
    """Convert PredictHQ event dict to EventCreate."""
    title = (event.get("title") or "").strip()
    if not title or len(title) < 4:
        return None

    start = (event.get("start") or "")[:10]
    end   = (event.get("end")   or start)[:10]
    today = date.today().isoformat()

    if not start or start < today:
        return None

    # Location
    geo = event.get("geo") or {}
    loc = event.get("location") or []
    lon = geo.get("lon") or (loc[0] if loc and len(loc) > 0 else 0)
    lat = geo.get("lat") or (loc[1] if loc and len(loc) > 1 else 0)

    place = event.get("place_hierarchies") or []
    city    = ""
    country = ""
    state   = ""
    if place:
        # PredictHQ hierarchy: [country, state, city, ...]
        flat = place[0] if isinstance(place[0], list) else place
        # Try entities for structured location
        for ent in (event.get("entities") or []):
            if ent.get("type") == "city":
                city = ent.get("name", "")
            elif ent.get("type") == "country":
                country = ent.get("name", "")

    # Fallback: country from event
    if not country:
        country = event.get("country", "")

    # Attendance (predicted by PHQ)
    att = event.get("phq_attendance") or 0

    # Category
    cat = (event.get("category") or "conference").lower()
    cat_map = {"conferences": "conference", "expos": "expo", "community": "meetup"}
    category = cat_map.get(cat, cat)

    # Labels → industry tags
    labels = event.get("labels") or []
    ind_tags = ", ".join(l.replace("-", " ").title() for l in labels[:6]) if labels else "Business Events"

    # Description
    desc = ""
    for ent in (event.get("entities") or []):
        if ent.get("type") == "venue":
            venue_name = ent.get("name", "")
            break
    else:
        venue_name = ""

    link = (event.get("event_url") or
            f"https://www.google.com/search?q={title.replace(' ', '+')}")

    event_id = str(uuid.uuid4())
    dh = _dedup_hash(title, start, city)

    return EventCreate(
        id              = event_id,
        dedup_hash      = dh,
        source_platform = "PredictHQ",
        source_url      = link,
        name            = title,
        description     = f"{title} — {category} in {city}, {country}. Category: {', '.join(labels[:3]) or category}.",
        short_summary   = "",
        edition_number  = "",
        start_date      = start,
        end_date        = end,
        duration_days   = max(1, (
            (datetime.strptime(end, "%Y-%m-%d") - datetime.strptime(start, "%Y-%m-%d")).days + 1
            if end and end != start else 1
        )),
        venue_name      = venue_name,
        event_venues    = venue_name,
        address         = "",
        city            = city,
        country         = country,
        event_cities    = f"{city}, {country}".strip(", "),
        is_virtual      = False,
        is_hybrid       = False,
        est_attendees   = int(att) if att else 0,
        category        = category,
        industry_tags   = ind_tags,
        related_industries = ind_tags,
        audience_personas = "",
        ticket_price_usd = 0.0,
        price_description = "",
        registration_url = link,
        website         = link,
        sponsors        = "",
        speakers_url    = "",
        agenda_url      = "",
    )


async def search_predicthq(
    api_key:     str,
    industries:  list[str],
    geographies: list[str],
    date_from:   str = "",
    date_to:     str = "",
    limit:       int = 50,
) -> list[EventCreate]:
    """
    Search PredictHQ for B2B events matching the ICP profile.

    Docs: https://docs.predicthq.com/api/events/search-events
    """
    if not api_key:
        return []

    today = date.today().isoformat()
    start_gte = date_from or today
    end_lte   = date_to   or "2028-12-31"

    # Build country list
    country_codes: list[str] = []
    for geo in geographies:
        if geo.lower() in ("global", "worldwide", "international", "any"):
            break  # no country filter
        code = _COUNTRY_CODES.get(geo)
        if code:
            country_codes.append(code)

    # Build keyword queries
    queries: list[str] = []
    for ind in industries[:4]:
        terms = _IND_TO_QUERY.get(ind, [ind.lower()])
        queries.extend(terms[:2])
    if not queries:
        queries = ["technology conference", "business summit"]

    all_events: list[EventCreate] = []
    seen_hashes: set[str] = set()

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept":        "application/json",
    }

    async with httpx.AsyncClient(headers=headers, timeout=15) as client:
        for q in queries[:6]:
            params: dict = {
                "q":          q,
                "start.gte":  start_gte,
                "end.lte":    end_lte,
                "category":   ",".join(B2B_CATEGORIES),
                "limit":      min(limit, 50),
                "sort":       "phq_attendance",
                "active.gte": start_gte,
            }
            if country_codes:
                params["country"] = ",".join(country_codes[:5])

            try:
                r = await client.get(BASE_URL, params=params)
                if r.status_code == 401:
                    logger.warning("PredictHQ: invalid API key")
                    break
                if r.status_code == 429:
                    logger.warning("PredictHQ: rate limited")
                    await asyncio.sleep(2)
                    continue
                if not r.is_success:
                    logger.debug(f"PredictHQ {q}: HTTP {r.status_code}")
                    continue

                data = r.json()
                raw_events = data.get("results", []) or []

                for ev in raw_events:
                    try:
                        ec = _phq_to_event_create(ev)
                        if ec and ec.dedup_hash not in seen_hashes:
                            seen_hashes.add(ec.dedup_hash)
                            all_events.append(ec)
                    except Exception as exc:
                        logger.debug(f"PredictHQ parse error: {exc}")

                logger.debug(f"PredictHQ '{q}': {len(raw_events)} raw, {len(all_events)} total")
                await asyncio.sleep(0.3)

            except httpx.TimeoutException:
                logger.debug(f"PredictHQ timeout for '{q}'")
            except Exception as exc:
                logger.warning(f"PredictHQ error for '{q}': {exc}")

    logger.info(f"PredictHQ: {len(all_events)} events fetched")
    return all_events
