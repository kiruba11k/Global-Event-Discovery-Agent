"""
enrichment/serpapi_enricher.py

Uses SerpAPI google_ai_mode to fill missing attendee counts and pricing.

Rules (strict — no false positives):
  • Only fills est_attendees when a number appears next to "attendees",
    "visitors", "exhibitors", or "delegates" in the AI response text.
  • Only fills pricing when a currency symbol + number appears in context
    of "registration", "ticket", "fee", or "pass".
  • Never overwrites existing non-zero values.
  • Returns {} if SerpAPI key not set or nothing found.

Usage from SerpAPI docs:
    import serpapi
    client = serpapi.Client(api_key="secret_api_key")
    results = client.search({"engine": "google_ai_mode", "q": "..."})
    text_blocks = results["text_blocks"]
"""
import re
import asyncio
from typing import Optional
from loguru import logger


# ── Regex patterns ─────────────────────────────────────────

# Attendees: "12,000 attendees" / "50k visitors" / "1.2M exhibitors"
_ATT_PATTERN = re.compile(
    r"([\d,]+(?:\.\d+)?)\s*(?:k|K|M)?\s*"
    r"(?:attendees?|visitors?|exhibitors?|delegates?|participants?|professionals?)",
    re.IGNORECASE,
)

# Price: "$1,200" / "USD 500" / "€900" / "£500"
_PRICE_PATTERN = re.compile(
    r"(?:USD|US\$|SGD|AED|€|£|₹|\$)\s*([\d,]+(?:\.\d+)?)",
    re.IGNORECASE,
)

# Price context words — must appear near the price for it to count
_PRICE_CONTEXT = re.compile(
    r"(register|registr|ticket|fee|pass|entry|admission|delegate\s+rate)",
    re.IGNORECASE,
)


def _parse_attendees(text: str) -> Optional[int]:
    """
    Extract attendee count. Returns None unless clearly stated.
    Handles: "12,000 attendees", "50k visitors", "50,000+ visitors"
    """
    m = _ATT_PATTERN.search(text)
    if not m:
        return None
    raw = m.group(1).replace(",", "")
    try:
        val = float(raw)
        # Check for k/M multiplier immediately after the number in the full match
        suffix_region = text[m.start():m.end()].lower()
        if re.search(r"\d\s*k\b", suffix_region) and val < 5000:
            val *= 1_000
        elif re.search(r"\d\s*m\b", suffix_region) and val < 500:
            val *= 1_000_000
        count = int(val)
        # Sanity: realistic event size 100 → 2,000,000
        if 100 <= count <= 2_000_000:
            return count
    except (ValueError, OverflowError):
        pass
    return None


def _parse_price(text: str) -> Optional[float]:
    """
    Extract price only when it appears near a registration/ticket keyword.
    Returns None unless clearly a ticket/registration price.
    """
    # Only search in sentences that contain price context words
    sentences = re.split(r"[.!?\n]", text)
    for sentence in sentences:
        if not _PRICE_CONTEXT.search(sentence):
            continue
        m = _PRICE_PATTERN.search(sentence)
        if m:
            raw = m.group(1).replace(",", "")
            try:
                price = float(raw)
                # Sanity: $5 → $100,000
                if 5 <= price <= 100_000:
                    return price
            except ValueError:
                pass
    return None


def _extract_all_text(text_blocks: list) -> str:
    """
    Flatten all text_blocks from google_ai_mode into one string.
    Each block has a 'snippet' or 'text' field.
    """
    parts = []
    for block in text_blocks:
        snippet = (
            block.get("snippet") or
            block.get("text")    or
            block.get("body")    or
            ""
        )
        if snippet:
            parts.append(str(snippet))
    return " ".join(parts)


# ── Single event enrichment ────────────────────────────────

def enrich_event_sync(
    name:        str,
    city:        str,
    country:     str,
    start_date:  str,
    serpapi_key: str,
    needs_attendees: bool = False,
    needs_price:     bool = False,
) -> dict:
    """
    Synchronous SerpAPI call using the serpapi Python package.
    Uses google_ai_mode engine and parses text_blocks.

    Returns dict with ONLY confirmed findings, e.g.:
        {"est_attendees": 12000}
        {"ticket_price_usd": 1200, "price_description": "From $1,200"}
        {}   ← if nothing found
    """
    if not serpapi_key or not (needs_attendees or needs_price):
        return {}

    year  = start_date[:4] if start_date else "2026"
    query = f"{name} {city} {country} {year}"

    try:
        import serpapi as _serpapi
        client  = _serpapi.Client(api_key=serpapi_key)
        results = client.search({
            "engine": "google_ai_mode",
            "q":      query,
        })
        text_blocks = results.get("text_blocks", [])
    except ImportError:
        logger.error("serpapi package not installed. Run: pip install serpapi")
        return {}
    except Exception as e:
        logger.debug(f"SerpAPI [{name[:35]}]: {e}")
        return {}

    if not text_blocks:
        logger.debug(f"SerpAPI [{name[:35]}]: no text_blocks returned.")
        return {}

    full_text = _extract_all_text(text_blocks)
    enriched  = {}

    # ── Attendee count ─────────────────────────────────────
    if needs_attendees:
        count = _parse_attendees(full_text)
        if count:
            enriched["est_attendees"] = count
            logger.info(f"SerpAPI enriched [{name[:35]}]: attendees={count:,}")
        else:
            logger.debug(f"SerpAPI [{name[:35]}]: attendees not found in AI response")

    # ── Ticket price ───────────────────────────────────────
    if needs_price:
        price = _parse_price(full_text)
        if price:
            enriched["ticket_price_usd"]  = price
            enriched["price_description"] = f"From ${price:,.0f}"
            logger.info(f"SerpAPI enriched [{name[:35]}]: price=~${price:,.0f}")
        else:
            logger.debug(f"SerpAPI [{name[:35]}]: price not found in AI response")

    return enriched


# ── Async wrapper ──────────────────────────────────────────

async def enrich_event(
    name:        str,
    city:        str,
    country:     str,
    start_date:  str,
    serpapi_key: str,
    needs_attendees: bool = False,
    needs_price:     bool = False,
) -> dict:
    """Async wrapper — runs the sync SerpAPI call in a thread pool."""
    return await asyncio.to_thread(
        enrich_event_sync,
        name, city, country, start_date, serpapi_key,
        needs_attendees, needs_price,
    )


# ── Batch enricher ─────────────────────────────────────────

async def batch_enrich(
    events:          list,       # list of EventORM objects
    serpapi_key:     str,
    max_enrichments: int = 5,    # max SerpAPI calls per search request
) -> dict:
    """
    Enrich up to max_enrichments events that are missing attendees or price.

    Returns: {event.id: {field: value, ...}, ...}

    Priority: enrich GO events first (sorted by relevance_score descending).
    Never enriches events that already have attendance/price data.
    """
    if not serpapi_key:
        return {}

    enrichments = {}
    calls_made  = 0

    for event in events:
        if calls_made >= max_enrichments:
            break

        needs_att   = not event.est_attendees or event.est_attendees == 0
        needs_price = (
            (not event.ticket_price_usd or event.ticket_price_usd == 0)
            and not (event.price_description or "").strip()
        )

        if not needs_att and not needs_price:
            continue  # already has all critical numbers

        city    = (
            getattr(event, "event_cities", "") or
            event.city or ""
        )
        country = event.country or ""

        result = await enrich_event(
            name            = event.name,
            city            = city,
            country         = country,
            start_date      = event.start_date or "",
            serpapi_key     = serpapi_key,
            needs_attendees = needs_att,
            needs_price     = needs_price,
        )

        if result:
            enrichments[event.id] = result
            calls_made += 1

        # Small delay to stay within SerpAPI rate limits
        if calls_made < max_enrichments:
            await asyncio.sleep(0.5)

    if enrichments:
        total_fields = sum(len(v) for v in enrichments.values())
        logger.info(
            f"SerpAPI batch: enriched {len(enrichments)} events, "
            f"{total_fields} fields filled, {calls_made} API calls."
        )

    return enrichments
