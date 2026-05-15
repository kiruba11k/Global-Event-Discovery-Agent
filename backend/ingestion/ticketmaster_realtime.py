"""
ingestion/ticketmaster_realtime.py  —  Ticketmaster real-time B2B event search

Uses the ICP query builder to generate targeted keyword + country queries.
Free tier: 5,000 calls/day
API docs: https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/
"""
from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import date, datetime
from typing import Optional

import httpx
from loguru import logger

from ingestion.icp_query_builder import TicketmasterQuery
from models.event import EventCreate

BASE = "https://app.ticketmaster.com/discovery/v2/events.json"

# B2B-relevant classification segments to request
TM_SEGMENTS = ["Conference", "Business", "Technology", "Seminar", "Expo"]


def _to_event_create(ev: dict, keyword: str) -> Optional[EventCreate]:
    name = (ev.get("name") or "").strip()
    if not name:
        return None

    dates = ev.get("dates", {}).get("start", {})
    start = dates.get("localDate", "")
    if not start or start < date.today().isoformat():
        return None

    venues  = (ev.get("_embedded") or {}).get("venues", [{}])
    venue   = venues[0] if venues else {}
    city    = venue.get("city", {}).get("name", "")
    country = venue.get("country", {}).get("name", "")
    vname   = venue.get("name", "")
    addr    = venue.get("address", {}).get("line1", "")

    cls   = (ev.get("classifications") or [{}])[0]
    seg   = cls.get("segment", {}).get("name", "")
    genre = cls.get("genre", {}).get("name", "")
    ind   = f"{keyword}, {seg}, {genre}".strip(", ")

    prices    = ev.get("priceRanges", [])
    price_min = float(prices[0].get("min", 0)) if prices else 0.0
    price_desc = f"From ${price_min:.0f}" if price_min > 0 else ""

    link = ev.get("url", "")
    dh   = hashlib.sha1(f"{name.lower().strip()}|{start}|{city.lower().strip()}".encode()).hexdigest()

    return EventCreate(
        id              = str(uuid.uuid4()),
        dedup_hash      = dh,
        source_platform = "Ticketmaster",
        source_url      = link,
        name            = name,
        description     = (ev.get("info") or ev.get("pleaseNote") or f"{name} — {seg} event in {city}.").strip()[:600],
        short_summary   = "",
        edition_number  = "",
        start_date      = start,
        end_date        = start,
        duration_days   = 1,
        venue_name      = vname,
        event_venues    = vname,
        address         = addr,
        city            = city,
        country         = country,
        event_cities    = f"{city}, {country}".strip(", "),
        is_virtual      = False,
        is_hybrid       = False,
        est_attendees   = int(ev.get("capacity") or 0),
        category        = "conference",
        industry_tags   = ind,
        related_industries = ind,
        audience_personas  = "",
        ticket_price_usd   = price_min,
        price_description  = price_desc,
        registration_url   = link,
        website            = link,
        sponsors = "", speakers_url = "", agenda_url = "",
    )


async def run_ticketmaster_queries(
    queries:  list[TicketmasterQuery],
    api_key:  str,
    date_from: str = "",
    date_to:   str = "",
) -> list[EventCreate]:
    if not api_key:
        return []

    today     = date.today().isoformat()
    all_events: list[EventCreate] = []
    seen:       set[str]          = set()
    ok = 0; skip_404 = False

    async with httpx.AsyncClient(timeout=12) as client:
        for q in queries:
            if skip_404:
                break
            try:
                r = await client.get(BASE, params={
                    "apikey":         api_key,
                    "keyword":        q.keyword,
                    "countryCode":    q.country_code,
                    "startDateTime":  q.start_dt,
                    "endDateTime":    q.end_dt,
                    "size":           50,
                    "sort":           "date,asc",
                    "locale":         "en-us",
                    # B2B classification — use single most common value
                    "classificationName": "conference",
                })

                if r.status_code == 404:
                    logger.debug("Ticketmaster: 404 on endpoint — stopping")
                    skip_404 = True
                    break
                if r.status_code == 401:
                    logger.warning("Ticketmaster: invalid API key")
                    break
                if r.status_code == 429:
                    logger.warning("Ticketmaster: rate limited — pausing 5s")
                    await asyncio.sleep(5)
                    continue
                if not r.is_success:
                    logger.debug(f"Ticketmaster '{q.keyword}/{q.country_code}': HTTP {r.status_code}")
                    await asyncio.sleep(0.3)
                    continue

                raw = r.json().get("_embedded", {}).get("events", []) or []
                ok += 1
                for ev in raw:
                    try:
                        ec = _to_event_create(ev, q.keyword)
                        if ec and ec.start_date >= today and ec.dedup_hash not in seen:
                            if date_from and ec.start_date < date_from:
                                continue
                            if date_to   and ec.start_date > date_to:
                                continue
                            seen.add(ec.dedup_hash)
                            all_events.append(ec)
                    except Exception as exc:
                        logger.debug(f"Ticketmaster parse: {exc}")

                await asyncio.sleep(0.2)

            except httpx.TimeoutException:
                logger.debug(f"Ticketmaster timeout '{q.keyword}'")
            except Exception as exc:
                logger.debug(f"Ticketmaster error '{q.keyword}': {exc}")

    logger.info(f"Ticketmaster: {len(all_events)} events ({ok} ok queries)")
    return all_events
