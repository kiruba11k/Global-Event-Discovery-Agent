"""
enrichment/serp_enricher.py  —  google_ai_mode enricher  (v3 — robust)

Key fixes vs v2:
  1. _clean_event_name() removes duplicate years ("2026 2026" → "2026") and
     strips the raw name for cleaner queries
  2. Multi-strategy querying: tries 3 increasingly broad queries before giving up
     — quoted exact name → unquoted name → short name + year + city
  3. Sequential execution (not asyncio.gather) to avoid rate-limit failures
     on SerpAPI free tier (100 req/month)
  4. Accepts any text_blocks length ≥ 1 char (was ≥ 50 — too strict)
  5. Extracts from serpapi_results organic snippets when text_blocks is empty
  6. Relevance guard lowered to 1 token match (was len//4 — too strict)

Usage (unchanged from v2):
    from enrichment.serp_enricher import enrich_events_batch
    enrichments = await enrich_events_batch(events=top_events, serpapi_key=key)
"""
from __future__ import annotations

import asyncio
import re
from typing import Optional
from urllib.parse import urlparse
from loguru import logger

try:
    import serpapi as _serpapi
    _SERPAPI_OK = True
except ImportError:
    _SERPAPI_OK = False
    logger.warning("serpapi not installed — run: pip install serpapi")

# Per-process cache: (cleaned_name|year|city) → result dict
_cache: dict[str, dict] = {}

# ── Venue / hotel / social domains that are NOT event official pages ──
_VENUE_DOMAINS: frozenset[str] = frozenset({
    "singaporeexpo.com.sg", "excel.london", "expoforum-center.ru",
    "fierapordenone.it", "twtc.org.tw", "thecharlottecountyfair.com",
    "fair.ee", "biec.in", "necc.co.in", "cticc.co.za",
    "sunteccity.com.sg", "bitec.com",
    "thelalit.com", "marriott.com", "hilton.com", "hyatt.com",
    "sheratonhotels.com", "ihg.com", "accor.com",
    "facebook.com", "m.facebook.com", "fb.com",
    "twitter.com", "x.com", "linkedin.com",
    "instagram.com", "youtube.com", "meetup.com",
    "wikipedia.org", "eventbrite.com",
})

# ── Industry keyword → buyer personas ─────────────────────────────
_IND_TO_PERSONAS: list[tuple[str, str]] = [
    (r"steel|corrosion|material|alloy|metallurg|metal\s*work",
     "Materials Engineers, Metallurgists, Plant Managers, Procurement Heads"),
    (r"mining|quarry|infrastructure\s+expo",
     "Mining Engineers, Project Managers, Operations Directors, Procurement Heads"),
    (r"manufactur|industrial|machiner|machine\s+tool|automat|robot|cnc|factory",
     "Plant Managers, Operations Directors, Engineers, Procurement Heads, COO"),
    (r"seafood|fish|aquaculture|marine|fishery",
     "Fishery Operators, Food Procurement Managers, F&B Buyers"),
    (r"food\s+process|catering|hospitality|restaurant|hotel",
     "F&B Managers, Procurement Directors, Hotel GMs, Catering Managers"),
    (r"mental\s+health|psychiatr|psychology|psycholog|healthcare|health\s+professional",
     "Hospital CIOs, Healthcare Administrators, Procurement Heads, R&D Directors, Clinical Leaders"),
    (r"fashion|textile|cloth|apparel|fabric",
     "Retail Buyers, Brand Managers, Merchandisers, Sourcing Directors"),
    (r"printing|graphic|inkjet|laser\s+print|packaging",
     "Print Buyers, Creative Directors, Production Managers"),
    (r"education|training|graduate|masters|university",
     "Students, HR Directors, L&D Heads, Talent Managers"),
    (r"boating|sailing|water\s+sport",
     "Marine Buyers, Boat Dealers, Watercraft Enthusiasts"),
    (r"technology|digital|software|cloud|saas|cyber|data\b",
     "CIO, CTO, CDO, VP Engineering, IT Directors"),
    (r"fintech|banking|finance|payment",
     "CFO, CTO, Head of Payments, Digital Banking Leaders"),
    (r"health|medtech|medical|pharma|hospital",
     "Hospital CIOs, Healthcare Administrators, Procurement Heads, R&D Directors"),
    (r"logistic|supply\s+chain|freight|warehou|transport",
     "COO, Supply Chain Head, VP Logistics, Procurement Heads"),
    (r"retail|ecommerce|consumer\s+good",
     "CMO, VP Retail, Head of Ecommerce, Merchandising Directors"),
    (r"energy|renewable|solar|wind|oil|gas",
     "CEO, COO, Sustainability Director, VP Operations"),
    (r"construct|build|real\s+estate|architect",
     "Developers, Architects, Project Managers, Procurement Heads"),
    (r"kitchen|bathroom|sanitary|heating|decor|furnit",
     "Architects, Interior Designers, Retail Buyers, Procurement Heads"),
]

# ── Extraction patterns ────────────────────────────────────────────
_ATT_PATTERNS = [
    r"(\d[\d,]+)\s*\+?\s*(?:attendees|visitors|delegates|participants|exhibitors|registrants|professionals)",
    r"(?:attracts?|draws?|expects?|hosts?|welcomes?|more\s+than|over|around|approximately)\s+(\d[\d,]+)\s+(?:attendees|visitors|delegates|professionals|exhibitors|people)",
    r"(\d[\d,]+)\s+(?:industry\s+)?(?:professionals|leaders|executives|brands|buyers|suppliers)",
    r"visited\s+by\s+(?:more\s+than\s+)?(\d[\d,]+)",
    r"(\d[\d,]+)\s+exhibitors?\s+from",
    r"(\d[\d,]+)\s+companies\s+from",
    r"(\d[\d,]+)\s+(?:medical|health|industry)\s+professionals",
    r"(\d[\d,]+)\s+(?:participants|registered|attendees)",
]

_PRICE_PATTERNS = [
    r"(?:registration|ticket|pass|entry|delegate|admission)\s*(?:fee|price|cost|rate)\s*[:\-]?\s*(?:from\s+)?(?:USD\s*|US\$\s*|\$\s*)(\d[\d,.]+)",
    r"(?:from\s*)?(?:USD\s*|US\$\s*|\$\s*)(\d[\d,.]+)\s*(?:USD)?(?:\s*/\s*(?:person|attendee|delegate))?",
    r"£\s*(\d[\d,.]+)(?:\s*GBP)?",
    r"€\s*(\d[\d,.]+)(?:\s*EUR)?",
    r"(?:INR|Rs\.?\s*|₹\s*)(\d[\d,.]+)",
]


# ── Helpers ────────────────────────────────────────────────────────

def _safe_int(s: str) -> Optional[int]:
    try:
        return int(s.replace(",", "").replace(" ", ""))
    except Exception:
        return None


def _safe_float(s: str) -> Optional[float]:
    try:
        return float(s.replace(",", "").replace(" ", ""))
    except Exception:
        return None


def _clean_event_name(name: str) -> str:
    """
    Clean up DB event name artifacts before using in a search query.
    
    Known issues in DB:
    - "MENTAL HEALTH CONFERENCE 2026 2026" → duplicate year
    - All-caps names → keep as-is, Google handles them
    - Leading/trailing whitespace
    """
    # Remove duplicate years: "2026 2026" → "2026"
    cleaned = re.sub(r'\b(\d{4})\s+\1\b', r'\1', name.strip())
    # Remove triple+ spaces
    cleaned = re.sub(r'\s{2,}', ' ', cleaned)
    return cleaned.strip()


def _is_venue_url(url: str) -> bool:
    if not url:
        return True
    lo = url.lower()
    for bad in ("example.com", "placeholder", "localhost", "127.0.0.1"):
        if bad in lo:
            return True
    try:
        domain = urlparse(url).netloc.lower().lstrip("www.").lstrip("m.")
        if domain in _VENUE_DOMAINS:
            return True
        for vd in _VENUE_DOMAINS:
            if domain.endswith(vd) or vd in domain:
                return True
    except Exception:
        pass
    return False


def _is_eventseye_event_page(url: str) -> bool:
    return bool(url and "eventseye.com/fairs/f-" in url.lower())


def _is_generic_description(text: str) -> bool:
    t = (text or "").lower().strip()
    if len(t) < 50:
        return True
    bad = (
        "source: eventseye", "sourced from eventseye",
        "trade show / expo sourced from",
        "professional conference sourced from",
        "see 10times listing", "see website", "major global trade fair",
    )
    return any(b in t for b in bad)


def _flatten_blocks(text_blocks: list) -> str:
    """Flatten google_ai_mode text_blocks into a string."""
    parts: list[str] = []
    for block in (text_blocks or []):
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict):
            text = (
                block.get("snippet") or block.get("text")
                or block.get("body") or block.get("content") or ""
            )
            if text:
                parts.append(str(text))
    return " ".join(parts)


def _organic_text(organic: list) -> str:
    return " ".join(
        f"{item.get('title','')} {item.get('snippet','')}"
        for item in (organic or [])[:6]
    )


def _extract_attendees(text: str) -> Optional[int]:
    for pat in _ATT_PATTERNS:
        m = re.search(pat, text, re.I)
        if m:
            n = _safe_int(m.group(1))
            if n and 50 <= n <= 5_000_000:
                return n
    return None


def _extract_price(text: str) -> Optional[tuple[float, str]]:
    for pat in _PRICE_PATTERNS:
        m = re.search(pat, text, re.I)
        if m:
            p = _safe_float(m.group(1))
            if p and 1.0 <= p <= 100_000.0:
                ctx = text[max(0, m.start() - 10): m.start() + 15].lower()
                if "£" in ctx or "gbp" in ctx:
                    return p, f"From £{p:,.0f}"
                if "€" in ctx or "eur" in ctx:
                    return p, f"From €{p:,.0f}"
                if "inr" in ctx or "rs." in ctx or "₹" in ctx:
                    return p, f"From ₹{p:,.0f}"
                return p, f"From ${p:,.0f}"
    return None


def _infer_personas(full_text: str, industry_tags: str) -> str:
    combined = (full_text + " " + industry_tags).lower()
    for pattern, personas in _IND_TO_PERSONAS:
        if re.search(pattern, combined, re.I):
            return personas
    return ""


def _best_event_link(organic: list, event_name: str, source_url: str) -> str:
    name_tokens = [
        w.lower() for w in re.split(r"[\s\-&,]+", event_name)
        if len(w) > 3 and not w.isdigit()
    ]
    signals = {
        "official", "register", "registration", "event", "expo",
        "conference", "summit", "fair", "show", "congress", "forum",
    }
    candidates: list[tuple[int, str]] = []
    for item in (organic or [])[:10]:
        link = str(item.get("link", "")).strip()
        if not link.startswith(("http://", "https://")):
            continue
        if _is_venue_url(link):
            continue
        haystack = f"{item.get('title','')} {item.get('snippet','')} {link}".lower()
        score = sum(1 for t in name_tokens if t in haystack)
        score += sum(2 for s in signals if s in haystack)
        candidates.append((score, link))

    candidates.sort(key=lambda x: -x[0])
    if candidates and candidates[0][0] > 0:
        return candidates[0][1]

    # Fallback: EventsEye source page is event-specific
    if _is_eventseye_event_page(source_url):
        return source_url
    return ""


# ── Single-event enricher ──────────────────────────────────────────

async def enrich_event(
    event_name:    str,
    year:          str,
    city:          str,
    source_url:    str,
    serpapi_key:   str,
    industry_tags: str = "",
    *,
    need_attendees:   bool = True,
    need_price:       bool = True,
    need_description: bool = False,
    need_link:        bool = True,
) -> dict:
    """
    Enrich one event using SerpAPI google_ai_mode.
    Tries 3 query strategies to maximise the chance of getting useful data.
    Returns a dict of enriched fields; empty dict = nothing reliable found.
    """
    if not serpapi_key or not _SERPAPI_OK:
        return {}

    # Clean the event name first (removes "2026 2026" → "2026")
    clean_name = _clean_event_name(event_name)
    cache_key  = f"{clean_name}|{year}|{city}"
    if cache_key in _cache:
        return _cache[cache_key]

    city_part  = f" {city}" if city else ""

    # 3 query strategies — most specific to broadest
    queries = [
        # 1. Quoted exact name (most specific)
        f'"{clean_name}" {year}{city_part} official website attendees registration',
        # 2. Unquoted name (handles DB artefacts better)
        f'{clean_name} {year}{city_part} attendees registration fee official site',
        # 3. First 4 words + year + city (broadest — for unusual event names)
        f'{" ".join(clean_name.split()[:4])} {year}{city_part} conference attendees',
    ]

    raw: dict = {}

    for i, query in enumerate(queries):
        # ── Try google_ai_mode first ───────────────────────────────
        try:
            client = _serpapi.Client(api_key=serpapi_key)
            raw = await asyncio.to_thread(
                client.search,
                {"engine": "google_ai_mode", "q": query},
            )
        except Exception as exc:
            logger.debug(f"SerpAPI ai_mode [{i+1}] error '{clean_name[:40]}': {exc}")
            raw = {}

        # ── Check if we got useful content ────────────────────────
        blocks  = raw.get("text_blocks", []) or []
        organic = raw.get("organic_results", []) or []

        ai_text  = _flatten_blocks(blocks)
        org_text = _organic_text(organic)
        full_text = f"{ai_text} {org_text}".strip()

        if len(full_text) < 5 and not organic:
            # Nothing from ai_mode — try plain google fallback
            try:
                client = _serpapi.Client(api_key=serpapi_key)
                raw = await asyncio.to_thread(
                    client.search,
                    {"engine": "google", "q": query, "num": 8},
                )
                organic = raw.get("organic_results", []) or []
                org_text = _organic_text(organic)
                full_text = org_text.strip()
            except Exception as exc2:
                logger.debug(f"SerpAPI google fallback [{i+1}] error '{clean_name[:40]}': {exc2}")

        if len(full_text) < 5:
            logger.debug(f"SerpAPI query [{i+1}] empty for '{clean_name[:40]}' — trying next")
            continue

        # ── Relevance guard: at least 1 name token must appear ─────
        name_words = [
            w for w in re.split(r"[\s\-&,]+", clean_name.lower())
            if len(w) > 3 and not w.isdigit()
        ]
        text_lower = full_text.lower()
        matched    = sum(1 for w in name_words if w in text_lower)

        if name_words and matched == 0:
            logger.debug(f"SerpAPI query [{i+1}] no name tokens matched for '{clean_name[:40]}'")
            continue

        # ── We have relevant content — extract data ────────────────
        logger.debug(f"SerpAPI query [{i+1}] OK for '{clean_name[:40]}' ({matched} tokens, {len(full_text)} chars)")

        result: dict = {}

        # Event link
        if need_link:
            link = _best_event_link(organic, clean_name, source_url)
            if link:
                result["event_link"] = link
                result["website"]    = link
            elif _is_eventseye_event_page(source_url):
                result["event_link"] = source_url
                result["website"]    = source_url

        # Attendees
        if need_attendees:
            att = _extract_attendees(full_text)
            if att:
                result["est_attendees"]      = att
                result["enriched_attendees"] = True
                logger.info(f"SerpAPI att    '{clean_name[:45]}': {att:,}")

        # Price
        if need_price:
            info = _extract_price(full_text)
            if info:
                price, desc = info
                result["ticket_price_usd"]  = price
                result["price_description"] = desc
                result["enriched_price"]    = True
                logger.info(f"SerpAPI price  '{clean_name[:45]}': {desc}")

        # Description from AI blocks
        if need_description and ai_text and len(ai_text) > 40:
            for block in blocks:
                if isinstance(block, dict):
                    txt = (block.get("snippet") or block.get("text") or block.get("body") or "").strip()
                    if len(txt) > 60:
                        result["description"]          = txt[:500]
                        result["description_enriched"] = True
                        break

        # Personas
        personas = _infer_personas(full_text, industry_tags)
        if personas:
            result["audience_personas"] = personas

        # Raw context for LLM
        result["serpapi_text"]    = full_text[:3000]
        result["serpapi_results"] = [
            {
                "title":   str(item.get("title",   ""))[:200],
                "link":    str(item.get("link",    ""))[:500],
                "snippet": str(item.get("snippet", ""))[:400],
            }
            for item in organic[:6]
        ]

        _cache[cache_key] = result
        return result

    # All 3 queries failed or returned irrelevant results
    logger.debug(f"SerpAPI: no useful data found for '{clean_name[:50]}' after 3 queries")
    _cache[cache_key] = {}
    return {}


# ── Batch enricher ─────────────────────────────────────────────────

async def enrich_events_batch(
    events:      list,
    serpapi_key: str,
    max_enrich:  int = 10,
) -> dict[str, dict]:
    """
    Enrich events with SerpAPI google_ai_mode — SEQUENTIALLY to avoid
    hitting the free-tier rate limit (100 req/month).

    Returns {event_id: enrichment_dict}.
    """
    if not serpapi_key or not _SERPAPI_OK:
        logger.warning("SerpAPI enrichment skipped — key missing or package not installed")
        return {}

    to_enrich: list[tuple] = []
    for event in events:
        need_att  = (event.est_attendees or 0) == 0
        need_prc  = not (event.price_description or "").strip() or \
                    (event.price_description or "").strip().lower() in (
                        "see website", "see 10times listing",
                        "see eventseye listing", "see event website",
                    )
        need_desc = _is_generic_description(event.description or "")
        current_url = (
            (getattr(event, "website", "") or "").strip() or
            (event.registration_url or "").strip() or
            (event.source_url or "").strip()
        )
        need_link = _is_venue_url(current_url) or not current_url.startswith("http")

        if any([need_att, need_prc, need_desc, need_link]):
            to_enrich.append((event, need_att, need_prc, need_desc, need_link))

    to_enrich = to_enrich[:max_enrich]
    if not to_enrich:
        return {}

    logger.info(
        f"SerpAPI enriching {len(to_enrich)} events sequentially "
        f"[att={sum(1 for x in to_enrich if x[1])} "
        f"prc={sum(1 for x in to_enrich if x[2])} "
        f"link={sum(1 for x in to_enrich if x[4])}]"
    )

    enriched_map: dict[str, dict] = {}

    # SEQUENTIAL — not asyncio.gather — to avoid rate-limit failures
    for event, need_att, need_prc, need_desc, need_link in to_enrich:
        year = (event.start_date or "")[:4] or "2026"
        city = (
            (getattr(event, "event_cities", "") or "").strip() or
            (event.city or "").strip()
        )
        ind  = (
            (getattr(event, "related_industries", "") or "").strip() or
            (event.industry_tags or "").strip()
        )
        data = await enrich_event(
            event_name       = event.name,
            year             = year,
            city             = city,
            source_url       = event.source_url or "",
            serpapi_key      = serpapi_key,
            industry_tags    = ind,
            need_attendees   = need_att,
            need_price       = need_prc,
            need_description = need_desc,
            need_link        = need_link,
        )
        if data:
            enriched_map[event.id] = data
        # Small delay between calls to be polite to the API
        await asyncio.sleep(0.3)

    att_n  = sum(1 for d in enriched_map.values() if d.get("est_attendees"))
    prc_n  = sum(1 for d in enriched_map.values() if d.get("price_description"))
    link_n = sum(1 for d in enriched_map.values() if d.get("event_link"))
    per_n  = sum(1 for d in enriched_map.values() if d.get("audience_personas"))
    logger.info(
        f"SerpAPI done — {len(enriched_map)}/{len(to_enrich)} enriched | "
        f"att={att_n} prc={prc_n} link={link_n} personas={per_n}"
    )
    return enriched_map
