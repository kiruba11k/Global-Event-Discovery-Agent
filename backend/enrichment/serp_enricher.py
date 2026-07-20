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

from relevance.llm_client import llm

try:
    import serpapi as _serpapi
    _SERPAPI_OK = True
except ImportError:
    _SERPAPI_OK = False
    logger.warning("serpapi not installed — run: pip install serpapi")

# Per-process cache: (cleaned_name|year|city) → result dict
_cache: dict[str, dict] = {}

# How many events to enrich concurrently. SerpAPI's free tier caps
# TOTAL requests per month (100), not requests per second, so capping
# concurrency (rather than going fully sequential) is safe and turns a
# ~2min wall-clock enrichment pass for 6 events into ~30-40s without
# spending any more quota. Keep modest — this also fans out into Groq
# validation calls per event, which share the same TPM budget.
_ENRICH_CONCURRENCY = 3

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


def _is_homepage_url(url: str) -> bool:
    """
    Returns True when the URL is a root domain or a shallow generic section
    with no event-specific path — i.e. likely the organiser's homepage, not
    the specific event edition page.

    Examples that return True (homepage / too shallow):
      https://marketingfestival.in/
      https://peoplematters.in/techhr/
      https://aws.amazon.com/events/
      https://example.com

    Examples that return False (looks edition-specific):
      https://peoplematters.in/techhr/techhr-india-2026/
      https://marketingfestival.in/summit/2026
      https://ciscolive.com/emea/attend/register.html
    """
    if not url:
        return True
    try:
        parsed = urlparse(url)
        # Strip leading/trailing slashes and split path segments
        path_parts = [p for p in parsed.path.strip("/").split("/") if p]
        # Root domain with no path → homepage
        if not path_parts:
            return True
        # Exactly one shallow segment with no digit (year) → generic section
        # e.g. /techhr/ or /events/ or /conference/
        if len(path_parts) == 1:
            segment = path_parts[0].lower()
            # If the segment contains a 4-digit year → edition-specific, keep it
            if re.search(r"\b20\d{2}\b", segment):
                return False
            # Generic section names that are never event-specific
            generic_sections = {
                "events", "event", "conferences", "conference", "register",
                "registration", "attend", "summit", "expo", "fair",
                "news", "blog", "press", "media", "about", "contact",
            }
            if segment in generic_sections:
                return True
            # Single-word segment with no year and short (≤8 chars) — likely a section
            if len(segment) <= 8:
                return True
        # Two segments but second is purely generic
        if len(path_parts) == 2:
            second = path_parts[1].lower()
            if not re.search(r"\b20\d{2}\b", second) and second in {
                "register", "attend", "overview", "home", "index", "info",
            }:
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


def _best_event_link(organic: list, event_name: str, source_url: str, year: str = "") -> str:
    """
    Pick the best event URL from SerpAPI organic results.

    Scoring (higher = better):
      +1 per event-name token in title/snippet/url
      +2 per signal word (register, official, conference, …)
      +5 if the URL contains the event year (e.g. /2026/ or -2026)  ← KEY FIX
      -3 if the URL is a homepage/shallow generic page               ← KEY FIX
      -5 if it's a known aggregator (10times, eventseye, bizzabo…)   ← KEY FIX

    Returns the best URL, or "" if nothing reliable found.
    """
    name_tokens = [
        w.lower() for w in re.split(r"[\s\-&,]+", event_name)
        if len(w) > 3 and not w.isdigit()
    ]
    signals = {
        "official", "register", "registration", "event", "expo",
        "conference", "summit", "fair", "show", "congress", "forum",
    }
    # Aggregator domains that list events but are not the event's own page
    aggregator_domains = {
        "10times.com", "eventseye.com", "bizzabo.com", "evensi.com",
        "allevents.in", "lanyrd.com", "confhub.com", "meetup.com",
        "eventbrite.com", "konferencje.pl", "conferencealerts.com",
        "papercrowd.com", "conference-service.com", "allconferences.com",
    }

    current_year = year or ""

    candidates: list[tuple[float, str]] = []
    for item in (organic or [])[:12]:
        link = str(item.get("link", "")).strip()
        if not link.startswith(("http://", "https://")):
            continue
        if _is_venue_url(link):
            continue

        try:
            link_domain = urlparse(link).netloc.lower().lstrip("www.")
        except Exception:
            link_domain = ""

        # Skip aggregators
        if any(agg in link_domain for agg in aggregator_domains):
            continue

        haystack = f"{item.get('title','')} {item.get('snippet','')} {link}".lower()
        score: float = 0.0

        # Name token matches
        score += sum(1.0 for t in name_tokens if t in haystack)
        # Signal word matches
        score += sum(2.0 for s in signals if s in haystack)

        # Year-in-URL bonus — strong signal that this is the right edition
        if current_year and current_year in link:
            score += 5.0
        elif re.search(r"/20\d{2}[/\-]?|[\-_]20\d{2}[\-_/.]", link):
            # Any 4-digit year in URL path
            score += 3.0

        # Homepage / shallow URL penalty
        if _is_homepage_url(link):
            score -= 3.0

        candidates.append((score, link))

    # Sort by score descending; break ties by preferring shorter URLs
    # (shorter URLs are often the canonical edition page)
    candidates.sort(key=lambda x: (-x[0], len(x[1])))

    if candidates and candidates[0][0] > 0:
        return candidates[0][1]

    # Fallback: EventsEye source page is event-specific
    if _is_eventseye_event_page(source_url):
        return source_url
    return ""


# ── Single-event enricher ──────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# Groq AI validator for SerpAPI results
# ─────────────────────────────────────────────────────────────────────────────
# Called AFTER google_ai_mode returns — Groq validates / extracts real values
# from the raw text. Strict anti-hallucination: Groq must only return values
# EXPLICITLY present in the source text, never inferred or made up.
# ─────────────────────────────────────────────────────────────────────────────

_GROQ_EXTRACTION_SYSTEM = """You are a strict data extractor. You will be given:
1. EVENT_NAME — the event you are enriching
2. SOURCE_TEXT — raw text from a Google AI Mode search about that event

YOUR ONLY JOB: extract specific factual values EXPLICITLY stated in SOURCE_TEXT.

ABSOLUTE RULES — violating any rule makes your entire response invalid:
1. ONLY extract values you can directly quote from SOURCE_TEXT.
2. If a value is NOT in SOURCE_TEXT, return null for that field. Never guess or infer.
3. For attendees: extract the NUMBER only if SOURCE_TEXT contains a phrase like
   "X attendees", "X participants", "X visitors", "attracts X", "draws X people",
   "expected X", "X registered". Do NOT extract venue capacity as attendees.
4. For registration_url: only return a URL if SOURCE_TEXT explicitly names it as
   the event's registration/official page. Never return a Google URL, venue URL,
   or social media URL.
5. For price: only return if SOURCE_TEXT says "from $X", "registration fee X",
   "ticket price X", "costs X", "X to attend", "X per delegate". Never guess free.
6. For description: copy a VERBATIM sentence from SOURCE_TEXT that describes WHAT
   the event IS about. Do not paraphrase. Do not generate new sentences.
7. For dates: extract the EXACT start and end dates ONLY if SOURCE_TEXT explicitly
   states the event dates (e.g. "January 15-17, 2026", "March 5, 2026").
   Return in YYYY-MM-DD format. Return null if dates are not explicitly stated.
   The year must be 2025 or later. Do NOT invent or guess dates.
8. If SOURCE_TEXT is not about EVENT_NAME (different event), return all nulls.

Return ONLY this JSON (no text before or after, no markdown, no code blocks):
{
  "est_attendees": <integer or null>,
  "registration_url": "<verified event URL string or null>",
  "price_description": "<verbatim price string from text or null>",
  "description": "<verbatim sentence from text or null>",
  "start_date": "<YYYY-MM-DD or null>",
  "end_date": "<YYYY-MM-DD or null>",
  "confidence": "<high|medium|low — how certain are you this text is about the named event>",
  "evidence": "<quote the exact phrase from SOURCE_TEXT that supports each non-null field>"
}"""



async def _groq_validate_enrichment(
    event_name:  str,
    year:        str,
    source_text: str,
    organic:     list,
    groq_client: object,
) -> dict:
    """
    Use Groq to validate and extract real values from SerpAPI google_ai_mode output.

    Strict anti-hallucination approach:
    - Groq only returns values explicitly present in source_text
    - All fields null if not found
    - Confidence rating lets caller decide how much to trust the output
    - Evidence field forces Groq to cite the source phrase

    Returns {} if Groq is unavailable or validation fails.
    """
    if not groq_client or not source_text or len(source_text) < 20:
        return {}

    # Truncate to 3000 chars — enough context without wasting tokens
    text_sample = source_text[:3000]

    # Include top organic snippets for additional grounding
    organic_snippets = "\n".join(
        f"[{i+1}] {item.get('title','')} — {item.get('snippet','')[:200]}"
        for i, item in enumerate((organic or [])[:5])
    )
    if organic_snippets:
        text_sample = f"{text_sample}\n\nORGANIC RESULTS:\n{organic_snippets}"

    user_prompt = (
        f"EVENT_NAME: {event_name} {year}\n\n"
        f"SOURCE_TEXT:\n{text_sample}"
    )

    try:
        # Route through the shared LLM gateway: token budgeting, TPM limiting,
        # model fallback and robust JSON repair (fences, trailing commas,
        # truncation) — a repairable response is never discarded.
        parsed = await llm.chat_json(
            _GROQ_EXTRACTION_SYSTEM,
            user_prompt,
            label="serp_validate",
            temperature=0.0,          # deterministic — no creativity
            max_completion_tokens=600,
            timeout=15,
            cache_ttl=300,
        )
        if not isinstance(parsed, dict):
            return {}

        # Validate: reject if confidence is low and we have no evidence
        confidence = str(parsed.get("confidence", "low")).lower()
        evidence   = str(parsed.get("evidence", "")).strip()

        if confidence == "low" and not evidence:
            logger.debug(f"Groq: low confidence, no evidence for '{event_name[:40]}' — discarding")
            return {}

        # Clean each field: null strings → None
        result = {}

        att = parsed.get("est_attendees")
        if att and isinstance(att, (int, float)) and int(att) > 0:
            result["est_attendees"] = int(att)

        reg = parsed.get("registration_url") or ""
        if reg and isinstance(reg, str) and reg.startswith("http"):
            # Extra guard: reject Google, social, venue URLs
            if not _is_venue_url(reg) and not _is_homepage_url(reg) and "google.com" not in reg:
                result["registration_url"] = reg
                result["website"]          = reg

        price = parsed.get("price_description") or ""
        if price and isinstance(price, str) and len(price) > 2 and price.lower() != "null":
            result["price_description"] = price[:200]

        desc = parsed.get("description") or ""
        if desc and isinstance(desc, str) and len(desc) > 40 and desc.lower() != "null":
            result["description"]          = desc[:600]
            result["description_enriched"] = True

        # Date extraction — validate format YYYY-MM-DD and year >= 2025
        for field in ("start_date", "end_date"):
            raw_date = parsed.get(field) or ""
            if raw_date and isinstance(raw_date, str) and raw_date.lower() != "null":
                raw_date = raw_date.strip()
                if re.match(r"^\d{4}-\d{2}-\d{2}$", raw_date):
                    date_year = int(raw_date[:4])
                    if date_year >= 2025:
                        result[field] = raw_date
                        logger.debug(f"Groq {field} '{event_name[:40]}': {raw_date}")

        result["groq_confidence"] = confidence
        result["groq_evidence"]   = evidence[:300] if evidence else ""

        logger.debug(
            f"Groq validated '{event_name[:40]}': "
            f"att={result.get('est_attendees')} "
            f"url={bool(result.get('registration_url'))} "
            f"price={bool(result.get('price_description'))} "
            f"conf={confidence}"
        )
        return result

    except Exception as exc:
        logger.debug(f"Groq validation error for '{event_name[:40]}': {exc}")
        return {}


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
    groq_client:      object = None,   # pass AsyncGroq client for validation
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

                # ── Groq validation: extract real values from AI Mode text ──
        # Runs ONLY when groq_client is provided.
        # Strict anti-hallucination: Groq must cite exact source phrases.
        # Groq-extracted values take PRIORITY over regex extraction below.
        groq_result: dict = {}
        if groq_client and full_text:
            groq_result = await _groq_validate_enrichment(
                event_name  = clean_name,
                year        = year,
                source_text = full_text,
                organic     = organic,
                groq_client = groq_client,
            )
            # If Groq found real values, use them immediately
            if groq_result.get("est_attendees"):
                result["est_attendees"]      = groq_result["est_attendees"]
                result["enriched_attendees"] = True
                logger.info(f"Groq att    '{clean_name[:45]}': {groq_result['est_attendees']:,}")
            if groq_result.get("registration_url"):
                result["event_link"]         = groq_result["registration_url"]
                result["website"]            = groq_result["registration_url"]
                result["registration_url"]   = groq_result["registration_url"]
                logger.info(f"Groq link   '{clean_name[:45]}': {groq_result['registration_url'][:60]}")
            if groq_result.get("price_description"):
                result["price_description"] = groq_result["price_description"]
                result["enriched_price"]    = True
                logger.info(f"Groq price  '{clean_name[:45]}': {groq_result['price_description']}")
            if groq_result.get("description") and need_description:
                result["description"]          = groq_result["description"]
                result["description_enriched"] = True
            # Date fields — Groq-extracted verified dates
            if groq_result.get("start_date"):
                result["start_date"]         = groq_result["start_date"]
                result["date_verified"]      = True
                logger.info(f"Groq date   '{clean_name[:45]}': {groq_result['start_date']}")
            if groq_result.get("end_date"):
                result["end_date"]           = groq_result["end_date"]
            # Record Groq confidence
            result["groq_confidence"] = groq_result.get("groq_confidence", "")
            result["groq_evidence"]   = groq_result.get("groq_evidence", "")

        # ── Regex fallback for fields Groq didn't find ─────────────
        # Only runs for fields not already populated by Groq validation.

        # Event link
        if need_link and not result.get("event_link"):
            link = _best_event_link(organic, clean_name, source_url, year=year)
            if link:
                result["event_link"] = link
                result["website"]    = link
            elif _is_eventseye_event_page(source_url):
                result["event_link"] = source_url
                result["website"]    = source_url

        # Attendees (regex fallback — only if Groq didn't find it)
        if need_attendees and not result.get("est_attendees"):
            att = _extract_attendees(full_text)
            if att:
                result["est_attendees"]      = att
                result["enriched_attendees"] = True
                logger.info(f"SerpAPI att    '{clean_name[:45]}': {att:,}")

        # Price (regex fallback — only if Groq didn't find it)
        if need_price and not result.get("price_description"):
            info = _extract_price(full_text)
            if info:
                price, desc = info
                result["ticket_price_usd"]  = price
                result["price_description"] = desc
                result["enriched_price"]    = True
                logger.info(f"SerpAPI price  '{clean_name[:45]}': {desc}")

        # Description from AI blocks (only if Groq didn't find it)
        if need_description and not result.get("description") and ai_text and len(ai_text) > 40:
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


async def enrich_sponsors(
    event_name:  str,
    year:        str,
    serpapi_key: str,
    groq_client: object = None,
) -> str:
    """
    Tier-2 improvement 3.9: Secondary SerpAPI search specifically for
    exhibitor/sponsor lists for events where sponsors field is empty.

    Query strategy: "{event_name} {year} exhibitors OR sponsors OR 'exhibitor list'"
    Groq extracts only company names explicitly listed as exhibitors/sponsors.

    Returns: comma-separated sponsor string, or "" if nothing found.
    Anti-hallucination: Groq must quote exact company names from the source text.
    """
    if not serpapi_key or not _SERPAPI_OK:
        return ""

    clean_name = _clean_event_name(event_name)
    cache_key  = f"sponsors|{clean_name}|{year}"
    if cache_key in _cache:
        return _cache[cache_key].get("sponsors", "")

    query = f'{clean_name} {year} exhibitors sponsors "exhibitor list" "sponsor list"'

    try:
        client = _serpapi.Client(api_key=serpapi_key)
        raw = await asyncio.to_thread(
            client.search,
            {"engine": "google_ai_mode", "q": query},
        )
    except Exception as exc:
        logger.debug(f"SerpAPI sponsor search error \'{clean_name[:40]}\': {exc}")
        return ""

    blocks  = raw.get("text_blocks", []) or []
    organic = raw.get("organic_results", []) or []
    ai_text = _flatten_blocks(blocks)
    org_text = _organic_text(organic)
    full_text = f"{ai_text} {org_text}".strip()

    if len(full_text) < 20:
        return ""

    # Groq extraction: only real company names from source text
    if not groq_client:
        _cache[cache_key] = {"sponsors": ""}
        return ""

    SPONSOR_SYSTEM = """You are extracting company names from event exhibitor/sponsor text.

RULES:
1. Return ONLY company names that are EXPLICITLY listed as exhibitors, sponsors,
   or participants in SOURCE_TEXT.
2. Do NOT include: event organizers, speakers, topics, venue names.
3. Do NOT invent or guess company names.
4. If no company names are explicitly listed, return an empty list.
5. Return ONLY JSON: {"companies": ["Company A", "Company B", ...]}
   Maximum 20 companies. Empty array if none found."""

    try:
        parsed = await llm.chat_json(
            SPONSOR_SYSTEM,
            f"EVENT: {event_name} {year}\n\nSOURCE_TEXT:\n{full_text[:2000]}",
            label="serp_sponsors",
            temperature=0.0,
            max_completion_tokens=300,
            timeout=15,
            cache_ttl=300,
        )
        if not isinstance(parsed, dict):
            _cache[cache_key] = {"sponsors": ""}
            return ""
        companies = parsed.get("companies", [])
        if not isinstance(companies, list):
            companies = []
        # Validate: reject single-character entries, URLs, numbers
        valid = [
            c.strip() for c in companies
            if isinstance(c, str) and len(c.strip()) > 2
            and not c.strip().startswith("http")
            and not c.strip().isdigit()
        ][:20]
        result_str = ", ".join(valid) if valid else ""
        _cache[cache_key] = {"sponsors": result_str}
        if result_str:
            logger.info(f"Sponsor enrichment \'{clean_name[:40]}\': {len(valid)} companies")
        return result_str
    except Exception as exc:
        logger.debug(f"Groq sponsor extraction error \'{clean_name[:40]}\': {exc}")
        _cache[cache_key] = {"sponsors": ""}
        return ""


async def enrich_events_batch(
    events:          list,
    serpapi_key:     str,
    groq_client:     object = None,   # AsyncGroq client for post-validation
    max_enrich:      int = 10,
    attendees_only:  bool = False,    # scope every call to est_attendees only
) -> dict[str, dict]:
    """
    Enrich events with SerpAPI google_ai_mode — SEQUENTIALLY to avoid
    hitting the free-tier rate limit (100 req/month).

    attendees_only=True restricts every SerpAPI lookup to attendee-count
    extraction only (skips price/description/link enrichment and sponsor
    lookups entirely) — for cost-controlled deployments where SerpAPI is
    reserved purely for filling in est_attendees.

    Returns {event_id: enrichment_dict}.
    """
    if not serpapi_key or not _SERPAPI_OK:
        logger.warning("SerpAPI enrichment skipped — key missing or package not installed")
        return {}

    to_enrich: list[tuple] = []
    for event in events:
        need_att  = (event.est_attendees or 0) == 0

        if attendees_only:
            if need_att:
                to_enrich.append((event, True, False, False, False))
            continue

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
        # Need a new link if:
        #   a) no URL at all
        #   b) it's a venue/blocked domain
        #   c) it's just the organiser's homepage or a shallow generic section
        need_link = (
            not current_url or
            not current_url.startswith("http") or
            _is_venue_url(current_url) or
            _is_homepage_url(current_url)
        )
        # Always re-verify dates (web reality may differ from DB)
        need_date = True

        if any([need_att, need_prc, need_desc, need_link, need_date]):
            to_enrich.append((event, need_att, need_prc, need_desc, need_link))


    to_enrich = to_enrich[:max_enrich]
    if not to_enrich:
        return {}

    logger.info(
        f"SerpAPI enriching {len(to_enrich)} events (concurrency={_ENRICH_CONCURRENCY}) "
        f"[att={sum(1 for x in to_enrich if x[1])} "
        f"prc={sum(1 for x in to_enrich if x[2])} "
        f"link={sum(1 for x in to_enrich if x[4])}]"
    )

    enriched_map: dict[str, dict] = {}

    # BOUNDED CONCURRENCY — a small semaphore (not full asyncio.gather,
    # not a strictly sequential loop). This was sequential with a fixed
    # 0.3s gap between every call, which serialises ~8-70s of network +
    # LLM-validation latency PER EVENT — 6 events took 2m19s in
    # production. SerpAPI's free tier is a MONTHLY request quota
    # (100/mo), not a per-second rate limit, so a small concurrency cap
    # (not unlimited fan-out) keeps us polite to the API while cutting
    # wall-clock time ~N-fold without using any more quota.
    sem = asyncio.Semaphore(_ENRICH_CONCURRENCY)

    async def _enrich_one(event, need_att, need_prc, need_desc, need_link):
        async with sem:
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
                groq_client      = groq_client,
            )
            result = dict(data) if data else {}

            # ── Sponsor enrichment (3.9): secondary search when sponsors empty ──
            if not attendees_only and groq_client and serpapi_key and not (event.sponsors or "").strip():
                try:
                    sponsors_str = await enrich_sponsors(
                        event_name  = event.name,
                        year        = year,
                        serpapi_key = serpapi_key,
                        groq_client = groq_client,
                    )
                    if sponsors_str:
                        result["sponsors"] = sponsors_str
                except Exception as exc:
                    logger.debug(f"Sponsor enrichment error: {exc}")

            return event.id, (result or None)

    results = await asyncio.gather(
        *(_enrich_one(*args) for args in to_enrich),
        return_exceptions=True,
    )
    for r in results:
        if isinstance(r, Exception):
            logger.warning(f"SerpAPI enrichment task failed: {r}")
            continue
        event_id, data = r
        if data:
            enriched_map[event_id] = data

    att_n  = sum(1 for d in enriched_map.values() if d.get("est_attendees"))
    prc_n  = sum(1 for d in enriched_map.values() if d.get("price_description"))
    link_n = sum(1 for d in enriched_map.values() if d.get("event_link"))
    per_n  = sum(1 for d in enriched_map.values() if d.get("audience_personas"))
    logger.info(
        f"SerpAPI done — {len(enriched_map)}/{len(to_enrich)} enriched | "
        f"att={att_n} prc={prc_n} link={link_n} personas={per_n}"
    )
    return enriched_map
