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
from relevance.geo_aliases import expand_geo

settings = get_settings()

TIER_GO       = "GO"
TIER_CONSIDER = "CONSIDER"
TIER_SKIP     = "SKIP"

# Rule-only thresholds (no FAISS / cosine)
RULE_GO_THRESHOLD       = 0.38
RULE_CONSIDER_THRESHOLD = 0.18

# Max points per scoring factor — single source of truth. Other modules
# (fit_scorer.py) that need to normalize against the rule scorer's scale
# must import these rather than hardcoding a duplicate constant that can
# silently drift out of sync when weights change here.
MAX_INDUSTRY_SCORE  = 0.35
MAX_PERSONA_SCORE   = 0.25
MAX_GEO_SCORE       = 0.22
MAX_TYPE_SCORE      = 0.10
MAX_ATTENDEE_SCORE  = 0.08
MAX_RULE_SCORE      = MAX_INDUSTRY_SCORE + MAX_PERSONA_SCORE


# ══════════════════════════════════════════════════════════════════════
# TAXONOMY BRIDGE
# Maps normalised profile industry tokens → EventsEye industry segments
# that semantically overlap.  Keys are lowercase, comma-separated tokens
# that the user might choose.  Values are sets of lowercase substrings
# to look for inside an event's industry_tags string.
# ══════════════════════════════════════════════════════════════════════
_PROFILE_TO_EVENTSEYE: dict[str, list[str]] = {
    # ── Manufacturing / Industrial ────────────────────────────────
    "manufacturing":            ["manufactur", "metal work", "mechanical", "industrial", "machiner",
                                 "machine tool", "welding", "casting", "forging", "cnc", "automation",
                                 "robotics", "production", "factory", "stamping", "sheet metal",
                                 "engineering", "material", "alloy", "steel", "aluminium", "foundry",
                                 "press", "die cast", "precision engineering", "process equipment"],
    "industrial":               ["industrial", "manufactur", "metal", "mechanical", "machiner",
                                 "engineering", "factory", "heavy industry", "process industry",
                                 "industrial automation", "plant"],
    "engineering":              ["engineering", "manufactur", "metal", "mechanical", "machiner",
                                 "structural", "civil", "aerospace", "process engineering",
                                 "chemical engineering", "electrical engineering"],
    "industry 4.0":             ["industry 4.0", "industrial iot", "smart manufactur", "digital factory",
                                 "automation", "robotics", "digital twin", "connected factory"],
    # ── Technology / IT ──────────────────────────────────────────
    "technology":               ["technolog", "it ", "information technology", "software",
                                 "digital", "compute", "network", "telecom", "electronic",
                                 "semiconductor", "iot", "smart", "multimedia", "cad", "cam",
                                 "digital transformation", "enterprise tech", "tech"],
    "information technology":   ["information technology", "it ", "software", "digital",
                                 "compute", "network", "it service", "it solution"],
    "it":                       ["it ", "information technology", "software", "compute", "network",
                                 "digital", "it service", "it infrastructure"],
    "software":                 ["software", "digital", "compute", "it ", "saas", "cloud",
                                 "application", "enterprise software", "platform", "b2b software"],
    "tech":                     ["technolog", "software", "digital", "compute", "iot", "smart",
                                 "digital transformation", "enterprise tech"],
    "digital transformation":   ["digital transformation", "digitisation", "digitalisation",
                                 "technolog", "automation", "cloud", "platform"],
    # ── AI / Data / Analytics ────────────────────────────────────
    "ai":                       ["artificial intelligence", "ai", "machine learning", "deep learning",
                                 "data science", "analytics", "automation", "robotics", "nlp",
                                 "computer vision", "generative ai", "llm", "predictive"],
    "ai / machine learning":    ["artificial intelligence", "ai", "machine learning", "analytics",
                                 "data science", "deep learning", "generative ai", "llm"],
    "machine learning":         ["machine learning", "deep learning", "artificial intelligence",
                                 "data science", "analytics", "neural network", "predictive"],
    "data science":             ["data science", "machine learning", "analytics", "big data",
                                 "data engineering", "data platform", "business intelligence"],
    "data & analytics":         ["data", "analytics", "business intelligence", "big data",
                                 "data science", "data management", "reporting", "visualization"],
    "cloud computing":          ["cloud", "saas", "paas", "iaas", "data center", "hosting",
                                 "virtualisation", "cloud platform", "cloud infrastructure",
                                 "digital transformation", "hybrid cloud"],
    "cloud":                    ["cloud", "saas", "data center", "hosting", "cloud platform",
                                 "cloud service", "managed service"],
    "saas":                     ["saas", "software as a service", "cloud", "b2b software",
                                 "platform", "subscription software"],
    "iot":                      ["iot", "internet of things", "connected", "smart device",
                                 "sensor", "industrial iot", "m2m"],
    # ── Cybersecurity ────────────────────────────────────────────
    "cybersecurity":            ["cyber", "security", "infosec", "information security",
                                 "network security", "data protection", "zero trust",
                                 "endpoint security", "siem", "soc", "vulnerability",
                                 "compliance", "identity management", "privileged access"],
    "information security":     ["information security", "infosec", "cybersecurity", "cyber",
                                 "data protection", "privacy", "gdpr", "compliance"],
    "security":                 ["security", "cyber", "information security", "network security",
                                 "data protection", "infosec", "physical security"],
    # ── Finance ──────────────────────────────────────────────────
    "fintech":                  ["fintech", "financial technology", "digital banking", "payment",
                                 "insurtech", "regtech", "blockchain", "cryptocurrency",
                                 "open banking", "neobank", "lending tech", "digital finance",
                                 "embedded finance", "wealthtech"],
    "finance":                  ["finance", "banking", "financial", "investment", "capital market",
                                 "insurance", "treasury", "fintech", "accounting", "wealth",
                                 "asset management", "private equity", "fund", "trading"],
    "financial":                ["finance", "financial", "banking", "investment", "capital market",
                                 "insurance", "treasury", "fintech", "accounting"],
    "financial services":       ["financial service", "finance", "banking", "investment",
                                 "insurance", "wealth management", "capital market"],
    "banking":                  ["banking", "finance", "financial", "payment", "fintech",
                                 "digital banking", "retail banking", "commercial banking"],
    "insurance":                ["insurance", "insurtech", "risk management", "reinsurance",
                                 "underwriting", "actuarial", "claims management"],
    "investment":               ["investment", "capital market", "private equity", "venture capital",
                                 "asset management", "wealth management", "fund management"],
    "payments":                 ["payment", "fintech", "digital payment", "transaction",
                                 "remittance", "card payment", "wallet", "money transfer"],
    "accounting":               ["accounting", "finance", "audit", "taxation",
                                 "financial reporting", "bookkeeping", "cpa"],
    "wealth management":        ["wealth management", "private banking", "asset management",
                                 "investment advisory", "financial planning"],
    "capital markets":          ["capital market", "investment banking", "trading", "equities",
                                 "fixed income", "derivatives", "securities"],
    # ── Healthcare / Life Sciences ────────────────────────────────
    "healthcare":               ["healthcare", "health", "medical", "medtech", "pharma",
                                 "biotech", "hospital", "clinical", "dental", "optical",
                                 "nursing", "life science", "diagnostic", "telemedicine",
                                 "digital health", "health it", "ehealth", "mhealth"],
    "health":                   ["health", "healthcare", "medical", "hospital", "clinical",
                                 "wellness", "public health", "preventive"],
    "medtech":                  ["medtech", "medical device", "medical equipment", "diagnostic",
                                 "imaging", "surgical", "medical technology", "in vitro"],
    "medical devices":          ["medical device", "medtech", "diagnostic", "surgical",
                                 "medical equipment", "imaging", "implant"],
    "pharma":                   ["pharma", "pharmaceutical", "drug", "biotech", "life science",
                                 "clinical", "laboratory", "clinical trial", "regulatory affairs"],
    "pharmaceutical":           ["pharmaceutical", "pharma", "drug", "biotech", "life science",
                                 "clinical trial", "drug discovery", "medicine"],
    "biotech":                  ["biotech", "life science", "pharmaceutical", "genomics",
                                 "bioinformatics", "drug discovery", "biology"],
    "life sciences":            ["life science", "biotech", "pharma", "healthcare",
                                 "clinical", "genomics", "laboratory"],
    "digital health":           ["digital health", "health it", "ehealth", "mhealth",
                                 "telemedicine", "telehealth", "health tech", "medtech"],
    # ── Logistics / Supply Chain ──────────────────────────────────
    "logistics":                ["logistic", "supply chain", "transport", "freight", "shipping",
                                 "warehousing", "cargo", "courier", "last mile", "fleet",
                                 "handling", "intralogistic", "distribution", "port", "3pl",
                                 "cold chain", "express delivery", "parcel"],
    "supply chain":             ["supply chain", "logistic", "procurement", "sourcing",
                                 "warehousing", "inventory", "distribution", "vendor management",
                                 "demand planning"],
    "transportation":           ["transport", "logistic", "freight", "shipping",
                                 "truck", "rail", "aviation", "maritime", "fleet management"],
    "procurement":              ["procurement", "supply chain", "sourcing", "purchasing",
                                 "vendor management", "category management", "strategic sourcing"],
    "freight":                  ["freight", "logistics", "shipping", "cargo", "transport",
                                 "forwarding", "air freight", "sea freight"],
    # ── Retail / E-commerce / Consumer ───────────────────────────
    "retail":                   ["retail", "ecommerce", "consumer", "fmcg", "fashion",
                                 "merchandise", "shopping", "omnichannel", "pos",
                                 "direct-to-consumer", "d2c", "brand", "cpg"],
    "ecommerce":                ["ecommerce", "e-commerce", "online retail", "digital commerce",
                                 "marketplace", "d2c", "online shopping"],
    "consumer goods":           ["consumer", "fmcg", "household", "appliance", "personal care",
                                 "food", "beverage", "retail", "cpg"],
    "fmcg":                     ["fmcg", "consumer goods", "cpg", "household", "personal care",
                                 "food", "beverage"],
    # ── Food & Beverage / Hospitality ─────────────────────────────
    "food & beverage":          ["food processing", "food", "beverage", "catering", "hospitality",
                                 "restaurant", "hotel", "bakery", "dairy", "meat", "seafood",
                                 "organic", "wine", "spirits", "food safety", "food tech"],
    "food":                     ["food processing", "food", "beverage", "catering", "bakery",
                                 "dairy", "seafood", "agri", "food retail", "food service"],
    "hospitality":              ["hospitality", "catering", "hotel", "restaurant", "food service",
                                 "tourism", "travel", "mice"],
    "food tech":                ["food tech", "food processing", "food safety", "agritech",
                                 "food science", "nutrition", "food innovation"],
    # ── Energy / Environment ──────────────────────────────────────
    "energy":                   ["energy", "oil", "gas", "petroleum", "renewable", "solar",
                                 "wind", "nuclear", "power", "electricity", "utility",
                                 "energy storage", "battery", "grid", "smart grid"],
    "cleantech":                ["cleantech", "renewable", "solar", "wind", "green energy",
                                 "sustainable", "environmental", "waste", "water treatment",
                                 "clean energy", "green tech"],
    "sustainability":           ["sustainab", "environmental", "cleantech", "green", "renewable",
                                 "circular economy", "esg", "carbon", "net zero", "climate",
                                 "decarbonisation", "green building"],
    "sustainability / esg":     ["sustainab", "esg", "environmental", "governance", "carbon",
                                 "climate", "net zero", "corporate responsibility"],
    "renewable energy":         ["renewable", "solar", "wind", "green energy", "clean energy",
                                 "hydro", "geothermal", "energy storage", "cleantech"],
    "oil and gas":              ["oil", "gas", "petroleum", "upstream", "downstream", "midstream",
                                 "refinery", "drilling", "exploration"],
    # ── Real Estate / Construction ────────────────────────────────
    "construction":             ["construction", "build", "architect", "real estate", "civil",
                                 "infrastructure", "contractor", "property", "build material",
                                 "housing", "fit out"],
    "real estate":              ["real estate", "property", "construction", "land", "housing",
                                 "commercial real estate", "proptech", "facility management"],
    "real estate / proptech":   ["real estate", "proptech", "property", "construction",
                                 "smart building", "facility management"],
    "proptech":                 ["proptech", "real estate", "property technology", "smart building",
                                 "building management", "facility management"],
    # ── Mining / Resources ────────────────────────────────────────
    "mining":                   ["mining", "mineral", "quarry", "ore", "coal", "metals",
                                 "extraction", "petroleum", "resources", "geology"],
    "mining / resources":       ["mining", "mineral", "quarry", "ore", "metals",
                                 "extraction", "resources"],
    # ── Media / Marketing ────────────────────────────────────────
    "marketing":                ["marketing", "advertising", "media", "digital marketing",
                                 "martech", "brand", "pr", "communication", "promotion",
                                 "content marketing", "demand generation", "lead generation"],
    "marketing / adtech":       ["marketing", "adtech", "advertising", "digital marketing",
                                 "martech", "programmatic", "media buying"],
    "media":                    ["media", "publishing", "broadcast", "print", "graphic",
                                 "content", "advertising", "news", "streaming"],
    "advertising":              ["advertising", "marketing", "adtech", "digital advertising",
                                 "media buying", "programmatic", "brand"],
    "martech":                  ["martech", "marketing technology", "crm", "marketing automation",
                                 "analytics", "digital marketing"],
    # ── HR / People ──────────────────────────────────────────────
    "hr tech":                  ["human resource", "hr", "talent", "recruitment", "workforce",
                                 "payroll", "people management", "future of work", "hris",
                                 "employee experience", "talent acquisition", "hr tech"],
    "hr":                       ["human resource", "hr ", "talent", "recruitment", "workforce",
                                 "people management", "employee", "hris"],
    "human resources":          ["human resource", "hr", "talent management", "recruitment",
                                 "workforce", "people ops", "payroll"],
    "talent management":        ["talent", "recruitment", "hr", "workforce", "learning",
                                 "people development"],
    # ── Education ────────────────────────────────────────────────
    "education":                ["education", "training", "learning", "university", "academic",
                                 "e-learning", "professional development", "edtech", "school",
                                 "upskilling", "reskilling"],
    "education / edtech":       ["education", "edtech", "e-learning", "lms", "online learning",
                                 "academic", "training"],
    "edtech":                   ["edtech", "education technology", "e-learning", "lms",
                                 "online learning", "education"],
    # ── Agriculture ──────────────────────────────────────────────
    "agriculture":              ["agriculture", "agri", "farming", "crop", "livestock",
                                 "aquaculture", "fishery", "agritech", "smart farming",
                                 "precision agriculture"],
    "agriculture / agritech":   ["agriculture", "agritech", "agri", "farming", "crop",
                                 "precision agriculture", "smart farming"],
    # ── Travel / Tourism ─────────────────────────────────────────
    "travel":                   ["travel", "tourism", "hospitality", "airline", "hotel",
                                 "destination", "mice", "business travel"],
    "travel / hospitality":     ["travel", "tourism", "hospitality", "airline", "hotel",
                                 "destination", "mice"],
    # ── Automotive ───────────────────────────────────────────────
    "automotive":               ["automotive", "vehicle", "car", "truck", "electric vehicle",
                                 "ev", "mobility", "fleet", "auto", "connected vehicle",
                                 "autonomous vehicle", "telematics"],
    "electric vehicle":         ["electric vehicle", "ev", "battery", "charging",
                                 "automotive", "clean transport", "mobility"],
    # ── Fashion / Textile ────────────────────────────────────────
    "fashion":                  ["fashion", "textile", "clothing", "apparel", "fabric",
                                 "garment", "leather", "footwear", "luxury"],
    "fashion / apparel":        ["fashion", "apparel", "textile", "clothing", "garment",
                                 "footwear", "luxury"],
    "textile":                  ["textile", "fabric", "garment", "apparel", "fashion",
                                 "yarn", "weaving"],
    # ── Printing / Packaging ─────────────────────────────────────
    "printing":                 ["printing", "packaging", "graphic", "inkjet", "label",
                                 "flexo", "offset", "digital print"],
    "packaging":                ["packaging", "printing", "label", "flexible packaging",
                                 "rigid packaging"],
    # ── Telecom ──────────────────────────────────────────────────
    "telecom":                  ["telecom", "5g", "network", "connectivity", "wireless",
                                 "fibre", "broadband", "isp", "mobile", "carrier"],
    "telecommunications":       ["telecom", "telecommunications", "5g", "network", "wireless",
                                 "mobile", "connectivity"],
    # ── Legal / Compliance ───────────────────────────────────────
    "legal tech":               ["legal tech", "legal", "law", "compliance", "regulatory",
                                 "governance", "contract management", "legaltech"],
    "legal":                    ["legal", "law", "compliance", "regulatory", "governance",
                                 "contract", "litigation"],
    "compliance":               ["compliance", "regulatory", "governance", "audit",
                                 "risk management", "legal", "gdpr"],
    # ── Government / Public Sector ───────────────────────────────
    "government":               ["government", "public sector", "smart city", "civic tech",
                                 "e-government", "policy", "public administration"],
    "government / public sector": ["government", "public sector", "municipal", "smart city",
                                   "public service", "e-government"],
    "smart city":               ["smart city", "urban", "government", "public sector",
                                 "infrastructure", "mobility", "civic tech"],
    # ── Defence / Aerospace ──────────────────────────────────────
    "defence":                  ["defence", "defense", "aerospace", "military", "security",
                                 "space", "aviation", "unmanned", "drone", "naval"],
    "defence / aerospace":      ["defence", "defense", "aerospace", "military", "space",
                                 "aviation", "drone"],
    "aerospace":                ["aerospace", "aviation", "space", "defence", "aircraft",
                                 "satellite", "uav", "drone"],
    # ── Sports Technology ─────────────────────────────────────────
    "sports technology":        ["sports technology", "sport", "esports", "fitness",
                                 "wearable", "sports analytics", "stadium tech"],
    # ── Business / Professional Services ─────────────────────────
    "business services":        ["business service", "professional service", "consulting",
                                 "outsourcing", "bpo", "shared service"],
    "startup / vc":             ["startup", "venture capital", "vc", "entrepreneur",
                                 "innovation", "scale-up", "seed funding"],
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


def _syn_in_text(syn: str, text: str) -> bool:
    """
    Boundary-aware synonym match.
    Short synonyms (≤4 chars) must match whole words only, so "auto"
    never fires inside "automation" and "ev" never fires inside "event".
    Longer synonyms are stems anchored at a word start ("manufactur"
    matches "manufacturing", "technolog" matches "technology").
    """
    syn = syn.strip().lower()
    if not syn:
        return False
    if len(syn) <= 4:
        return bool(re.search(r"\b" + re.escape(syn) + r"\b", text, re.I))
    return bool(re.search(r"\b" + re.escape(syn), text, re.I))


# ── Industry matching (profile → event) ───────────────────────────

def _score_industry(event: EventORM, profile: ICPProfile) -> Tuple[float, list[str]]:
    """
    Score industry match using three-pass approach:
    Pass 1: Direct token match between profile industry names and event text
    Pass 2: Taxonomy bridge — map profile industry to EventsEye synonyms
    Pass 3: Company description / buyer description stem match
    Returns (score 0..0.35, list of matched profile industry values).
    """
    if not profile.target_industries:
        return 0.0, []

    industry_str = _get_industry(event).lower()
    event_text   = _get_event_text(event)
    matched: list[str] = []

    # Build a combined ICP text for pass-3 context matching
    icp_context = (getattr(profile, "buyer_description", "") or "").lower()

    for prof_ind in profile.target_industries:
        pi_lower = prof_ind.lower().strip()
        already  = False

        # Pass 1: direct word / stem match in event text
        # Use all meaningful sub-tokens including partial stems
        pi_words = [w for w in re.split(r"[\s/,\-&]+", pi_lower) if len(w) > 2]
        if any(_word_in_text(w, event_text) for w in pi_words):
            matched.append(prof_ind)
            already = True

        if already:
            continue

        # Pass 1b: prefix/stem match (e.g. "financial" matches "finance").
        # Stem must start at a word boundary so "automo" never fires
        # mid-word and short stems don't match unrelated substrings.
        for w in pi_words:
            stem = w[:min(len(w), 6)]  # 6-char prefix stem
            if len(stem) >= 5 and re.search(r"\b" + re.escape(stem), event_text):
                matched.append(prof_ind)
                already = True
                break

        if already:
            continue

        # Pass 2: taxonomy bridge — profile industry key → EventsEye synonyms
        # Key activation is token-based, never substring: "tech" must not
        # activate for "medtech", or a healthcare ICP inherits every
        # technology synonym and matches unrelated industrial events.
        pi_tokens = [t for t in re.split(r"[^a-z0-9.]+", pi_lower) if len(t) > 2]
        for key, synonyms in _PROFILE_TO_EVENTSEYE.items():
            key_words = [kw for kw in key.split() if len(kw) > 2]
            if not key_words:
                continue
            key_match_score = sum(
                1 for kw in key_words
                if any(t == kw or t.startswith(kw) for t in pi_tokens)
            )
            if key_match_score == 0:
                continue
            # Does the event text contain any synonym from this key's list?
            for syn in synonyms:
                if _syn_in_text(syn, industry_str) or _syn_in_text(syn, event_text):
                    matched.append(prof_ind)
                    already = True
                    break
            if already:
                break

        if already:
            continue

        # Pass 3: ICP buyer description → event description context match
        # If what the company sells relates to the event topic
        if icp_context:
            for w in pi_words:
                if len(w) >= 4 and _syn_in_text(w, event_text):
                    matched.append(prof_ind)
                    break

    # LLM-parsed niche keywords ("ambulatory surgery", "cold chain") count
    # as secondary evidence — covers long-tail ICPs outside the taxonomy.
    for kw in (getattr(profile, "extra_keywords", None) or []):
        if kw and _syn_in_text(kw, event_text):
            matched.append(kw)

    matched = list(dict.fromkeys(matched))  # preserve order, deduplicate

    # The FIRST target industry is the user's primary intent (the parser
    # emits it first). An event matching only secondary industries must
    # never outrank one matching the primary — this is what previously
    # let a manufacturing show beat a healthcare show for a healthcare ICP.
    n = len(matched)
    primary     = (profile.target_industries[0] or "").strip() if profile.target_industries else ""
    primary_hit = primary in matched

    if n == 0:
        score = 0.0
    elif primary_hit:
        if   n >= 3: score = 0.35
        elif n == 2: score = 0.32
        else:        score = 0.26
    else:
        if   n >= 3: score = 0.24
        elif n == 2: score = 0.20
        else:        score = 0.14

    return round(score, 4), matched


# Expanded persona synonym map for matching event text
_PERSONA_ALIASES: dict[str, list[str]] = {
    "cio":               ["cio", "chief information officer", "it director", "head of it",
                          "vp it", "director of it", "head of technology"],
    "cto":               ["cto", "chief technology officer", "vp engineering", "head of engineering",
                          "director of engineering", "vp technology", "head of tech"],
    "cfo":               ["cfo", "chief financial officer", "finance director", "vp finance",
                          "head of finance", "director of finance", "treasurer"],
    "coo":               ["coo", "chief operating officer", "head of operations", "vp operations",
                          "director of operations", "operations director"],
    "ceo":               ["ceo", "chief executive", "managing director", "president",
                          "executive director", "founder", "co-founder"],
    "ciso":              ["ciso", "chief information security", "vp security",
                          "head of security", "head of cybersecurity", "security director"],
    "cmo":               ["cmo", "chief marketing officer", "vp marketing", "head of marketing",
                          "marketing director", "director of marketing"],
    "cdo":               ["cdo", "chief digital officer", "chief data officer",
                          "vp data", "head of data", "digital director"],
    "chro":              ["chro", "chief human resources", "chief people officer",
                          "hr director", "vp hr", "head of hr"],
    "vp engineering":    ["vp engineering", "cto", "head of engineering",
                          "director of engineering", "engineering manager"],
    "vp supply chain":   ["vp supply chain", "supply chain director", "head of supply chain",
                          "vp logistics", "logistics director", "head of logistics",
                          "procurement director"],
    "head of procurement": ["head of procurement", "procurement director", "vp procurement",
                            "chief procurement", "sourcing director", "category director"],
    "operations manager": ["operations manager", "plant manager", "factory manager",
                           "production manager", "site manager", "facility manager"],
    "founder":           ["founder", "co-founder", "owner", "managing director",
                          "entrepreneur"],
    "vp sales":          ["vp sales", "chief revenue officer", "cro", "sales director",
                          "head of sales", "director of sales"],
    "vp product":        ["vp product", "chief product officer", "cpo", "product director",
                          "head of product"],
    "it manager":        ["it manager", "it director", "technology manager",
                          "systems manager", "infrastructure manager"],
    "finance manager":   ["finance manager", "financial controller", "finance director",
                          "treasury manager", "accounting manager"],
}


def _score_persona(event: EventORM, profile: ICPProfile) -> Tuple[float, list[str]]:
    """
    Match target personas against event audience_personas and event text.
    Uses expanded alias map so "CFO" also matches "finance director", etc.
    """
    if not profile.target_personas:
        return 0.0, []

    persona_text = (event.audience_personas or "").lower()
    event_text   = _get_event_text(event)
    matched: list[str] = []

    for persona in profile.target_personas:
        p_lower  = persona.lower().strip()
        already  = False

        # 1. Direct word match in audience_personas field
        first_word = p_lower.split()[0]
        if persona_text and len(first_word) >= 2 and first_word in persona_text:
            matched.append(persona)
            continue

        # 2. Check all aliases for this persona
        aliases = _PERSONA_ALIASES.get(p_lower, [])
        if not aliases:
            # Generic: build aliases from persona token words
            aliases = [w for w in re.split(r"[\s/,\-&]+", p_lower) if len(w) >= 2]

        for alias in aliases:
            if alias in persona_text or alias in event_text:
                matched.append(persona)
                already = True
                break

        if already:
            continue

        # 3. Partial token match in full event text
        tokens = [w for w in re.split(r"[\s/,\-&]+", p_lower) if len(w) >= 3]
        if any(_word_in_text(t, event_text) for t in tokens):
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
        for variant in expand_geo(geo):
            if variant in geo_text:
                return 0.22, geo
            geo_words = [w for w in re.split(r"[\s,/\-]+", variant) if len(w) > 2]
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


# Designation (persona) is the PRIMARY filter — a user who names "CTO"
# wants CTO-relevant shows first, full stop. Pure additive scoring let an
# event with zero persona relevance still surface as GO purely on
# industry+geo (e.g. a "CMO in Tech" event scoring industry 0.35 + geo
# 0.22 = 0.57, clearing GO at 0.38, despite matching NOTHING about the
# user's actual buyer persona). This multiplicative penalty on a total
# persona mismatch (only applied when the profile actually specified a
# persona) crushes such events down near/below SKIP regardless of how
# strong their industry or geo match is, so a wrong-designation event
# never outranks a right-designation one.
PERSONA_MISMATCH_PENALTY = 0.15

# "No persona data at all" is NOT the same as "persona data exists and
# it's the wrong one" — many events (especially not yet backfilled from
# a curated CSV, see the "Designations attending" column) simply have an
# empty audience_personas field, not a confirmed-wrong one. Genuinely
# wrong persona data still gets the harsh penalty above. (This used to be
# a flat PERSONA_UNKNOWN_PENALTY multiplier on the "no data" case; that's
# now handled by redistributing persona's weight into industry/geo below
# instead of penalizing every event in a low-persona-coverage catalog by
# the same fixed amount.)

# Geography is SECONDARY, a backfill preference once designation is
# satisfied — not a hard requirement. A persona-matching event from a
# different country should still be able to surface (to fill out a full
# 6-result list when the target country is thin), just ranked below an
# equally-relevant in-country match. This is a much lighter penalty than
# the persona one on purpose: 0.35+0.25+0.10 (industry+persona+type) with
# no geo match still totals ~0.7 × 0.65 ≈ 0.46, comfortably GO — geo
# mismatch alone should never be enough to hide an otherwise-strong,
# right-designation match.
GEO_MISMATCH_PENALTY = 0.65

# Industry is the HIGHEST-weighted single factor (0.35) but previously had
# no mismatch penalty at all — an event that matched persona + geo but
# NOTHING about the target industry could still clear GO purely on those
# two (e.g. an HR-industry event scoring persona 0.15 + geo 0.22 + type
# 0.07 = 0.44, well past the 0.38 GO bar, despite the event having no
# connection whatsoever to the buyer's actual industry). This let
# industry-irrelevant events surface as top recommendations whenever they
# happened to name the right job title. Lighter than the persona penalty
# (industry taxonomy coverage is inherently fuzzier — a real miss is more
# likely than with the explicit persona alias map), but non-zero so an
# industry-blank match no longer rides purely on persona+geo into GO.
#
# Same "unknown vs. actively wrong" split already made for personas:
# _get_industry() returning "" (related_industries, industry_tags AND
# category all empty — common for events not yet backfilled from a
# curated CSV) is not evidence the event is a bad fit, just that we
# never learned its industry. A populated industry_tags string that
# still didn't match anything in the taxonomy bridge is stronger
# evidence of a real mismatch and gets the harsher penalty.
INDUSTRY_MISMATCH_PENALTY = 0.50
INDUSTRY_UNKNOWN_PENALTY  = 0.75


# ── Main rule scorer ───────────────────────────────────────────────

def _best_segment_scores(
    event: EventORM, profile: ICPProfile,
) -> Tuple[Tuple[float, list[str]], Tuple[float, list[str]]]:
    """
    When the ICP has explicit persona/industry pairs (profile.icp_segments -
    e.g. "CEO at BFSI" and "CIO at Medtech" as two separate groups), score
    each pair independently and keep whichever pair fits this event best,
    rather than the flat behaviour of matching "any persona" against "any
    industry" (which would wrongly credit an event for CEO + Medtech, a
    combination nobody asked for). No segments -> unchanged flat scoring.
    """
    segments = getattr(profile, "icp_segments", None) or []
    if not segments:
        return _score_industry(event, profile), _score_persona(event, profile)

    best = None
    for seg in segments:
        seg_industries = seg.get("industries") or []
        seg_personas   = seg.get("personas") or []
        if not seg_industries and not seg_personas:
            continue
        seg_profile = profile.model_copy(update={
            "target_industries": seg_industries,
            "target_personas":   seg_personas,
        })
        ind = _score_industry(event, seg_profile)
        per = _score_persona(event, seg_profile)
        combined = ind[0] + per[0]
        if best is None or combined > best[0]:
            best = (combined, ind, per)

    if best is None:
        return _score_industry(event, profile), _score_persona(event, profile)
    return best[1], best[2]


def _rule_score(event: EventORM, profile: ICPProfile) -> Tuple[float, dict]:
    (ind_score, ind_matched), (per_score, per_matched) = _best_segment_scores(event, profile)
    geo_score, geo_matched  = _score_geo(event, profile)
    type_score              = _score_type(event, profile)
    att_score, att_tier     = _score_attendees(event, profile)

    persona_data_present = bool((event.audience_personas or "").strip())

    # When the event has no persona data at all, there's nothing to score
    # on that dimension - redistribute persona's 0.25 weight into industry
    # and geography (the two consistently-populated real signals in the
    # current catalog) instead of scoring persona as 0 and applying a flat
    # PERSONA_UNKNOWN_PENALTY multiplier to the whole total. The old
    # approach meant every event in a catalog with 0% persona coverage got
    # the exact same -45% haircut regardless of how well it actually
    # matched - uniform, so not biased, but pure wasted weight and a
    # needlessly deflated score. Redistributed proportionally to each
    # dimension's own weight share (0.35 / 0.22) so the industry-vs-geo
    # balance is preserved, just scaled up to fill the freed 0.25.
    if not persona_data_present:
        REDISTRIBUTE_FACTOR = 1 + (0.25 / (0.35 + 0.22))  # ≈ 1.4386
        ind_score = round(ind_score * REDISTRIBUTE_FACTOR, 4)
        geo_score = round(geo_score * REDISTRIBUTE_FACTOR, 4)
        per_score = 0.0
        per_matched = []

    total = round(
        ind_score + per_score + geo_score + type_score + att_score,
        4
    )
    # Mismatch penalties: apply only the SINGLE strongest applicable
    # penalty, not all of them multiplicatively. Stacking them (e.g.
    # persona 0.15 * geo 0.65 * industry 0.50) compounds into an
    # undocumented ~5% multiplier for any event missing all three
    # dimensions — far harsher than any one penalty was designed for,
    # and it swamps genuine partial signal in whichever dimension DID
    # match. Taking the min (strongest single) penalty still clearly
    # demotes a multi-dimension mismatch below a single-dimension one,
    # without the compounding blowup.
    applicable_penalties: list[float] = []
    if profile.target_personas and per_score == 0.0 and persona_data_present:
        applicable_penalties.append(PERSONA_MISMATCH_PENALTY)
    if geo_matched not in ("Global", "Virtual/Hybrid") and geo_score == 0.0:
        applicable_penalties.append(GEO_MISMATCH_PENALTY)
    if profile.target_industries and ind_score == 0.0:
        penalty = INDUSTRY_MISMATCH_PENALTY if _get_industry(event).strip() else INDUSTRY_UNKNOWN_PENALTY
        applicable_penalties.append(penalty)
    if applicable_penalties:
        total = round(total * min(applicable_penalties), 4)

    detail = {
        "industry_matched":  ind_matched[:4],
        "industry_score":    ind_score,
        "industry_missed":   ind_score == 0.0,
        "persona_matched":   per_matched[:4],
        "persona_score":     per_score,
        "persona_missed":    per_score == 0.0,
        "persona_data_present": persona_data_present,
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

    # Geography is a HARD filter: when the ICP form names specific
    # geographies (and hasn't opted into "global"/"any"), events that don't
    # match one of those geographies (and aren't virtual/hybrid) must not
    # appear at all — not even demoted. If nothing in that geography
    # matches, the result list is empty rather than backfilling with
    # events from other countries.
    strict_geo = bool(profile.target_geographies) and not any(
        g.lower().strip() in ("global", "worldwide", "international", "any")
        for g in profile.target_geographies
    )

    # Industry is now ALSO a hard filter, mirroring strict_geo above — but
    # only for a CONFIRMED mismatch (the event has real industry data and
    # none of it matches), never for "unknown" (no industry data at all).
    # related_industries/industry_tags are ~100% populated in the current
    # catalog, so a confirmed mismatch here is a strong, trustworthy signal
    # — unlike persona/attendees/category, which are sparse enough that a
    # miss there could just mean "not backfilled yet," not "wrong event."
    strict_industry = bool(profile.target_industries)

    # A pgvector semantic-recall candidate was pulled in specifically
    # because its embedding is topically close to the ICP profile despite
    # not sharing literal industry-tag keywords (see routes_events.py's
    # recall cutoff of cos >= 0.60) — the whole point of semantic recall
    # is to catch fits that keyword/taxonomy matching misses. Applying the
    # keyword-only industry hard filter to those candidates unconditionally
    # threw them straight back out, silently discarding every semantic
    # recall the moment it reached scoring. A strong cosine score is
    # treated as its own confirmation of industry fit here, on par with a
    # literal keyword match.
    SEMANTIC_INDUSTRY_OVERRIDE = 0.60

    for event in events:
        cosine = cosine_scores.get(event.id, 0.0)

        if strict_geo:
            geo_score, geo_matched = _score_geo(event, profile)
            if geo_score == 0.0 and geo_matched not in ("Global", "Virtual/Hybrid"):
                continue

        if strict_industry and cosine < SEMANTIC_INDUSTRY_OVERRIDE:
            ind_score, _ = _score_industry(event, profile)
            # Only trust related_industries/industry_tags as "confirmed
            # data" for this hard filter — NOT the category fallback
            # _get_industry() also checks, since category answers "what
            # kind of event" (conference/trade show/...), not "what
            # industry," and shouldn't be strong enough evidence to
            # hard-exclude an event on its own.
            has_industry_data = bool(
                (getattr(event, "related_industries", None) or "").strip()
                or (event.industry_tags or "").strip()
            )
            if ind_score == 0.0 and has_industry_data:
                continue

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
