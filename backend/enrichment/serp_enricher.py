"""
SerpAPI enricher — fills missing event fields at display time.

Rules:
  • Only called when a field is genuinely missing / generic.
  • NEVER fills data that doesn't match the event name (no false positives).
  • Enriched values are added to the response payload; they are NOT written
    back to the database (display-time only).
  • Results are cached in memory per process to avoid duplicate API calls.
  • Respects rate limits — at most one call per unique event name per run.

Requires: SERPAPI_KEY in environment / .env
Free tier: 100 searches/month. We only enrich events missing key fields.
"""
from __future__ import annotations

import asyncio
import re
from typing import Optional
from loguru import logger

try:
    import httpx
    _HTTPX_OK = True
except ImportError:
    _HTTPX_OK = False

# In-process cache: event_name → enriched dict
_cache: dict[str, dict] = {}

# Patterns to extract attendee counts
_ATT_PATTERNS = [
    r"(\d[\d,]+)\s*\+?\s*(?:attendees|visitors|delegates|participants|exhibitors|registrants)",
    r"(?:attended|attracts|draws|expected|hosts|welcomes)\s*(?:over|more than|around|approx\.?)?\s*(\d[\d,]+)",
    r"(\d[\d,]+)\s*(?:industry\s*)?(?:professionals|leaders|executives|companies)",
    r"(\d[\d,]+)\s*(?:sqm|sq\s*m|square\s*metres?)",  # sometimes venue size implies scale
]

# Patterns to extract ticket / registration price in USD
_PRICE_PATTERNS = [
    r"(?:from\s*)?\$\s*(\d[\d,.]+)\s*(?:USD|per\s*(?:person|attendee|delegate))?",
    r"(?:USD|US\$)\s*(\d[\d,.]+)",
    r"(?:registration|ticket|pass|entry)\s*(?:fee|price|cost)\s*(?:is|of|from)?\s*\$\s*(\d[\d,.]+)",
    r"(?:starts?\s*at|as\s*low\s*as)\s*\$\s*(\d[\d,.]+)",
]


def _is_generic_description(text: str) -> bool:
    """True if the description is a boilerplate fallback, not real content."""
    generic_phrases = [
        "major global trade fair",
        "source: eventseye",
        "sourced from eventseye",
        "trade show / expo sourced from",
        "professional conference sourced from",
        "global event sourced from",
        "see 10times listing",
        "see website",
    ]
    t = (text or "").lower().strip()
    if len(t) < 60:
        return True
    return any(phrase in t for phrase in generic_phrases)


def _safe_int(text: str) -> Optional[int]:
    try:
        return int(text.replace(",", "").replace(" ", ""))
    except (ValueError, AttributeError):
        return None


def _safe_float(text: str) -> Optional[float]:
    try:
        return float(text.replace(",", "").replace(" ", ""))
    except (ValueError, AttributeError):
        return None


def _extract_attendees(full_text: str) -> Optional[int]:
    for pat in _ATT_PATTERNS:
        m = re.search(pat, full_text, re.I)
        if m:
            n = _safe_int(m.group(1))
            if n and 200 <= n <= 5_000_000:
                return n
    return None


def _extract_price(full_text: str) -> Optional[tuple[float, str]]:
    """Returns (price_usd, description) or None."""
    for pat in _PRICE_PATTERNS:
        m = re.search(pat, full_text, re.I)
        if m:
            p = _safe_float(m.group(1))
            if p and 1.0 <= p <= 50_000.0:
                return p, f"From ${p:,.0f}"
    return None


def _build_query(event_name: str, year: str) -> str:
    """Build a focused Google search query for the event."""
    return f'"{event_name}" {year} attendees registration fee'


async def enrich_event(
    event_name: str,
    year: str,
    city: str,
    serpapi_key: str,
    *,
    need_attendees: bool = False,
    need_price: bool = False,
    need_description: bool = False,
) -> dict:
    """
    Call SerpAPI for missing event fields.
    Returns a dict with only the fields we're confident about.
    Empty dict → nothing reliable found.

    Args:
        event_name:      Full event name (e.g. "Indonesia Tech Week 2026")
        year:            Event year as string (e.g. "2026")
        city:            Event city for disambiguation
        serpapi_key:     SerpAPI API key
        need_attendees:  True if est_attendees is 0 / missing
        need_price:      True if price is "See website" / missing
        need_description:True if description is generic / missing
    """
    if not serpapi_key or not _HTTPX_OK:
        return {}
    if not any([need_attendees, need_price, need_description]):
        return {}

    cache_key = f"{event_name}|{year}"
    if cache_key in _cache:
        return _cache[cache_key]

    query = _build_query(event_name, year)

    try:
        async with httpx.AsyncClient(timeout=12) as client:
            r = await client.get(
                "https://serpapi.com/search.json",
                params={
                    "engine":        "google",
                    "q":             query,
                    "api_key":       serpapi_key,
                    "num":           5,
                    "gl":            "us",
                    "hl":            "en",
                    "google_domain": "google.com",
                },
            )
            r.raise_for_status()
            data = r.json()
    except Exception as exc:
        logger.debug(f"SerpAPI enrichment failed for '{event_name}': {exc}")
        _cache[cache_key] = {}
        return {}

    result: dict = {}

    # ── Aggregate all text from the response ───────────────────
    snippets: list[str] = []
    for item in data.get("organic_results", [])[:5]:
        snippets.append(item.get("snippet", ""))
        snippets.append(item.get("title", ""))
    kg = data.get("knowledge_graph", {})
    snippets.append(str(kg.get("description", "")))
    ab = data.get("answer_box", {})
    snippets.append(str(ab.get("answer", "")))
    snippets.append(str(ab.get("snippet", "")))
    full_text = " ".join(snippets)

    # ── Sanity-check: does the result actually match this event? ─
    # Require that the event name words (ignoring year) appear in results
    name_words = [w for w in event_name.lower().split() if len(w) > 3 and not w.isdigit()]
    text_lower  = full_text.lower()
    matched_words = sum(1 for w in name_words if w in text_lower)
    if name_words and matched_words < max(1, len(name_words) // 2):
        logger.debug(f"SerpAPI result doesn't match '{event_name}' — skipping enrichment")
        _cache[cache_key] = {}
        return {}

    # ── Attendees ──────────────────────────────────────────────
    if need_attendees:
        att = _extract_attendees(full_text)
        if att:
            result["est_attendees"]        = att
            result["enriched_attendees"]   = True
            logger.debug(f"Enriched attendees for '{event_name}': {att:,}")

    # ── Price ──────────────────────────────────────────────────
    if need_price:
        price_info = _extract_price(full_text)
        if price_info:
            price, desc = price_info
            result["ticket_price_usd"]   = price
            result["price_description"]  = desc
            result["enriched_price"]     = True
            logger.debug(f"Enriched price for '{event_name}': {desc}")

    # ── Description ────────────────────────────────────────────
    if need_description:
        # Prefer knowledge graph description (most authoritative)
        kg_desc = kg.get("description", "").strip()
        if kg_desc and len(kg_desc) > 60:
            result["description_enriched"] = kg_desc[:500]
            result["enriched_description"] = True
            logger.debug(f"Enriched description for '{event_name}' from KG")
        else:
            # Try first organic result snippet
            for item in data.get("organic_results", [])[:3]:
                snip = item.get("snippet", "").strip()
                if len(snip) > 80:
                    result["description_enriched"] = snip[:500]
                    result["enriched_description"] = True
                    logger.debug(f"Enriched description for '{event_name}' from snippet")
                    break

    _cache[cache_key] = result
    return result


async def enrich_events_batch(
    events: list,           # list of EventORM
    serpapi_key: str,
    max_enrich: int = 7,    # limit API calls per search request
) -> dict[str, dict]:
    """
    Enrich a batch of events concurrently.
    Returns {event_id: enrichment_dict}.

    Only enriches events that actually need it.
    Processes at most `max_enrich` events to conserve API quota.
    """
    if not serpapi_key or not _HTTPX_OK:
        return {}

    to_enrich: list[tuple] = []  # (event, need_att, need_price, need_desc)

    for event in events:
        need_att  = (event.est_attendees or 0) == 0
        need_prc  = not event.price_description or event.price_description.strip().lower() in (
            "see website", "see 10times listing", "see eventseye listing", ""
        )
        need_desc = _is_generic_description(event.description or "")
        if any([need_att, need_prc, need_desc]):
            to_enrich.append((event, need_att, need_prc, need_desc))

    # Prioritise GO events; limit total API calls
    to_enrich = to_enrich[:max_enrich]

    if not to_enrich:
        return {}

    async def _one(event, need_att, need_prc, need_desc):
        year = (event.start_date or "")[:4] or "2026"
        enriched = await enrich_event(
            event_name=event.name,
            year=year,
            city=event.city or "",
            serpapi_key=serpapi_key,
            need_attendees=need_att,
            need_price=need_prc,
            need_description=need_desc,
        )
        return event.id, enriched

    results_list = await asyncio.gather(*[_one(*args) for args in to_enrich])
    return {eid: enriched for eid, enriched in results_list if enriched}
