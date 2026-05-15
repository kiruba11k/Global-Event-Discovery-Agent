"""
ingestion/eventbrite_realtime.py  —  Eventbrite real-time B2B event search

Uses lat/lon search exclusively (country-code search returns 404 on Eventbrite v3).
Free with Eventbrite account.
Docs: https://www.eventbrite.com/platform/api#/reference/event/search
"""
from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import date
from typing import Optional

import httpx
from loguru import logger

from ingestion.icp_query_builder import EventbriteQuery
from models.event import EventCreate

BASE = "https://www.eventbriteapi.com/v3/events/search/"


def _to_event_create(ev: dict, keyword: str) -> Optional[EventCreate]:
    name = (ev.get("name", {}).get("text") or "").strip()
    if not name:
        return None

    start = (ev.get("start", {}).get("local") or "")[:10]
    if not start or start < date.today().isoformat():
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
    price_desc = "Free" if is_free else (f"From ${price:.0f}" if price > 0 else "")

    desc = (ev.get("description", {}).get("text") or "")[:600]
    link = ev.get("url", "")
    dh   = hashlib.sha1(f"{name.lower().strip()}|{start}|{city.lower().strip()}".encode()).hexdigest()

    return EventCreate(
        id              = str(uuid.uuid4()),
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
        industry_tags   = keyword,
        related_industries = keyword,
        audience_personas  = "",
        ticket_price_usd   = price,
        price_description  = price_desc,
        registration_url   = link,
        website            = link,
        sponsors = "", speakers_url = "", agenda_url = "",
    )


async def run_eventbrite_queries(
    queries:  list[EventbriteQuery],
    token:    str,
    date_from: str = "",
    date_to:   str = "",
) -> list[EventCreate]:
    if not token:
        return []

    today     = date.today().isoformat()
    all_events: list[EventCreate] = []
    seen:       set[str]          = set()
    ok = 0; endpoint_dead = False

    headers = {"Authorization": f"Bearer {token}"}
    start_dt = f"{date_from or today}T00:00:00Z"

    async with httpx.AsyncClient(headers=headers, timeout=12) as client:
        for q in queries:
            if endpoint_dead:
                break
            try:
                r = await client.get(BASE, params={
                    "q":                      q.keyword,
                    "location.latitude":      q.lat,
                    "location.longitude":     q.lon,
                    "location.within":        q.radius,
                    "start_date.range_start": start_dt,
                    "expand":                 "venue,ticket_availability",
                    "page_size":              50,
                    "sort_by":                "date",
                })

                if r.status_code == 404:
                    logger.debug("Eventbrite: endpoint 404 — stopping")
                    endpoint_dead = True
                    break
                if r.status_code == 401:
                    logger.warning("Eventbrite: invalid token")
                    break
                if not r.is_success:
                    logger.debug(f"Eventbrite '{q.keyword}': HTTP {r.status_code}")
                    await asyncio.sleep(0.3)
                    continue

                raw = r.json().get("events", []) or []
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
                        logger.debug(f"Eventbrite parse: {exc}")

                await asyncio.sleep(0.3)

            except httpx.HTTPStatusError as exc:
                if "404" in str(exc):
                    endpoint_dead = True
                    break
            except httpx.TimeoutException:
                logger.debug(f"Eventbrite timeout '{q.keyword}'")
            except Exception as exc:
                logger.debug(f"Eventbrite error '{q.keyword}': {exc}")

    logger.info(f"Eventbrite: {len(all_events)} events ({ok} ok queries)")
    return all_events
