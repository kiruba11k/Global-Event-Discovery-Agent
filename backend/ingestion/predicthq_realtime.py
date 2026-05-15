"""
ingestion/predicthq_realtime.py  —  PredictHQ real-time B2B event intelligence

Free tier: 1,000 events/month (no credit card required)
Signup:    https://www.predicthq.com/signup
Docs:      https://docs.predicthq.com/api/events/search-events

Returns conferences, expos with predicted attendance (phq_attendance).
Great for finding industry events not on mainstream platforms.
"""
from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import date, datetime
from typing import Optional

import httpx
from loguru import logger

from ingestion.icp_query_builder import PredictHQQuery
from models.event import EventCreate

BASE = "https://api.predicthq.com/v1/events/"
PHQ_B2B_CATEGORIES = "conferences,expos,community"


def _to_event_create(ev: dict) -> Optional[EventCreate]:
    title = (ev.get("title") or "").strip()
    if not title or len(title) < 4:
        return None

    start = (ev.get("start") or "")[:10]
    end   = (ev.get("end")   or start)[:10]
    today = date.today().isoformat()
    if not start or start < today:
        return None

    # Location via entities
    city = country = venue_name = ""
    for ent in (ev.get("entities") or []):
        if ent.get("type") == "city"    and not city:
            city = ent.get("name", "")
        elif ent.get("type") == "country" and not country:
            country = ent.get("name", "")
        elif ent.get("type") == "venue"  and not venue_name:
            venue_name = ent.get("name", "")

    # Fallback to country field
    if not country:
        country = ev.get("country", "")

    att      = int(ev.get("phq_attendance") or 0)
    labels   = ev.get("labels") or []
    category = (ev.get("category") or "conference").lower()
    cat_map  = {"conferences": "conference", "expos": "expo", "community": "meetup"}
    category = cat_map.get(category, category)
    ind_tags = ", ".join(lbl.replace("-", " ").title() for lbl in labels[:6]) if labels else "Business Events"

    link = (ev.get("event_url") or
            f"https://www.google.com/search?q={title.replace(' ', '+')}")
    dh   = hashlib.sha1(f"{title.lower().strip()}|{start}|{city.lower().strip()}".encode()).hexdigest()

    duration = 1
    if start and end and start != end:
        try:
            duration = max(1, (datetime.strptime(end, "%Y-%m-%d") - datetime.strptime(start, "%Y-%m-%d")).days + 1)
        except ValueError:
            pass

    return EventCreate(
        id              = str(uuid.uuid4()),
        dedup_hash      = dh,
        source_platform = "PredictHQ",
        source_url      = link,
        name            = title,
        description     = f"{title} — {category} in {city}, {country}. Tags: {', '.join(labels[:3]) or category}.",
        short_summary   = "",
        edition_number  = "",
        start_date      = start,
        end_date        = end,
        duration_days   = duration,
        venue_name      = venue_name,
        event_venues    = venue_name,
        address         = "",
        city            = city,
        country         = country,
        event_cities    = f"{city}, {country}".strip(", "),
        is_virtual      = False,
        is_hybrid       = False,
        est_attendees   = att,
        category        = category,
        industry_tags   = ind_tags,
        related_industries = ind_tags,
        audience_personas  = "",
        ticket_price_usd   = 0.0,
        price_description  = "",
        registration_url   = link,
        website            = link,
        sponsors = "", speakers_url = "", agenda_url = "",
    )


async def run_predicthq_queries(
    queries:  list[PredictHQQuery],
    api_key:  str,
    date_from: str = "",
    date_to:   str = "",
) -> list[EventCreate]:
    if not api_key:
        return []

    today     = date.today().isoformat()
    all_events: list[EventCreate] = []
    seen:       set[str]          = set()
    ok = 0

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept":        "application/json",
    }

    async with httpx.AsyncClient(headers=headers, timeout=15) as client:
        for q in queries:
            params: dict = {
                "q":          q.q,
                "start.gte":  q.start_gte,
                "end.lte":    q.end_lte,
                "category":   PHQ_B2B_CATEGORIES,
                "limit":      50,
                "sort":       "phq_attendance",
            }
            if q.country_code:
                params["country"] = q.country_code

            try:
                r = await client.get(BASE, params=params)
                if r.status_code == 401:
                    logger.warning("PredictHQ: invalid API key (check PREDICTHQ_KEY)")
                    break
                if r.status_code == 429:
                    logger.warning("PredictHQ: rate limited — pausing 3s")
                    await asyncio.sleep(3)
                    continue
                if not r.is_success:
                    logger.debug(f"PredictHQ '{q.q}/{q.country_code}': HTTP {r.status_code}")
                    await asyncio.sleep(0.3)
                    continue

                ok += 1
                for ev in (r.json().get("results") or []):
                    try:
                        ec = _to_event_create(ev)
                        if ec and ec.start_date >= today and ec.dedup_hash not in seen:
                            if date_from and ec.start_date < date_from:
                                continue
                            if date_to   and ec.start_date > date_to:
                                continue
                            seen.add(ec.dedup_hash)
                            all_events.append(ec)
                    except Exception as exc:
                        logger.debug(f"PredictHQ parse: {exc}")

                await asyncio.sleep(0.3)

            except httpx.TimeoutException:
                logger.debug(f"PredictHQ timeout '{q.q}'")
            except Exception as exc:
                logger.debug(f"PredictHQ error '{q.q}': {exc}")

    logger.info(f"PredictHQ: {len(all_events)} events ({ok} ok queries)")
    return all_events
