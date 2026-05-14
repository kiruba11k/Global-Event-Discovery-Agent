"""
relevance/scorer.py  —  DB-aware scoring for EventsEye-style trade show data.

Key facts about the Neon DB (from actual rows):
  ✅ industry_tags       populated  ("Metal Working Industries, Mechanical Components")
  ✅ venue_name          populated  ("Singapore Expo")
  ✅ city / country      populated  ("Singapore", "Singapore")
  ✅ description         populated  (event description text)
  ✅ name                populated
  ✅ source_url          populated  (eventseye.com event page)
  ❌ related_industries  NULL / ""   — never use as primary
  ❌ event_cities        NULL / ""   — never use as primary
  ❌ event_venues        NULL / ""   — never use as primary
  ❌ website             NULL / ""   — never use as primary
  ❌ est_attendees       = 0        — do NOT filter on this; SerpAPI fills later
  ❌ audience_personas   ""         — SerpAPI fills later

Pipeline order for every field:
  industry  : related_industries  → industry_tags  → category → ""
  location  : event_cities        → city + country
  venue     : event_venues        → venue_name
  link      : website             → source_url (eventseye page) → registration_url

TAXONOMY BRIDGE
--------------
EventsEye uses its own taxonomy ("Metal Working Industries", "Catering and Hospitality
Industries") that doesn't match user-facing profile industries ("Manufacturing",
"Food & Beverage").  We maintain a forward map so that a profile targeting
"Manufacturing" scores events tagged "Metal Working Industries", "Industrial Machinery",
etc., correctly without false positives.

SCORING WEIGHTS (rule-only mode, no FAISS):
  Industry match  0.35
  Persona match   0.25
  Geography match 0.22
  Event type      0.10
  Attendee tier   0.08  (0 if unknown — not penalised)
"""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

from loguru import logger

from config import get_settings
from models.event import EventORM
from models.icp_profile import ICPProfile

settings = get_settings()

TIER_GO       = "GO"
TIER_CONSIDER = "CONSIDER"
TIER_SKIP     = "SKIP"

# Rule-only thresholds (no FAISS / cosine)
RULE_GO_THRESHOLD       = 0.38
RULE_CONSIDER_THRESHOLD = 0.18


# ══════════════════════════════════════════════════════════════════════
# TAXONOMY BRIDGE
# Maps normalised profile industry tokens → EventsEye industry segments
# that semantically overlap.  Keys are lowercase, comma-separated tokens
# that the user might choose.  Values are sets of lowercase substrings
# to look for inside an event's industry_tags string.
# ══════════════════════════════════════════════════════════════════════
_PROFILE_TO_EVENTSEYE: dict[str, list[str]] = {
    # Manufacturing / Industrial
    "manufacturing":        ["manufactur", "metal work", "mechanical", "industrial", "machiner",
                             "machine tool", "welding", "casting", "forging", "cnc", "automation",
                             "robotics", "production", "factory", "stamping", "sheet metal",
                             "engineering", "material", "alloy", "steel", "aluminium"],
    "industrial":           ["industrial", "manufactur", "metal", "mechanical", "machiner",
                             "engineering", "factory"],
    "engineering":          ["engineering", "manufactur", "metal", "mechanical", "machiner",
                             "structural", "civil", "aerospace"],
    # Technology / IT
    "technology":           ["technolog", "it ", "information technology", "software",
                             "digital", "compute", "network", "telecom", "electronic",
                             "semiconductor", "iot", "smart", "multimedia", "cad", "cam"],
    "information technology": ["information technology", "it ", "software", "digital",
                                "compute", "network"],
    "it":                   ["it ", "information technology", "software", "compute", "network",
                             "digital"],
    "software":             ["software", "digital", "compute", "it ", "saas", "cloud",
                             "application"],
    "ai":                   ["artificial intelligence", "ai", "machine learning", "deep learning",
                             "data science", "analytics", "automation", "robotics"],
    "ai / machine learning": ["artificial intelligence", "ai", "machine learning", "analytics",
                               "data science", "deep learning"],
    "cloud computing":      ["cloud", "saas", "paas", "iaas", "data center", "hosting",
                             "virtualisation", "digital transformation"],
    "cybersecurity":        ["cyber", "security", "infosec", "information security",
                             "network security", "data protection"],
    "digital":              ["digital", "technolog", "software", "compute", "internet",
                             "iot", "smart"],
    # Finance / Fintech
    "fintech":              ["fintech", "financial technology", "digital banking", "payment",
                             "insurtech", "regtech", "blockchain", "cryptocurrency"],
    "finance":              ["finance", "banking", "financial", "investment", "capital market",
                             "insurance", "treasury", "fintech", "accounting"],
    "banking":              ["banking", "finance", "financial", "payment", "fintech"],
    # Healthcare / Life Sciences
    "healthcare":           ["healthcare", "health", "medical", "medtech", "pharma",
                             "biotech", "hospital", "clinical", "dental", "optical",
                             "nursing", "life science", "diagnostic", "telemedicine"],
    "medtech":              ["medtech", "medical device", "medical equipment", "diagnostic",
                             "imaging", "surgical"],
    "pharma":               ["pharma", "pharmaceutical", "drug", "biotech", "life science",
                             "clinical", "laboratory"],
    # Logistics / Supply Chain
    "logistics":            ["logistic", "supply chain", "transport", "freight", "shipping",
                             "warehousing", "cargo", "courier", "last mile", "fleet",
                             "handling", "intralogistic", "distribution", "port"],
    "supply chain":         ["supply chain", "logistic", "procurement", "sourcing",
                             "warehousing", "inventory", "distribution"],
    "transportation":       ["transport", "logistic", "freight", "shipping", "automotive",
                             "truck", "rail", "aviation", "maritime", "fleet"],
    # Retail / E-commerce / Consumer
    "retail":               ["retail", "ecommerce", "consumer", "fmcg", "fashion",
                             "merchandise", "shopping", "omnichannel", "pos"],
    "ecommerce":            ["ecommerce", "e-commerce", "online retail", "digital commerce",
                             "marketplace", "d2c"],
    "consumer goods":       ["consumer", "fmcg", "household", "appliance", "personal care",
                             "food", "beverage", "retail"],
    # Food & Beverage / Hospitality
    "food & beverage":      ["food processing", "food", "beverage", "catering", "hospitality",
                             "restaurant", "hotel", "bakery", "dairy", "meat", "seafood",
                             "organic", "wine", "spirits"],
    "food":                 ["food processing", "food", "beverage", "catering", "bakery",
                             "dairy", "seafood", "agri"],
    "hospitality":          ["hospitality", "catering", "hotel", "restaurant", "food service",
                             "tourism", "travel"],
    # Energy / Environment
    "energy":               ["energy", "oil", "gas", "petroleum", "renewable", "solar",
                             "wind", "nuclear", "power", "electricity", "utility"],
    "cleantech":            ["cleantech", "renewable", "solar", "wind", "green energy",
                             "sustainable", "environmental", "waste", "water treatment"],
    "sustainability":       ["sustainab", "environmental", "cleantech", "green", "renewable",
                             "circular economy", "esg", "carbon"],
    # Real Estate / Construction
    "construction":         ["construction", "build", "architect", "real estate", "civil",
                             "infrastructure", "contractor", "property"],
    "real estate":          ["real estate", "property", "construction", "land", "housing"],
    # Mining / Resources
    "mining":               ["mining", "mineral", "quarry", "ore", "coal", "metals",
                             "extraction", "petroleum"],
    # Media / Print / Marketing
    "marketing":            ["marketing", "advertising", "media", "digital marketing",
                             "martech", "brand", "pr", "communication", "promotion"],
    "media":                ["media", "publishing", "broadcast", "print", "graphic",
                             "content", "advertising"],
    # HR / Education
    "hr tech":              ["human resource", "hr", "talent", "recruitment", "workforce",
                             "payroll", "people management", "future of work"],
    "education":            ["education", "training", "learning", "university", "academic",
                             "e-learning", "professional development"],
    # Agriculture
    "agriculture":          ["agriculture", "agri", "farming", "crop", "livestock",
                             "aquaculture", "fishery", "agritech"],
    # Travel / Tourism
    "travel":               ["travel", "tourism", "hospitality", "airline", "hotel",
                             "destination", "mice"],
    # Automotive
    "automotive":           ["automotive", "vehicle", "car", "truck", "electric vehicle",
                             "ev", "mobility", "fleet"],
    # Fashion / Textile
    "fashion":              ["fashion", "textile", "clothing", "apparel", "fabric",
                             "garment", "leather", "footwear"],
    # Printing / Packaging
    "printing":             ["printing", "packaging", "graphic", "inkjet", "label",
                             "flexo", "offset"],
}


def _get_industry(event: EventORM) -> str:
    """
    Return the best available industry string from DB columns.
    Priority: related_industries → industry_tags → category
    For this DB: related_industries is always NULL/empty, so industry_tags is used.
    """
    ri = getattr(event, "related_industries", None)
    if ri and ri.strip():
        return ri.strip()
    it = event.industry_tags or ""
    if it.strip():
        return it.strip()
    return (event.category or "").strip()


def _get_event_text(event: EventORM) -> str:
    """
    Build a comprehensive searchable text blob using only populated columns.
    Uses industry_tags / venue_name / city / country — not the NULL new columns.
    """
    industry = _get_industry(event)
    # Location: prefer event_cities if populated, fall back to city/country
    ec = (getattr(event, "event_cities", "") or "").strip()
    location = ec if ec else f"{event.city or ''} {event.country or ''}".strip()
    # Venue: prefer event_venues if populated, fall back to venue_name
    ev = (getattr(event, "event_venues", "") or "").strip()
    venue = ev if ev else (event.venue_name or "").strip()

    parts = [
        event.name or "",
        industry,
        event.description or "",
        event.short_summary or "",
        event.audience_personas or "",
        event.category or "",
        venue,
        location,
        getattr(event, "organizer", "") or "",
    ]
    return " ".join(p for p in parts if p).lower()


def _get_geo_text(event: EventORM) -> str:
    """Return a clean city+country string for geo matching."""
    ec = (getattr(event, "event_cities", "") or "").strip()
    if ec:
        return ec.lower()
    city    = (event.city or "").strip()
    country = (event.country or "").strip()
    # Strip known suffixes like "UK - United Kingdom" → keep just "United Kingdom"
    if " - " in country:
        country = country.split(" - ")[-1].strip()
    return f"{city} {country}".lower().strip()


# ── Tokenisation with word-boundary awareness ──────────────────────

def _tokenise(text: str) -> List[str]:
    """
    Split by standard delimiters and return unique tokens of length > 2.
    Does NOT further split tokens by whitespace to avoid sub-word matches
    (e.g. "machine" inside "mechanical").
    """
    raw_parts = re.split(r"[/,|;]", text)
    tokens: list[str] = []
    seen: set[str] = set()
    for part in raw_parts:
        t = part.strip().lower()
        if t and len(t) > 2 and t not in seen:
            tokens.append(t)
            seen.add(t)
            # Also add significant individual words from multi-word tokens
            for w in t.split():
                if len(w) > 3 and w not in seen:
                    tokens.append(w)
                    seen.add(w)
    return tokens


def _word_in_text(word: str, text: str) -> bool:
    """True only if `word` appears as a complete word in `text`."""
    return bool(re.search(r"\b" + re.escape(word) + r"\b", text, re.I))


# ── Industry matching (profile → event) ───────────────────────────

def _score_industry(event: EventORM, profile: ICPProfile) -> Tuple[float, list[str]]:
    """
    Score industry match using a two-pass approach:
    Pass 1: Direct token match between profile industry names and event text
    Pass 2: Taxonomy bridge — map profile industry to EventsEye synonyms
    Returns (score 0..0.35, list of matched profile industry values).
    """
    if not profile.target_industries:
        return 0.0, []

    industry_str = _get_industry(event).lower()
    event_text   = _get_event_text(event)
    matched: list[str] = []

    for prof_ind in profile.target_industries:
        pi_lower = prof_ind.lower().strip()
        already  = False

        # Pass 1: direct word match in event text
        pi_words = [w for w in re.split(r"[\s/,\-&]+", pi_lower) if len(w) > 2]
        if any(_word_in_text(w, event_text) for w in pi_words):
            matched.append(prof_ind)
            already = True

        if already:
            continue

        # Pass 2: taxonomy bridge
        for key, synonyms in _PROFILE_TO_EVENTSEYE.items():
            # Does this profile industry activate this taxonomy key?
            key_words = key.split()
            if not all(_word_in_text(kw, pi_lower) or kw in pi_lower for kw in key_words):
                continue
            # Does the event's industry_tags contain any synonym?
            for syn in synonyms:
                if syn in industry_str:
                    matched.append(prof_ind)
                    already = True
                    break
            if already:
                break

    matched = list(dict.fromkeys(matched))  # preserve order, deduplicate

    n = len(matched)
    if   n >= 3: score = 0.35
    elif n == 2: score = 0.28
    elif n == 1: score = 0.20
    else:
        score = 0.0

    return round(score, 4), matched


# ── Persona matching ───────────────────────────────────────────────

def _score_persona(event: EventORM, profile: ICPProfile) -> Tuple[float, list[str]]:
    """
    Match target personas against event audience_personas field.
    When audience_personas is empty (all DB events), score is 0.
    SerpAPI will fill this field before display — but scoring runs before enrichment.
    We give a partial score if the event description or industry implies a persona.
    """
    if not profile.target_personas:
        return 0.0, []

    persona_text = (event.audience_personas or "").lower()
    event_text   = _get_event_text(event)
    matched: list[str] = []

    for persona in profile.target_personas:
        p_lower = persona.lower()
        # Direct match in persona field
        if persona_text and _word_in_text(p_lower.split()[0], persona_text):
            matched.append(persona)
            continue
        # Partial match in full event text (catches "CTO" in description, etc.)
        key_word = p_lower.split()[0]  # first word: "CIO" from "CIO / CTO"
        if len(key_word) >= 3 and _word_in_text(key_word, event_text):
            matched.append(persona)

    matched = list(dict.fromkeys(matched))
    n = len(matched)
    if   n >= 2: score = 0.25
    elif n == 1: score = 0.15
    else:        score = 0.0
    return round(score, 4), matched


# ── Geography matching ─────────────────────────────────────────────

def _score_geo(event: EventORM, profile: ICPProfile) -> Tuple[float, str]:
    if not profile.target_geographies:
        return 0.22, "Global"

    is_global = any(
        g.lower().strip() in ("global", "worldwide", "international", "any")
        for g in profile.target_geographies
    )
    if is_global:
        return 0.22, "Global"

    geo_text = _get_geo_text(event)
    for geo in profile.target_geographies:
        geo_words = [
            w for w in re.split(r"[\s,/\-]+", geo.lower())
            if len(w) > 2
        ]
        if any(_word_in_text(w, geo_text) for w in geo_words):
            return 0.22, geo

    if event.is_virtual or event.is_hybrid:
        return 0.12, "Virtual/Hybrid"

    return 0.0, ""


# ── Event type matching ────────────────────────────────────────────

def _score_type(event: EventORM, profile: ICPProfile) -> float:
    type_text = f"{event.category or ''} {event.name or ''}".lower()
    for t in (profile.preferred_event_types or []):
        t_words = [w for w in re.split(r"[\s/,\-]+", t.lower()) if len(w) > 2]
        if any(_word_in_text(w, type_text) for w in t_words):
            return 0.10
    # Generic fallback: most EventsEye events are trade shows / conferences
    generic_event_words = ["trade", "expo", "fair", "conference", "exhibition",
                           "summit", "congress", "symposium", "forum", "show"]
    if any(w in type_text for w in generic_event_words):
        # If profile wants any of these formats, give partial credit
        if any(f in ["trade show", "expo", "conference", "summit", "exhibition"]
               for f in (profile.preferred_event_types or [])):
            return 0.07
    return 0.0


# ── Attendee tier ──────────────────────────────────────────────────

def _score_attendees(event: EventORM, profile: ICPProfile) -> Tuple[float, str]:
    """
    Score based on estimated attendees.
    IMPORTANT: all DB events have est_attendees=0 (unknown, not zero).
    We return 0 score but empty tier — this is neutral, not a penalty.
    SerpAPI will enrich this field later and it's used for display only.
    """
    att = event.est_attendees or 0
    min_att = max(profile.min_attendees or 0, 0)  # never filter by attendees when unknown

    if att == 0:
        # Unknown — neutral, no penalty, no bonus
        return 0.0, ""
    if att >= 10_000: score = 0.08; tier = f"{att:,}+ (flagship)"
    elif att >= 5_000: score = 0.07; tier = f"{att:,}+ (large)"
    elif att >= 1_000: score = 0.05; tier = f"{att:,} (mid-size)"
    elif att >= max(min_att, 200): score = 0.03; tier = f"{att:,}"
    elif att > 0: score = 0.01; tier = f"{att} (boutique)"
    else:
        score = 0.0; tier = ""

    return round(score, 4), tier


# ── Main rule scorer ───────────────────────────────────────────────

def _rule_score(event: EventORM, profile: ICPProfile) -> Tuple[float, dict]:
    ind_score, ind_matched  = _score_industry(event, profile)
    per_score, per_matched  = _score_persona(event, profile)
    geo_score, geo_matched  = _score_geo(event, profile)
    type_score              = _score_type(event, profile)
    att_score, att_tier     = _score_attendees(event, profile)

    total = round(
        ind_score + per_score + geo_score + type_score + att_score,
        4
    )

    detail = {
        "industry_matched":  ind_matched[:4],
        "industry_score":    ind_score,
        "industry_missed":   ind_score == 0.0,
        "persona_matched":   per_matched[:4],
        "persona_score":     per_score,
        "persona_missed":    per_score == 0.0,
        "geo_matched":       geo_matched,
        "geo_score":         geo_score,
        "geo_missed":        geo_score == 0.0,
        "type_matched":      type_score > 0,
        "type_score":        type_score,
        "attendee_tier":     att_tier,
    }
    return total, detail


def _tier(score: float, semantic_active: bool) -> str:
    if semantic_active:
        go_t  = settings.go_threshold
        con_t = settings.consider_threshold
    else:
        go_t  = RULE_GO_THRESHOLD
        con_t = RULE_CONSIDER_THRESHOLD
    if score >= go_t:  return TIER_GO
    if score >= con_t: return TIER_CONSIDER
    return TIER_SKIP


# ── Fallback rationale builder ─────────────────────────────────────

def _join(items: list) -> str:
    items = [str(i) for i in items if i]
    if not items:       return "your target areas"
    if len(items) == 1: return items[0]
    if len(items) == 2: return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])} and {items[-1]}"


def _clean_tags(s: str) -> str:
    return ", ".join(t.strip() for t in s.split(",") if t.strip())[:120]


def build_fallback_rationale(
    event: EventORM, profile: ICPProfile,
    detail: dict, score: float, tier: str,
) -> str:
    ind_matched = detail.get("industry_matched", [])
    per_matched = detail.get("persona_matched", [])
    geo_matched = detail.get("geo_matched", "")
    att_tier    = detail.get("attendee_tier", "")
    score_pct   = int(score * 100)

    # Location string — use what's available
    ec      = (getattr(event, "event_cities", "") or "").strip()
    city    = ec if ec else f"{event.city or ''}, {event.country or ''}".strip(", ")
    # Strip "UK - United Kingdom" → "United Kingdom"
    if " - " in city:
        city = city.split(" - ")[-1].strip()

    # Industry info from DB
    event_ind = _clean_tags(_get_industry(event))

    # --- Industry sentence ---
    if ind_matched:
        ind_s = (
            f"This event covers {_join(ind_matched[:3])}, "
            f"which aligns with your target market."
        )
    elif event_ind:
        ind_s = (
            f"This event is focused on {event_ind}, "
            f"which doesn't directly match your target industries "
            f"({_join((profile.target_industries or [])[:3])})."
        )
    else:
        ind_s = (
            f"Attendee profile is unclear for your target buyers "
            f"({_join((profile.target_personas or [])[:3])})."
        )

    # --- Persona sentence ---
    target_p = _join((profile.target_personas or [])[:3])
    if per_matched:
        per_s = f"The event attracts {_join(per_matched[:3])} — your target decision-makers."
    else:
        per_s = f"Attendee profile is unclear for your target buyers ({target_p})."

    # --- Geo sentence ---
    if geo_matched == "Global":
        geo_s = f"Held in {city}. Your global scope means geography is not a barrier."
    elif geo_matched:
        geo_s = f"Located in {city} — within your target geography."
    elif event.is_virtual or event.is_hybrid:
        geo_s = "Virtual/hybrid format — your team can attend remotely."
    else:
        target_g = _join((profile.target_geographies or [])[:2])
        geo_s = f"Held in {city}, which is outside your primary target regions ({target_g})."

    scale_note = f" Scale: {att_tier}." if att_tier else ""

    if tier == TIER_GO:
        parts = [ind_s, per_s, f"Strong pipeline fit — worth attending ({score_pct}% match).{scale_note}"]
    elif tier == TIER_CONSIDER:
        parts = [ind_s, per_s]
        if not geo_matched or geo_matched == "":
            parts.append(geo_s)
        parts.append(f"Partial fit ({score_pct}%) — evaluate before committing budget.{scale_note}")
    else:
        parts = []
        if not ind_matched:  parts.append(ind_s)
        if not per_matched:  parts.append(per_s)
        if not geo_matched:  parts.append(geo_s)
        if not parts:        parts.append(ind_s)
        parts.append(f"Weak fit ({score_pct}%) — audience and industry don't align well.")

    return " ".join(parts)


# ── Public API ─────────────────────────────────────────────────────

def score_candidates(
    events:        List[EventORM],
    profile:       ICPProfile,
    cosine_scores: Dict[str, float],
) -> List[Tuple[EventORM, float, str, dict]]:
    """
    Score and tier all events.  Returns list sorted by score descending.
    cosine_scores is empty when FAISS is disabled (default on free tier).
    """
    semantic_active = bool(cosine_scores)
    results: list = []

    for event in events:
        cosine = cosine_scores.get(event.id, 0.0)
        rule, detail = _rule_score(event, profile)

        hybrid = (
            (settings.cosine_weight * cosine) + (settings.rule_weight * rule)
            if semantic_active else rule
        )
        hybrid = round(hybrid, 4)
        tier   = _tier(hybrid, semantic_active)
        results.append((event, hybrid, tier, detail))

    results.sort(key=lambda x: -x[1])

    counts: dict[str, int] = {TIER_GO: 0, TIER_CONSIDER: 0, TIER_SKIP: 0}
    for _, _, t, _ in results:
        counts[t] += 1

    logger.info(
        f"Scored {len(results)} events — "
        f"GO={counts[TIER_GO]} "
        f"CONSIDER={counts[TIER_CONSIDER]} "
        f"SKIP={counts[TIER_SKIP]}"
    )
    return results
