"""
relevance/groq_ranker.py  —  LLM ranker with correct DB field mapping.

DB column reality (from Neon sample rows):
  POPULATED   : name, description, industry_tags, venue_name, city, country,
                source_url (eventseye page), start_date, end_date
  NULL / EMPTY: related_industries, event_cities, event_venues, website
  ALWAYS ZERO : est_attendees, ticket_price_usd
  ALWAYS EMPTY: audience_personas, price_description

Field priority used throughout this file:
  industry  → related_industries  → industry_tags  → category
  location  → event_cities        → city + country
  venue     → event_venues        → venue_name
  link      → website             → SerpAPI enriched → source_url (eventseye page)
                                  → Google search fallback

After SerpAPI enrichment, event dicts sent to the LLM include:
  est_attendees      (filled by SerpAPI or still 0 if not found)
  price_description  (filled by SerpAPI or "See website")
  audience_personas  (inferred from industry)
  event_link         (official site from SerpAPI organic results)
  serpapi_text       (AI-mode text blocks for LLM context)
"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional
from urllib.parse import quote_plus

from loguru import logger
from pydantic import BaseModel, field_validator

from config import get_settings
from models.event import EventORM, RankedEvent
from models.icp_profile import CompanyContext, ICPProfile
from relevance.llm_client import llm, estimate_tokens
from relevance.scorer import build_fallback_rationale

settings = get_settings()

# ── Pydantic schemas ───────────────────────────────────────────────

class GroqEventResult(BaseModel):
    id:             str
    fit_verdict:    str = "CONSIDER"
    verdict_notes:  str = ""
    key_numbers:    str = ""
    what_its_about: str = ""
    buyer_persona:  str = ""
    pricing:        str = ""
    # event_link intentionally absent — LLM never generates URLs.
    # Extra fields from old prompts are silently ignored via model_config.
    est_attendees:  int = 0

    model_config = {"extra": "ignore"}  # ignore event_link if LLM still returns it

    @field_validator("fit_verdict", mode="before")
    @classmethod
    def _check(cls, v) -> str:
        # Forgiving: never reject the whole event for a fixable verdict.
        v = str(v or "").strip().upper()
        if v not in {"GO", "CONSIDER", "SKIP"}:
            for known in ("GO", "SKIP", "CONSIDER"):
                if known in v:
                    return known
            return "CONSIDER"
        return v

    @field_validator("est_attendees", mode="before")
    @classmethod
    def _coerce_attendees(cls, v) -> int:
        # "12,000", "5000+", 5000.0, None, "unknown" → safe int
        if v is None or isinstance(v, bool):
            return 0
        if isinstance(v, (int, float)):
            return max(0, int(v))
        m = re.search(r"\d[\d,\.]*", str(v))
        if not m:
            return 0
        try:
            return max(0, int(float(m.group(0).replace(",", ""))))
        except ValueError:
            return 0


class GroqRankingResponse(BaseModel):
    ranked_events: List[GroqEventResult] = []

    model_config = {"extra": "ignore"}


class ValidationResult(BaseModel):
    id:                 str
    verdict_ok:         bool = True
    corrected_verdict:  Optional[str] = None
    hallucination_flag: bool = False
    issue:              Optional[str] = None

    model_config = {"extra": "ignore"}


class ValidationResponse(BaseModel):
    validations: List[ValidationResult] = []

    model_config = {"extra": "ignore"}


# ── Field accessors with correct fallback order ────────────────────

def _industry(event: EventORM) -> str:
    """Always returns the populated industry_tags string."""
    return (
        (getattr(event, "related_industries", "") or "").strip() or
        (event.industry_tags or "").strip() or
        (event.category or "").strip()
    )


def _venue(event: EventORM) -> str:
    return (
        (getattr(event, "event_venues", "") or "").strip() or
        (event.venue_name or "").strip()
    )


def _city(event: EventORM) -> str:
    ec = (getattr(event, "event_cities", "") or "").strip()
    if ec:
        return ec
    city    = (event.city or "").strip()
    country = (event.country or "").strip()
    # Normalise "UK - United Kingdom" → "United Kingdom"
    if " - " in country:
        country = country.split(" - ")[-1].strip()
    return f"{city}, {country}".strip(", ")


def _place(event: EventORM) -> str:
    parts = [p for p in [_venue(event), _city(event)] if p]
    return ", ".join(parts)


def _is_generic(text: str) -> bool:
    t = (text or "").lower().strip()
    if t in ("", "see website", "see event website", "—", "-"):
        return True
    bad = (
        "major global trade fair",
        "source: eventseye", "sourced from eventseye",
        "trade show / expo sourced from",
        "professional conference sourced from",
        "see 10times listing",
    )
    return any(b in t for b in bad)


def _is_venue_url(url: str) -> bool:
    from enrichment.serp_enricher import _is_venue_url as _check
    return _check(url)


def _google_fallback(event: EventORM) -> str:
    year = (event.start_date or "")[:4] or ""
    city = (event.city or "").strip()
    q    = " ".join(filter(None, [event.name, year, city, "official website"]))
    return f"https://www.google.com/search?q={quote_plus(q)}"


# ── URL validation helpers ────────────────────────────────────────
# Domains that are known event-platform sources; source_url from these
# is always event-specific because it was scraped from that platform's
# event detail page, not a listing or homepage.
_EVENT_PLATFORM_DOMAINS: frozenset[str] = frozenset({
    "eventseye.com",        # source_url = /fairs/f-{slug}-{id}-1.html
    "ticketmaster.com",     # source_url = /event/{event-slug}/event/{id}
    "ticketmaster.co.uk",
    "ticketmaster.com.au",
    "eventbrite.com",       # source_url = /e/{slug}-{id}/
    "predicthq.com",        # internal API source
    "allevents.in",
    "luma.com",             # luma event pages
    "lu.ma",
    "10times.com",          # only source_url (event detail), not organic results
    "konfhub.com",
    "townscript.com",
    "imtj.com",
    "10times.in",
})

def _is_platform_event_url(url: str) -> bool:
    """
    Returns True if the URL is from a known event platform where the
    source_url is always a specific event detail page (not a listing).
    EventsEye, Ticketmaster, Eventbrite, PredictHQ, etc.
    """
    if not url or not url.startswith(("http://", "https://")):
        return False
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower().lstrip("www.")
        path   = urlparse(url).path or ""
        for pd in _EVENT_PLATFORM_DOMAINS:
            if domain == pd or domain.endswith("." + pd):
                # Extra guard: path must not be just "/" or empty
                clean_path = path.strip("/")
                if clean_path:
                    return True
    except Exception:
        pass
    return False


def _is_homepage_url(url: str) -> bool:
    """
    True when a URL is the organiser's root domain or a shallow generic
    section — i.e. NOT an edition-specific event page.

    Returns True (= homepage/useless) for:
      https://marketingfestival.in/          no path
      https://peoplematters.in/techhr/       1 short segment, no year
      https://aws.amazon.com/events/         generic section name

    Returns False (= keep it) for:
      https://peoplematters.in/techhr/techhr-india-2026/    has year
      https://marketingfestival.in/summit/2026-edition/     has year
      https://www.idc.com/ap/events/india-2026              has year
    """
    if not url:
        return True
    try:
        from urllib.parse import urlparse
        parsed     = urlparse(url)
        path_parts = [p for p in parsed.path.strip("/").split("/") if p]

        if not path_parts:                       # root domain — homepage
            return True

        full_path = "/".join(path_parts).lower()

        # If a 4-digit year appears anywhere in the path → edition-specific
        if re.search(r"20\d{2}", full_path):
            return False

        # Single segment
        if len(path_parts) == 1:
            seg = path_parts[0].lower()
            _GENERIC = {
                "events", "event", "conferences", "conference", "register",
                "registration", "attend", "summit", "expo", "fair",
                "news", "blog", "press", "media", "about", "contact",
                "en", "home", "index", "default",
            }
            if seg in _GENERIC:
                return True
            if len(seg) <= 10:      # short single segment with no year
                return True

        # Two segments: treat as homepage if the last segment is a known generic section
        # and there is no year anywhere in the full path
        if len(path_parts) >= 2 and not re.search(r"20\d{2}", full_path):
            last = path_parts[-1].lower()
            _GENERIC_SECTIONS = {
                "register", "attend", "overview", "home", "index", "info",
                "events", "event", "en", "default", "conferences", "conference",
                "us", "ap", "apj", "emea", "global", "worldwide",
            }
            # All remaining segments after the first are generic
            if all(p.lower() in _GENERIC_SECTIONS or len(p) <= 4
                   for p in path_parts[1:]):
                return True

    except Exception:
        pass
    return False


def _is_google_url(url: str) -> bool:
    """True for any Google search/URL that is not a real event page."""
    if not url:
        return False
    lo = url.lower()
    return (
        lo.startswith("https://www.google.com/search") or
        lo.startswith("http://www.google.com/search") or
        "google.com/search?" in lo
    )


def _verify_link(url: str) -> bool:
    """
    Master URL validator — returns True only for a link we're confident
    is a real, event-specific page worth showing to the user.

    Rejects:
      • Empty strings
      • Google search fallback URLs
      • Venue / social / aggregator domains
      • Root-domain homepages (no path)
      • Known generic section paths (/events, /en, etc.)
    """
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        return False
    if _is_google_url(url):
        return False
    if _is_venue_url(url):
        return False
    if _is_homepage_url(url):
        return False
    return True


def _best_link(event: EventORM, enrichments: dict) -> str:
    """
    Returns the best verified event-specific URL, or "" if none found.

    Priority order (most trustworthy → least):
      1. source_url from a known event platform
         (EventsEye /fairs/f-*, Ticketmaster /event/*, Eventbrite /e/*, …)
         These are always event-specific by construction — scraped from
         the platform's event detail page, not a listing or homepage.

      2. SerpAPI-enriched link (year-specific scoring from live web search)

      3. DB registration_url — verified against _verify_link()

      4. DB website — verified against _verify_link()

      5. DB source_url (non-platform) — last resort, still verified

    Returns "" (empty string) when nothing passes verification.
    The frontend renders "Link not available" for empty strings — never
    shows a Google search URL or a misleading homepage link.
    """
    # 1. Platform source_url — always event-specific by construction
    src_url = (event.source_url or "").strip()
    if src_url and _is_platform_event_url(src_url):
        return src_url

    # 2. SerpAPI-enriched link (live, year-specific verification)
    serp = (enrichments.get("event_link") or enrichments.get("website") or "").strip()
    if _verify_link(serp):
        return serp

    # 3. DB registration_url
    reg = (event.registration_url or "").strip()
    if _verify_link(reg):
        return reg

    # 4. DB website
    web = (getattr(event, "website", "") or "").strip()
    if _verify_link(web):
        return web

    # 5. Non-platform source_url (e.g. Seed events, Wikipedia, TechCrunch)
    if src_url and _verify_link(src_url):
        return src_url

    # Nothing passed verification
    return ""


def _personas(event: EventORM, enrichments: dict, llm_value: str = "") -> str:
    db = (event.audience_personas or "").strip()
    if db and not _is_generic(db):
        return db
    if llm_value and not _is_generic(llm_value):
        return llm_value
    ep = enrichments.get("audience_personas", "")
    if ep:
        return ep
    # Last resort: infer from industry_tags
    from enrichment.serp_enricher import _infer_personas
    ind = _industry(event)
    if ind:
        inferred = _infer_personas("", ind)
        if inferred:
            return inferred
    return ""


def _pricing(event: EventORM, enrichments: dict, llm_value: str = "") -> str:
    pd = (event.price_description or "").strip()
    if pd and not _is_generic(pd):
        return pd
    if event.ticket_price_usd and event.ticket_price_usd > 0:
        return f"From ${event.ticket_price_usd:,.0f}"
    if llm_value and not _is_generic(llm_value):
        return llm_value
    ep = enrichments.get("price_description", "")
    if ep and not _is_generic(ep):
        return ep
    return "See website"


def _description(event: EventORM, enrichments: dict, llm_value: str = "") -> str:
    for v in [event.short_summary, event.description, llm_value,
              enrichments.get("description", "")]:
        if v and not _is_generic(v):
            return v[:300]
    return (event.description or event.short_summary or "")[:300]


def _key_numbers(event: EventORM, enrichments: dict, llm_nums: str = "", llm_att: int = 0) -> str:
    # LLM key_numbers if not generic
    if llm_nums and not _is_generic(llm_nums):
        return llm_nums
    # Build from known numeric fields
    parts: list[str] = []
    att = event.est_attendees or llm_att or enrichments.get("est_attendees", 0)
    if att:
        parts.append(f"{att:,} attendees")
    vip = getattr(event, "vip_count", 0) or 0
    if vip:
        parts.append(f"{vip} VIPs")
    spk = getattr(event, "speaker_count", 0) or 0
    if spk:
        parts.append(f"{spk} speakers")
    if parts:
        return "; ".join(parts)
    # Fall back to first sentence of description
    desc = event.description or ""
    if desc and not _is_generic(desc):
        for s in re.split(r"[.!?]", desc):
            s = s.strip()
            if len(s) > 30:
                return s[:120]
    return "See event website"


# ── System prompt ──────────────────────────────────────────────────

def _system_prompt(profile: ICPProfile, ctx: Optional[CompanyContext]) -> str:
    company_block = ""
    if ctx:
        parts = []
        if ctx.company_name:  parts.append(f"Company: {ctx.company_name}")
        if ctx.location:      parts.append(f"HQ: {ctx.location}")
        if ctx.what_we_do:    parts.append(f"What they sell: {ctx.what_we_do[:500]}")
        if ctx.what_we_need:  parts.append(f"Event goals: {ctx.what_we_need[:400]}")
        if ctx.deck_text:     parts.append(f"Deck excerpt:\n{ctx.deck_text[:1800]}")
        if parts:
            company_block = "\n\nCOMPANY CONTEXT:\n" + "\n".join(parts)

    return f"""You are an expert B2B sales strategist recommending trade events.

CLIENT ICP:
  Target industries: {', '.join(profile.target_industries)}
  Target buyer roles: {', '.join(profile.target_personas)}
  Focus geographies: {', '.join(profile.target_geographies)}
  Preferred formats: {', '.join(profile.preferred_event_types)}
  Company description: {profile.company_description[:300]}
{company_block}

VERDICT DEFINITIONS:
  GO      = Strong industry + buyer role match. Clear pipeline opportunity.
  CONSIDER = Partial overlap. Buyer profiles partially match or geography is borderline.
  SKIP    = Weak or no alignment.

CRITICAL WRITING RULES:
  ✅ Use ONLY fields visible in the event data (industry_focus, description, typical_attendees, location).
  ✅ Describe what the event ACTUALLY covers based on its industry_focus and description.
  ✅ Explain WHY it's relevant (or not) in terms of sales opportunity.
  ✅ If serpapi_text has attendee or pricing data, extract it accurately.
  ✅ Use event_link from the event data for the link field.

  ❌ NEVER say an event covers "AI/ML", "Technology", "Cloud" unless those words appear
     in the event's own industry_focus, description, or serpapi_text.
  ❌ NEVER project the client's target industries onto the event.
  ❌ NEVER use code field names like event.industry_tags, profile.target_personas.
  ❌ Do not fabricate attendee numbers or prices — use "See event website" if unknown.

Output ONLY valid JSON. No text outside JSON."""


VALIDATION_SYS = """You are a QA reviewer for B2B event intelligence.

For each verdict, check:
1. Does the verdict match the event data (not the client's industry wishlist)?
2. Does verdict_notes describe what the event ACTUALLY covers?
3. Are there any developer field names in the text? → hallucination_flag=true
4. Does it claim industries not in the event's own data? → hallucination_flag=true

Return ONLY this JSON:
{"validations":[{"id":"...","verdict_ok":true,"corrected_verdict":null,"hallucination_flag":false,"issue":null}]}"""


# ── Event serialiser for LLM ───────────────────────────────────────

def _event_dict(
    event:      EventORM,
    score:      float,
    tier:       str,
    detail:     dict,
    enrichments: dict,
) -> dict:
    """Build the dict sent to the LLM — uses only populated DB fields + enrichments."""
    return {
        "id":                   event.id,
        "name":                 event.name,
        "description":          _description(event, enrichments)[:400],
        "start_date":           event.start_date,
        "end_date":             event.end_date or event.start_date,
        "location":             _place(event),
        "venue":                _venue(event),
        "is_virtual":           event.is_virtual,
        "is_hybrid":            event.is_hybrid,
        "est_attendees":        event.est_attendees or enrichments.get("est_attendees", 0),
        "industry_focus":       _industry(event),
        "typical_attendees":    _personas(event, enrichments),
        "pricing":              _pricing(event, enrichments),
        "event_link":           _best_link(event, enrichments),
        "serpapi_text":         enrichments.get("serpapi_text", "")[:2000],
        "serpapi_results":      enrichments.get("serpapi_results", []),
        "pre_score":            score,
        "pre_tier":             tier,
        "rule_matched_industries": detail.get("industry_matched", []),
        "rule_matched_personas":   detail.get("persona_matched", []),
        "geo_match":               detail.get("geo_matched", ""),
    }


def _profile_dict(profile: ICPProfile) -> dict:
    return {
        "company_name":       profile.company_name,
        "what_we_do":         profile.company_description[:400],
        "target_industries":  profile.target_industries,
        "target_buyer_roles": profile.target_personas,
        "target_locations":   profile.target_geographies,
        "preferred_formats":  profile.preferred_event_types,
    }


def _ranking_prompt(events_dicts: list, profile_dict: dict) -> str:
    # Strip event_link from every event dict sent to the LLM.
    # The LLM must NEVER generate or modify links — it hallucinates them.
    # Links are resolved exclusively by _best_link() after the LLM call.
    safe_events = []
    for ev in events_dicts:
        ev_copy = dict(ev)
        ev_copy.pop("event_link", None)
        ev_copy.pop("website", None)
        ev_copy.pop("registration_url", None)
        ev_copy.pop("source_url", None)
        safe_events.append(ev_copy)

    return f"""CLIENT ICP:
{json.dumps(profile_dict, indent=2)}

EVENTS:
{json.dumps(safe_events, indent=2)}

For each event:
- what_its_about: describe based on industry_focus + description fields ONLY
- buyer_persona: use typical_attendees field, or infer from industry_focus
- pricing: use pricing field from event data, or extract from serpapi_text
- est_attendees: extract number from serpapi_text if available, else 0
- key_numbers: attendee count + any numeric facts from serpapi_text; empty string if unknown
- verdict_notes: explain the relevance in plain sales-analyst language

DO NOT generate or guess any URLs. Links are resolved from the database separately.

Return JSON:
{{
  "ranked_events": [
    {{
      "id": "<id>",
      "fit_verdict": "GO|CONSIDER|SKIP",
      "verdict_notes": "<2-3 sentences about what the event is and its sales relevance>",
      "key_numbers": "<numbers from serpapi_text or empty string>",
      "what_its_about": "<what this event covers based on its own data>",
      "buyer_persona": "<who attends based on industry>",
      "pricing": "<from serpapi_text or 'See website'>",
      "est_attendees": 0
    }}
  ]
}}"""


# ── Token-budgeted chunking ────────────────────────────────────────

# Completion budget per event in a ranking response (~7 short fields).
_COMPLETION_TOKENS_PER_EVENT = 180
_COMPLETION_TOKENS_MIN       = 600


def _completion_budget(n_events: int) -> int:
    return min(settings.groq_max_tokens,
               max(_COMPLETION_TOKENS_MIN, n_events * _COMPLETION_TOKENS_PER_EVENT))


def _chunk_events_by_budget(events_dicts: list, system: str, profile_dict: dict) -> list[list]:
    """
    Greedily pack event dicts into chunks whose full prompt (system +
    scaffold + events JSON + completion budget) fits under the TPM limit.
    Guarantees we never send a request we know will 413.
    """
    # Fixed part of every request: system prompt + ranking prompt with no events.
    scaffold = _ranking_prompt([], profile_dict)
    fixed_tokens = estimate_tokens(system) + estimate_tokens(scaffold)

    chunks: list[list] = []
    current: list = []
    current_tokens = 0

    for ev in events_dicts:
        ev_tokens = estimate_tokens(json.dumps(ev, indent=2))
        # A single oversized event (huge serpapi payload) must still fit:
        # slim its enrichment bulk rather than guarantee a 413.
        if fixed_tokens + ev_tokens + _completion_budget(1) > settings.groq_tpm_limit * 0.9:
            ev = dict(ev)
            ev.pop("serpapi_results", None)
            ev["serpapi_text"] = (ev.get("serpapi_text") or "")[:600]
            ev["description"]  = (ev.get("description") or "")[:200]
            ev_tokens = estimate_tokens(json.dumps(ev, indent=2))
        # Would adding this event still fit (incl. per-event completion budget)?
        prospective = fixed_tokens + current_tokens + ev_tokens \
            + _completion_budget(len(current) + 1)
        if current and prospective > settings.groq_tpm_limit * 0.9:
            chunks.append(current)
            current, current_tokens = [], 0
        current.append(ev)
        current_tokens += ev_tokens

    if current:
        chunks.append(current)
    return chunks


# ── Hallucination guard ────────────────────────────────────────────

def _is_hallucinated(
    result:  GroqEventResult,
    event:   EventORM,
    profile: ICPProfile,
    detail:  dict,
) -> bool:
    notes = (result.verdict_notes or "").lower().strip()
    if len(notes) < 20:
        return True
    if any(p in notes for p in ("event.industry", "profile.target", "icp field",
                                 "event.name", "profile.company")):
        return True

    event_text  = (
        f"{event.name} {_industry(event)} {event.description or ''} "
        f"{event.audience_personas or ''} {event.category or ''}"
    ).lower()
    matched_ind = {s.lower() for s in detail.get("industry_matched", [])}

    for ind in profile.target_industries or []:
        tokens = [
            t for t in re.split(r"[^a-z0-9]+", ind.lower())
            if len(t) > 2
        ]
        if not tokens:
            continue
        mentioned = any(t in notes for t in tokens)
        evidenced = (
            any(t in event_text for t in tokens) or
            ind.lower() in matched_ind
        )
        negated = any(
            f"not {t}" in notes or f"outside {t}" in notes
            for t in tokens
        )
        if mentioned and not evidenced and not negated:
            logger.debug(
                f"Hallucination: '{ind}' in notes for '{event.name[:50]}' "
                f"but not in event data"
            )
            return True
    return False


# ── Main entry ─────────────────────────────────────────────────────

async def rank_with_groq(
    events:      List[EventORM],
    profile:     ICPProfile,
    pre_scores:  Dict[str, float],
    pre_tiers:   Dict[str, str],
    pre_details: Dict[str, dict],
    company_ctx: Optional[CompanyContext] = None,
    enrichments: Dict[str, dict]  = None,
    deal_size_category: str = "medium",
) -> List[RankedEvent]:

    enrichments  = enrichments or {}
    groq_results: Dict[str, GroqEventResult] = {}
    hallucinated: set[str] = set()

    if events:
        events_dicts = [
            _event_dict(
                e,
                pre_scores.get(e.id, 0.0),
                pre_tiers.get(e.id, "SKIP"),
                pre_details.get(e.id, {}),
                enrichments.get(e.id, {}),
            )
            for e in events
        ]

        system       = _system_prompt(profile, company_ctx)
        profile_dict = _profile_dict(profile)

        # Agent 1 — ranker, token-budgeted chunking.
        # If the full prompt won't fit under the free-tier TPM ceiling,
        # split events into chunks that each fit and merge the results.
        full_prompt = _ranking_prompt(events_dicts, profile_dict)
        if llm.fits_budget(system, full_prompt,
                           completion_tokens=_completion_budget(len(events_dicts))):
            chunks = [events_dicts]
        else:
            chunks = _chunk_events_by_budget(events_dicts, system, profile_dict)
            logger.info(
                f"Ranker: {len(events_dicts)} events exceed TPM budget — "
                f"split into {len(chunks)} chunks"
            )

        for ci, chunk in enumerate(chunks):
            parsed = await llm.chat_json(
                system,
                _ranking_prompt(chunk, profile_dict),
                label=f"ranker[{ci + 1}/{len(chunks)}]",
                schema=GroqRankingResponse,
                max_completion_tokens=_completion_budget(len(chunk)),
                timeout=settings.groq_timeout_seconds,
            )
            if parsed is None:
                logger.warning(f"Ranker chunk {ci + 1}/{len(chunks)} failed — "
                               "events fall back to rule-based tier")
                continue
            groq_results.update({r.id: r for r in parsed.ranked_events})
        logger.info(f"Ranker: {len(groq_results)}/{len(events_dicts)} events ranked")

        # Agent 2 — validator (hallucination check).
        # Cheap and non-blocking: slim payload, short hard timeout. If it
        # fails or times out we just log and proceed — the local
        # _is_hallucinated heuristic still runs on every result.
        if len(groq_results) >= 3:
            slim_events = [
                {
                    "id":              ev["id"],
                    "name":            ev["name"],
                    "industry_focus":  ev["industry_focus"],
                    "location":        ev["location"],
                    "description":     (ev.get("description") or "")[:150],
                    "pre_tier":        ev.get("pre_tier", ""),
                }
                for ev in events_dicts
            ]
            primary_list = [
                {"id": r.id, "fit_verdict": r.fit_verdict,
                 "verdict_notes": r.verdict_notes[:300], "key_numbers": r.key_numbers}
                for r in groq_results.values()
            ]
            val_user = (f"SOURCE DATA:\n{json.dumps(slim_events, indent=2)}\n\n"
                        f"VERDICTS:\n{json.dumps(primary_list, indent=2)}")
            val_completion = min(1200, 60 * len(primary_list) + 200)
            val = None
            if llm.fits_budget(VALIDATION_SYS, val_user,
                               completion_tokens=val_completion):
                val = await llm.chat_json(
                    VALIDATION_SYS,
                    val_user,
                    label="validator",
                    schema=ValidationResponse,
                    max_completion_tokens=val_completion,
                    timeout=20,           # hard cap — never 45s of dead time
                )
            else:
                logger.warning("Validator payload over TPM budget — skipping "
                               "(local hallucination heuristic still applies)")
            if val is None:
                logger.warning("Validator unavailable/failed — proceeding with "
                               "ranker results")
            else:
                corrections = 0
                for v in val.validations:
                    if v.hallucination_flag:
                        hallucinated.add(v.id)
                        logger.warning(f"Validator flagged: {v.id} — {v.issue}")
                    cv = (v.corrected_verdict or "").strip().upper()
                    if (not v.verdict_ok and cv in {"GO", "CONSIDER", "SKIP"}
                            and v.id in groq_results):
                        old = groq_results[v.id].fit_verdict
                        groq_results[v.id] = groq_results[v.id].model_copy(
                            update={"fit_verdict": cv}
                        )
                        corrections += 1
                        logger.info(f"Corrected {v.id}: {old}→{cv}")
                logger.info(
                    f"Validation: {corrections} corrected, {len(hallucinated)} flagged"
                )

    # ── Build final RankedEvent list ───────────────────────────────
    ranked: List[RankedEvent] = []
    for event in events:
        score  = pre_scores.get(event.id, 0.0)
        tier   = pre_tiers.get(event.id, "SKIP")
        detail = pre_details.get(event.id, {})
        ev_en  = enrichments.get(event.id, {})

        llm_about   = ""
        llm_persona = ""
        llm_pricing = ""
        llm_att     = 0
        llm_nums    = ""

        if event.id in groq_results and event.id not in hallucinated:
            gr = groq_results[event.id]
            if _is_hallucinated(gr, event, profile, detail):
                logger.warning(f"Replacing hallucinated rationale: '{event.name[:50]}'")
                verdict   = tier
                rationale = build_fallback_rationale(event, profile, detail, score, tier)
            else:
                verdict   = gr.fit_verdict
                rationale = gr.verdict_notes
                llm_about   = gr.what_its_about or ""
                llm_persona = gr.buyer_persona  or ""
                llm_pricing = gr.pricing        or ""
                # URL never read from LLM response — _best_link() handles all links
                llm_att     = gr.est_attendees  or 0
                llm_nums    = gr.key_numbers    or ""
        else:
            verdict   = tier
            rationale = build_fallback_rationale(event, profile, detail, score, tier)

        # Link resolution: DB/SerpAPI only — LLM output never used for links
        final_link = _best_link(event, ev_en)
        final_att  = (
            event.est_attendees or
            llm_att or
            ev_en.get("est_attendees", 0) or
            0
        )

        ranked.append(RankedEvent(
            id              = event.id,
            event_name      = event.name,
            date            = (
                event.start_date +
                (f" – {event.end_date}"
                 if event.end_date and event.end_date != event.start_date else "")
            ),
            place           = _place(event),
            event_link      = final_link,
            what_its_about  = _description(event, ev_en, llm_about)[:200],
            key_numbers     = _key_numbers(event, ev_en, llm_nums, llm_att),
            industry        = _industry(event),
            buyer_persona   = _personas(event, ev_en, llm_persona),
            pricing         = _pricing(event, ev_en, llm_pricing),
            pricing_link    = final_link,
            fit_verdict     = verdict,
            verdict_notes   = rationale,
            sponsors        = event.sponsors or "",
            speakers_link   = event.speakers_url or "",
            agenda_link     = event.agenda_url or "",
            relevance_score = score,
            source_platform = event.source_platform,
            est_attendees   = final_att,
            organizer       = getattr(event, "organizer", "") or "",
            website         = final_link,
            serpapi_enriched= bool(ev_en),
        ))

    return ranked
