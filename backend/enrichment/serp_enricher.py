"""
enrichment/serp_enricher.py  —  google_ai_mode enricher

Uses the official `serpapi` Python package:
    import serpapi
    client = serpapi.Client(api_key="...")
    results = client.search({"engine": "google_ai_mode", "q": "..."})
    text_blocks = results["text_blocks"]

Fills missing fields for DB events that have:
    est_attendees   = 0    (all events from this DB)
    price_description = "" (all events)
    audience_personas = "" (all events)
    website           = NULL (all events)

Also: registration_url often points to a venue (singaporeexpo.com.sg, excel.london),
and source_url is the EventsEye event page — we use source_url as the fallback link
and only override with a better SerpAPI-found official URL.

Fallback chain per event:
  1. google_ai_mode  → parse text_blocks
  2. plain google    → parse organic_results snippets (if ai_mode fails/empty)
"""
from __future__ import annotations

import asyncio
import re
from typing import Optional
from urllib.parse import urlparse
from loguru import logger

# ── Official serpapi package ───────────────────────────────────────
try:
    import serpapi as _serpapi
    _SERPAPI_OK = True
except ImportError:
    _SERPAPI_OK = False
    logger.warning("serpapi not installed — run: pip install serpapi")

# In-process cache: (name|year|city) → result dict
_cache: dict[str, dict] = {}

# ── Domains that are venue/hotel/social sites, NOT official event pages ─
_VENUE_DOMAINS: frozenset[str] = frozenset({
    # Specific venues from DB
    "singaporeexpo.com.sg", "excel.london", "expoforum-center.ru",
    "fierapordenone.it", "twtc.org.tw", "thecharlottecountyfair.com",
    "fair.ee", "biec.in", "necc.co.in", "cticc.co.za",
    "sunteccity.com.sg", "bitec.com",
    # Hotel chains
    "thelalit.com", "marriott.com", "hilton.com", "hyatt.com",
    "sheratonhotels.com", "ihg.com", "accor.com",
    # Social / generic platforms
    "facebook.com", "m.facebook.com", "fb.com",
    "twitter.com", "x.com", "linkedin.com",
    "instagram.com", "youtube.com", "meetup.com",
    "wikipedia.org", "eventbrite.com",
})

# ── Industry keyword → buyer personas ──────────────────────────────
_IND_TO_PERSONAS: list[tuple[str, str]] = [
    (r"steel|corrosion|material|alloy|metallurg|metal\s+work",
     "Materials Engineers, Metallurgists, Plant Managers, Procurement Heads"),
    (r"mining|quarry|infrastructure\s+expo",
     "Mining Engineers, Project Managers, Operations Directors, Procurement Heads"),
    (r"manufactur|industrial|machiner|machine\s+tool|automat|robot|cnc|factory",
     "Plant Managers, Operations Directors, Engineers, Procurement Heads, COO"),
    (r"seafood|fish|aquaculture|marine|fishery",
     "Fishery Operators, Food Procurement Managers, F&B Buyers, Operations Directors"),
    (r"food\s+process|catering|hospitality|restaurant|hotel",
     "F&B Managers, Procurement Directors, Hotel GMs, Catering Managers, Chefs"),
    (r"fashion|textile|cloth|apparel|fabric",
     "Retail Buyers, Brand Managers, Merchandisers, Sourcing Directors"),
    (r"printing|graphic|inkjet|laser\s+print|packaging",
     "Print Buyers, Creative Directors, Production Managers, Brand Managers"),
    (r"education|training|graduate|masters|university",
     "Students, HR Directors, L&D Heads, Talent Managers, Admissions Officers"),
    (r"boating|sailing|water\s+sport|marine\s+financing",
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
    (r"wine|spirits|beer|beverage",
     "Sommelier, Bar Managers, Retail Buyers, Importers"),
]

# ── Extraction patterns ────────────────────────────────────────────
_ATT_PATTERNS = [
    r"(\d[\d,]+)\s*\+?\s*(?:attendees|visitors|delegates|participants|exhibitors|registrants|professionals)",
    r"(?:attracts?|draws?|expects?|hosts?|welcomes?|more\s+than|over|around|approximately)\s+(\d[\d,]+)\s+(?:attendees|visitors|delegates|professionals|exhibitors|people)",
    r"(\d[\d,]+)\s+(?:industry\s+)?(?:professionals|leaders|executives|brands|buyers|suppliers)",
    r"visited\s+by\s+(?:more\s+than\s+)?(\d[\d,]+)",
    r"(\d[\d,]+)\s+exhibitors?\s+from",
    r"(\d[\d,]+)\s+companies\s+from",
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
    """EventsEye fairs pages are event-specific and useful as links."""
    return bool(url and "eventseye.com/fairs/f-" in url.lower())


def _is_10times_event_page(url: str) -> bool:
    return bool(url and "10times.com" in url.lower() and "/e/" in url.lower())


def _flatten_blocks(text_blocks: list) -> str:
    """Flatten google_ai_mode text_blocks into a single string."""
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
    """
    Find the best official event page URL.
    Priority:
      1. Organic result URL that scores high on event-name + signal words
      2. source_url if it's an EventsEye/10times event page
      3. Empty string (caller will use Google search fallback)
    """
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
        # EventsEye/10times source links are event-specific — allow them
        haystack = f"{item.get('title','')} {item.get('snippet','')} {link}".lower()
        score = sum(1 for t in name_tokens if t in haystack)
        score += sum(2 for s in signals if s in haystack)
        candidates.append((score, link))

    candidates.sort(key=lambda x: -x[0])
    if candidates and candidates[0][0] > 0:
        return candidates[0][1]

    # Fallback: use source_url if it's an event-specific page
    if _is_eventseye_event_page(source_url) or _is_10times_event_page(source_url):
        return source_url

    return ""


# ── Core enricher ──────────────────────────────────────────────────

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
    Enrich one event using SerpAPI google_ai_mode engine.
    Returns a dict of enriched fields; empty dict = nothing reliable found.
    """
    if not serpapi_key or not _SERPAPI_OK:
        return {}

    cache_key = f"{event_name}|{year}|{city}"
    if cache_key in _cache:
        return _cache[cache_key]

    city_part = f" {city}" if city else ""
    query     = f'"{event_name}" {year}{city_part} official website attendees registration fee'

    raw: dict = {}

    # ── Primary: google_ai_mode ────────────────────────────────────
    try:
        client = _serpapi.Client(api_key=serpapi_key)
        raw = await asyncio.to_thread(
            client.search,
            {"engine": "google_ai_mode", "q": query},
        )
        logger.debug(f"SerpAPI ai_mode: '{event_name[:50]}'")
    except Exception as exc:
        logger.debug(f"SerpAPI ai_mode error '{event_name[:40]}': {exc}")

    # ── Fallback: plain google ─────────────────────────────────────
    if not raw.get("text_blocks") and not raw.get("organic_results"):
        try:
            client = _serpapi.Client(api_key=serpapi_key)
            raw = await asyncio.to_thread(
                client.search,
                {"engine": "google", "q": query, "num": 8},
            )
            logger.debug(f"SerpAPI google fallback: '{event_name[:50]}'")
        except Exception as exc2:
            logger.debug(f"SerpAPI google fallback error '{event_name[:40]}': {exc2}")
            _cache[cache_key] = {}
            return {}

    # ── Aggregate text ─────────────────────────────────────────────
    text_blocks  = raw.get("text_blocks", []) or []
    organic      = raw.get("organic_results", []) or []
    kg_text      = ((raw.get("knowledge_graph") or {}).get("description") or "")
    ab_text      = ((raw.get("answer_box") or {}).get("snippet") or "")

    ai_text      = _flatten_blocks(text_blocks)
    org_text     = " ".join(str(item.get("snippet", "")) for item in organic[:6])
    full_text    = " ".join(filter(None, [ai_text, org_text, kg_text, ab_text]))

    if not full_text.strip():
        _cache[cache_key] = {}
        return {}

    # ── Relevance guard ────────────────────────────────────────────
    # At least 1 significant name token must appear in results
    name_words = [
        w for w in re.split(r"[\s\-&,]+", event_name.lower())
        if len(w) > 3 and not w.isdigit()
    ]
    text_lower = full_text.lower()
    matched    = sum(1 for w in name_words if w in text_lower)
    if name_words and matched < max(1, len(name_words) // 4):
        logger.debug(
            f"SerpAPI mismatch '{event_name[:40]}' "
            f"({matched}/{len(name_words)} tokens) — skipping"
        )
        _cache[cache_key] = {}
        return {}

    result: dict = {}

    # ── Event link ─────────────────────────────────────────────────
    if need_link:
        link = _best_event_link(organic, event_name, source_url)
        if link:
            result["event_link"] = link
            result["website"]    = link
        elif _is_eventseye_event_page(source_url):
            # EventsEye page is always a valid event-specific link
            result["event_link"] = source_url
            result["website"]    = source_url

    # ── Attendees ──────────────────────────────────────────────────
    if need_attendees:
        att = _extract_attendees(full_text)
        if att:
            result["est_attendees"]      = att
            result["enriched_attendees"] = True
            logger.info(f"SerpAPI att    '{event_name[:45]}': {att:,}")

    # ── Price ──────────────────────────────────────────────────────
    if need_price:
        info = _extract_price(full_text)
        if info:
            price, desc = info
            result["ticket_price_usd"]  = price
            result["price_description"] = desc
            result["enriched_price"]    = True
            logger.info(f"SerpAPI price  '{event_name[:45]}': {desc}")

    # ── Description from AI blocks ─────────────────────────────────
    if need_description and len(ai_text) > 60:
        for block in text_blocks:
            if isinstance(block, dict):
                txt = (
                    block.get("snippet") or block.get("text") or block.get("body") or ""
                ).strip()
                if len(txt) > 80:
                    result["description"]          = txt[:500]
                    result["description_enriched"] = True
                    break

    # ── Personas (inferred from industry + ai text) ────────────────
    personas = _infer_personas(full_text, industry_tags)
    if personas:
        result["audience_personas"] = personas

    # ── Raw context for LLM ────────────────────────────────────────
    result["serpapi_text"] = full_text[:3000]
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


# ── Batch enricher ─────────────────────────────────────────────────

async def enrich_events_batch(
    events:      list,      # List[EventORM]
    serpapi_key: str,
    max_enrich:  int = 10,
) -> dict[str, dict]:
    """
    Concurrently enrich events with SerpAPI google_ai_mode.
    Returns {event_id: enrichment_dict}.

    All DB events have est_attendees=0 / price='' / website=NULL, so
    every event qualifies for enrichment. max_enrich caps total API calls.
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
        need_link = (
            _is_venue_url(current_url) or
            not current_url.startswith("http") or
            not _is_eventseye_event_page(event.source_url or "")  # we want a REAL event site
        )

        if any([need_att, need_prc, need_desc, need_link]):
            to_enrich.append((event, need_att, need_prc, need_desc, need_link))

    to_enrich = to_enrich[:max_enrich]

    if not to_enrich:
        logger.info("SerpAPI: all events already complete")
        return {}

    logger.info(
        f"SerpAPI enriching {len(to_enrich)}/{len(events)} events "
        f"[att={sum(1 for x in to_enrich if x[1])} "
        f"prc={sum(1 for x in to_enrich if x[2])} "
        f"link={sum(1 for x in to_enrich if x[4])}]"
    )

    async def _one(event, need_att, need_prc, need_desc, need_link):
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
        return event.id, data

    results      = await asyncio.gather(*[_one(*args) for args in to_enrich])
    enriched_map = {eid: d for eid, d in results if d}

    att_n  = sum(1 for d in enriched_map.values() if d.get("est_attendees"))
    prc_n  = sum(1 for d in enriched_map.values() if d.get("price_description"))
    link_n = sum(1 for d in enriched_map.values() if d.get("event_link"))
    per_n  = sum(1 for d in enriched_map.values() if d.get("audience_personas"))
    logger.info(
        f"SerpAPI done — {len(enriched_map)}/{len(to_enrich)} enriched | "
        f"att={att_n} prc={prc_n} link={link_n} personas={per_n}"
    )
    return enriched_map


def _is_generic_description(text: str) -> bool:
    t = (text or "").lower().strip()
    if len(t) < 50:
        return True
    bad = (
        "source: eventseye", "sourced from eventseye",
        "trade show / expo sourced from",
        "professional conference sourced from",
        "see 10times listing", "see website",
        "major global trade fair",
    )
    return any(b in t for b in bad)
