"""
ingestion/ita_trade_events.py  —  ITA Trade Events API (data.trade.gov)

Triggered live when the ICP form submits, same as predicthq_realtime.py.
Covers industry conferences, trade missions, and webinars curated by the
U.S. Commercial Service and other trade agencies for exporters — a
strong B2B-only source (no consumer events at all).

API:  GET https://data.trade.gov/trade_events/v1/search
Auth: subscription-key header (or query param)
Docs: https://developer.trade.gov/api-details#api=trade-events
Free with a data.trade.gov account.

Real API response fields used (see TradeEvent schema):
    .id                   → dedup_hash suffix (internal ITA ID)
    .name                 → name
    .event_type           → category
    .start_date/.end_date → start_date/end_date (already YYYY-MM-DD)
    .cost                 → price_description
    .url                  → source_url
    .description          → description
    .registration_url     → registration_url
    .source               → provenance note appended to description
    .industries[]         → industry_tags
    .venues[0]            → venue_name / city / country
"""
from __future__ import annotations

import asyncio
from datetime import date
from typing import Optional

import httpx
from loguru import logger

from ingestion.icp_query_builder import ItaQuery
from ingestion.platform_normaliser import normalise
from ingestion.source_health import source_health

SOURCE = "ITA"

BASE_URL = "https://data.trade.gov/trade_events/v1/search"

MAX_EVENTS_PER_SEARCH = 150
PAGE_SIZE = 50   # API max


def _venue(ev: dict) -> tuple[str, str, str]:
    venues = ev.get("venues") or []
    if not venues:
        return "", "", ""
    v = venues[0] or {}
    return (v.get("name") or "").strip(), (v.get("city") or "").strip(), (v.get("country") or "").strip()


def _price(ev: dict) -> str:
    cost = ev.get("cost")
    if cost in (None, "", 0):
        return ""
    try:
        return f"${float(cost):,.0f}"
    except (TypeError, ValueError):
        return str(cost)


def _parse_event(ev: dict, keyword: str) -> Optional[dict]:
    """Map one ITA Trade Events result → 28-column normaliser dict."""
    name = (ev.get("name") or "").strip()
    if not name or len(name) < 3:
        return None

    start = str(ev.get("start_date") or "")[:10]
    end   = str(ev.get("end_date") or "")[:10] or start
    if not start or start < date.today().isoformat():
        return None

    venue_name, city, country = _venue(ev)
    industries = ev.get("industries") or []
    industry   = ", ".join(str(i) for i in industries) if industries else keyword

    desc   = (ev.get("description") or "").strip()
    source = (ev.get("source") or "").strip()
    if source and source.upper() != "ITA":
        desc = f"{desc} (via {source})".strip()

    return {
        "source_platform":   "ITA",
        "source_url":        ev.get("url") or "",
        "name":              name,
        "description":       desc or f"{name} — trade event in {city or country or 'multiple locations'}.",
        "category":          (ev.get("event_type") or "conference").lower(),
        "start_date":        start,
        "end_date":          end,
        "venue_name":        venue_name,
        "city":              city,
        "country":           country,
        "industry_tags":     industry,
        "audience_personas": "",
        "est_attendees":     0,          # ITA doesn't publish attendance
        "price_description": _price(ev),
        "registration_url":  ev.get("registration_url") or "",
        "website":           ev.get("url") or "",
        "sponsors":          "",
        "speakers_url":      "",
        "agenda_url":        "",
        "confidence_score":  0.7,        # curated by U.S. trade agencies — solid B2B signal
        "_ita_id":           ev.get("id", ""),
    }


async def _check_error(resp: httpx.Response, ctx: str) -> Optional[str]:
    """Returns "fatal", "skip", or None (success)."""
    c = resp.status_code
    if c == 200:
        source_health.record_success(SOURCE)
        return None
    if c == 400:
        logger.debug(f"ITA 400 {ctx}: {resp.text[:100]}")
        return "skip"
    if c in (401, 403):
        logger.error(f"ITA {c} — check ITA_API_KEY")
        source_health.record_failure(SOURCE, status=c, detail="check ITA_API_KEY")
        return "fatal"
    if c == 404:
        source_health.record_failure(SOURCE, status=404, detail="endpoint gone")
        return "fatal"
    if c == 429:
        source_health.record_failure(SOURCE, status=429, detail="rate limited")
        logger.warning("ITA 429 rate-limited — stopping remaining queries")
        return "fatal"
    if c >= 500:
        source_health.record_failure(SOURCE, kind="transient", detail=f"HTTP {c}")
    logger.debug(f"ITA HTTP {c} {ctx}")
    return "skip"


async def _fetch_page(
    client:  httpx.AsyncClient,
    q:       ItaQuery,
    offset:  int,
) -> tuple[list, bool]:
    """GET /search — one page. Returns (results, fatal)."""
    params = {
        "q":                       q.q,
        "start_date_range[from]":  q.start_from,
        "start_date_range[to]":    q.start_to,
        "size":                    str(PAGE_SIZE),
        "offset":                  str(offset),
    }
    try:
        resp  = await client.get(BASE_URL, params=params)
        error = await _check_error(resp, f"'{q.q}' offset={offset}")
        if error == "fatal": return [], True
        if error == "skip":  return [], False
        if resp.status_code != 200: return [], False

        body = resp.json()
        return body.get("results", []) or [], False

    except httpx.TimeoutException:
        logger.debug(f"ITA timeout '{q.q}'")
        source_health.record_failure(SOURCE, kind="transient", detail="timeout")
        return [], False
    except Exception as exc:
        logger.debug(f"ITA search error '{q.q}': {exc}")
        source_health.record_failure(SOURCE, kind="transient", detail=str(exc)[:80])
        return [], False


async def run_ita_queries(
    queries:   list[ItaQuery],
    api_key:   str,
    date_from: str = "",
    date_to:   str = "",
    max_pages: int = 2,
) -> list[dict]:
    """
    Execute ICP-driven ITA Trade Events queries.

    Steps:
      1. Page through /search (size=50/page)
      2. Parse → normalise() → 28-column dict
      3. Dedup by dedup_hash

    Returns list of normalised dicts for crud.batch_upsert_events().
    """
    if not api_key:
        logger.warning("ITA: ITA_API_KEY not set — skipping")
        return []

    today     = date.today().isoformat()
    seen_hash: set[str]   = set()
    results:   list[dict] = []
    abort:     bool       = False

    headers = {"subscription-key": api_key, "Accept": "application/json"}

    async with httpx.AsyncClient(
        headers=headers, timeout=httpx.Timeout(20.0, connect=5.0), follow_redirects=True,
    ) as client:

        for q in queries:
            if abort or len(results) >= MAX_EVENTS_PER_SEARCH:
                break

            for page in range(max_pages):
                if abort or len(results) >= MAX_EVENTS_PER_SEARCH:
                    break

                evs, fatal = await _fetch_page(client, q, offset=page * PAGE_SIZE)
                if fatal:
                    abort = True
                    break
                if not evs:
                    break

                for ev in evs:
                    if not isinstance(ev, dict) or len(results) >= MAX_EVENTS_PER_SEARCH:
                        break

                    start = str(ev.get("start_date") or "")[:10]
                    if not start or start < today:
                        continue
                    if date_from and start < date_from: continue
                    if date_to   and start > date_to:   continue

                    try:
                        raw = _parse_event(ev, q.q)
                        if raw is None:
                            continue

                        ita_id = raw.pop("_ita_id", "")
                        if ita_id:
                            import hashlib
                            raw["dedup_hash"] = hashlib.sha1(f"ita:{ita_id}".encode()).hexdigest()

                        clean = normalise(raw, "ITA")
                        dh = clean["dedup_hash"]
                        if dh in seen_hash:
                            continue
                        seen_hash.add(dh)
                        results.append(clean)

                    except Exception as exc:
                        logger.debug(f"ITA parse '{ev.get('name','?')[:40]}': {exc}")

                if len(evs) < PAGE_SIZE or len(results) >= MAX_EVENTS_PER_SEARCH:
                    break
                await asyncio.sleep(0.3)

            await asyncio.sleep(0.3)

    logger.info(f"ITA: {len(results)} trade events from {len(queries)} queries")
    return results
