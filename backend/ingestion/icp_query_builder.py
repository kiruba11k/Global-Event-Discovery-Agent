"""
ingestion/icp_query_builder.py  —  ICP form inputs → API query sets

Key change: `_extract_desc_keywords` is now replaced by a call to
`groq_tagger.extract_search_keywords()` which understands ANY company description
using Groq LLM — not just the hardcoded keyword list.

build_queries() is the main async entry point.
build_queries_sync() is a sync wrapper for places that can't await.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date

from loguru import logger


# ── Geographic data ──────────────────────────────────────────────────
# countryCode → {ticketmaster code, predicthq code, lat/lon, SerpAPI location strings}
GEO_DATA: dict[str, dict] = {
    "Indonesia":    {"tm": "ID", "phq": "ID", "lat": -6.2088,  "lon": 106.8456, "serp": ["Jakarta Indonesia", "Indonesia"],              "eb_radius": "100km"},
    "Singapore":    {"tm": "SG", "phq": "SG", "lat":  1.3521,  "lon": 103.8198, "serp": ["Singapore"],                                   "eb_radius": "50km"},
    "India":        {"tm": "IN", "phq": "IN", "lat": 12.9716,  "lon":  77.5946, "serp": ["Bangalore India", "Mumbai India", "New Delhi India"], "eb_radius": "100km"},
    "USA":          {"tm": "US", "phq": "US", "lat": 40.7128,  "lon": -74.0060, "serp": ["New York USA", "San Francisco USA", "Las Vegas USA"],  "eb_radius": "50km"},
    "UK":           {"tm": "GB", "phq": "GB", "lat": 51.5074,  "lon":  -0.1278, "serp": ["London UK"],                                   "eb_radius": "50km"},
    "UAE":          {"tm": "AE", "phq": "AE", "lat": 25.2048,  "lon":  55.2708, "serp": ["Dubai UAE", "Abu Dhabi UAE"],                   "eb_radius": "100km"},
    "Germany":      {"tm": "DE", "phq": "DE", "lat": 52.5200,  "lon":  13.4050, "serp": ["Frankfurt Germany", "Berlin Germany", "Munich Germany"], "eb_radius": "100km"},
    "Australia":    {"tm": "AU", "phq": "AU", "lat": -33.8688, "lon": 151.2093, "serp": ["Sydney Australia", "Melbourne Australia"],       "eb_radius": "100km"},
    "Japan":        {"tm": "JP", "phq": "JP", "lat": 35.6762,  "lon": 139.6503, "serp": ["Tokyo Japan"],                                 "eb_radius": "50km"},
    "Malaysia":     {"tm": "MY", "phq": "MY", "lat":  3.1390,  "lon": 101.6869, "serp": ["Kuala Lumpur Malaysia"],                        "eb_radius": "100km"},
    "South Korea":  {"tm": "KR", "phq": "KR", "lat": 37.5665,  "lon": 126.9780, "serp": ["Seoul South Korea"],                           "eb_radius": "50km"},
    "Canada":       {"tm": "CA", "phq": "CA", "lat": 43.6532,  "lon": -79.3832, "serp": ["Toronto Canada", "Vancouver Canada"],           "eb_radius": "100km"},
    "France":       {"tm": "FR", "phq": "FR", "lat": 48.8566,  "lon":   2.3522, "serp": ["Paris France"],                                "eb_radius": "50km"},
    "Netherlands":  {"tm": "NL", "phq": "NL", "lat": 52.3676,  "lon":   4.9041, "serp": ["Amsterdam Netherlands"],                       "eb_radius": "50km"},
    "Brazil":       {"tm": None, "phq": "BR", "lat": -23.5505, "lon": -46.6333, "serp": ["Sao Paulo Brazil"],                             "eb_radius": "100km"},
    "Saudi Arabia": {"tm": "SA", "phq": "SA", "lat": 24.7136,  "lon":  46.6753, "serp": ["Riyadh Saudi Arabia"],                         "eb_radius": "100km"},
    "South Africa": {"tm": None, "phq": "ZA", "lat": -33.9249, "lon":  18.4241, "serp": ["Cape Town South Africa", "Johannesburg South Africa"], "eb_radius": "100km"},
    "Philippines":  {"tm": None, "phq": "PH", "lat": 14.5995,  "lon": 120.9842, "serp": ["Manila Philippines"],                           "eb_radius": "100km"},
    "Thailand":     {"tm": None, "phq": "TH", "lat": 13.7563,  "lon": 100.5018, "serp": ["Bangkok Thailand"],                             "eb_radius": "100km"},
    "Vietnam":      {"tm": None, "phq": "VN", "lat": 10.8231,  "lon": 106.6297, "serp": ["Ho Chi Minh City Vietnam", "Hanoi Vietnam"],    "eb_radius": "100km"},
    "Nigeria":      {"tm": None, "phq": "NG", "lat":  6.5244,  "lon":   3.3792, "serp": ["Lagos Nigeria"],                               "eb_radius": "100km"},
    "Kenya":        {"tm": None, "phq": "KE", "lat": -1.2921,  "lon":  36.8219, "serp": ["Nairobi Kenya"],                               "eb_radius": "100km"},
    "Global":       {"tm": None, "phq": None, "lat":  1.3521,  "lon": 103.8198, "serp": ["Asia", "Europe", "USA", "Middle East", "Singapore"], "eb_radius": "200km"},
}


@dataclass
class SerpAPIQuery:
    q:        str
    location: str
    year:     str


@dataclass
class TicketmasterQuery:
    keyword:      str
    country_code: str
    start_dt:     str
    end_dt:       str


@dataclass
class EventbriteQuery:
    keyword:   str
    lat:       float
    lon:       float
    radius:    str
    date_from: str


@dataclass
class PredictHQQuery:
    q:            str
    country_code: str
    start_gte:    str
    end_lte:      str


@dataclass
class QueryBundle:
    serpapi:      list[SerpAPIQuery]      = field(default_factory=list)
    ticketmaster: list[TicketmasterQuery] = field(default_factory=list)
    eventbrite:   list[EventbriteQuery]   = field(default_factory=list)
    predicthq:    list[PredictHQQuery]    = field(default_factory=list)
    year:         str                     = "2026"
    keywords_used: list[str]             = field(default_factory=list)


# ── Main async builder ───────────────────────────────────────────────

async def build_queries(
    industries:    list[str],
    geographies:   list[str],
    personas:      list[str],
    event_types:   list[str],
    company_desc:  str,
    date_from:     str,
    date_to:       str,
    *,
    max_serpapi:      int = 8,
    max_ticketmaster: int = 12,
    max_eventbrite:   int = 9,
    max_predicthq:    int = 6,
) -> QueryBundle:
    """
    Async version: uses Groq LLM to extract keywords from company description.
    Call this from async contexts (e.g. realtime_pipeline.py).
    """
    today = date.today().isoformat()
    start = date_from or today
    end   = date_to   or "2028-12-31"
    year  = start[:4]

    # ── Step 1: Groq LLM keyword extraction ───────────────────────────
    # Understands ANY company description — not limited to hardcoded keywords.
    try:
        from relevance.groq_tagger import extract_search_keywords
        keywords = await extract_search_keywords(
            company_desc = company_desc,
            industries   = industries,
            personas     = personas,
            event_types  = event_types,
        )
        logger.info(f"Groq keywords ({len(keywords)}): {keywords}")
    except Exception as exc:
        logger.warning(f"Groq keyword extraction failed: {exc} — using fallback")
        keywords = _fallback_keywords(industries)

    if not keywords:
        keywords = _fallback_keywords(industries)

    # ── Step 2: Resolve geo data ───────────────────────────────────────
    is_global = any(
        g.lower().strip() in ("global", "worldwide", "international", "any")
        for g in geographies
    )
    resolved: list[tuple[str, dict]] = []
    for geo in geographies:
        if geo in GEO_DATA:
            resolved.append((geo, GEO_DATA[geo]))

    # Global → use spread of major hubs
    if is_global or not resolved:
        for g in ["Singapore", "UK", "USA"]:
            resolved.append((g, GEO_DATA[g]))

    # ── Step 3: Build SerpAPI queries ──────────────────────────────────
    serp: list[SerpAPIQuery] = []
    for kw in keywords[:4]:
        for _, geo in resolved[:3]:
            for loc in geo["serp"][:1]:
                serp.append(SerpAPIQuery(q=f"{kw} {year}", location=loc, year=year))
                if len(serp) >= max_serpapi:
                    break
            if len(serp) >= max_serpapi:
                break
        if len(serp) >= max_serpapi:
            break

    # ── Step 4: Build Ticketmaster queries ─────────────────────────────
    tm_countries = list({geo["tm"] for _, geo in resolved if geo.get("tm")}) or ["US", "GB", "SG"]
    start_dt = f"{start}T00:00:00Z"
    end_dt   = f"{end}T23:59:59Z"
    tm: list[TicketmasterQuery] = []
    for kw in keywords[:4]:
        for cc in tm_countries[:3]:
            tm.append(TicketmasterQuery(keyword=kw, country_code=cc, start_dt=start_dt, end_dt=end_dt))
            if len(tm) >= max_ticketmaster:
                break
        if len(tm) >= max_ticketmaster:
            break

    # ── Step 5: Build Eventbrite queries ───────────────────────────────
    eb: list[EventbriteQuery] = []
    for kw in keywords[:3]:
        for _, geo in resolved[:3]:
            eb.append(EventbriteQuery(
                keyword=kw,
                lat=geo["lat"], lon=geo["lon"],
                radius=geo.get("eb_radius", "100km"),
                date_from=start,
            ))
            if len(eb) >= max_eventbrite:
                break
        if len(eb) >= max_eventbrite:
            break

    # ── Step 6: Build PredictHQ queries ────────────────────────────────
    phq_countries = list({geo["phq"] for _, geo in resolved if geo.get("phq")}) or ["US", "GB"]
    phq: list[PredictHQQuery] = []
    for kw in keywords[:3]:
        for cc in phq_countries[:2]:
            phq.append(PredictHQQuery(q=kw, country_code=cc, start_gte=start, end_lte=end))
            if len(phq) >= max_predicthq:
                break
        if len(phq) >= max_predicthq:
            break

    bundle = QueryBundle(
        serpapi=serp, ticketmaster=tm, eventbrite=eb, predicthq=phq,
        year=year, keywords_used=keywords,
    )
    logger.info(
        f"QueryBundle: serp={len(serp)} tm={len(tm)} eb={len(eb)} phq={len(phq)} "
        f"keywords={keywords[:3]}"
    )
    return bundle


def _fallback_keywords(industries: list[str]) -> list[str]:
    """Deterministic fallback when Groq is unavailable."""
    _MAP = {
        "Technology":            "technology conference",
        "AI / Machine Learning": "AI artificial intelligence conference",
        "Cloud Computing":       "cloud computing summit",
        "Cybersecurity":         "cybersecurity conference",
        "Manufacturing":         "manufacturing industrial expo",
        "Logistics / Supply Chain": "supply chain logistics conference",
        "Healthcare / Medtech":  "healthcare medtech summit",
        "Fintech":               "fintech financial technology conference",
        "Retail / Ecommerce":    "retail ecommerce summit",
        "Energy / Cleantech":    "energy cleantech sustainability conference",
        "Data & Analytics":      "data analytics summit",
        "HR Tech":               "HR technology talent conference",
        "Marketing / Adtech":    "marketing technology conference",
        "Startup / VC":          "startup venture capital conference",
        "Legal Tech":            "legal technology conference",
        "Sustainability / ESG":  "sustainability ESG conference",
        "Telecommunications":    "telecom 5G connectivity summit",
        "Real Estate / PropTech": "proptech real estate technology conference",
        "Education / EdTech":    "education technology conference",
        "Agriculture / AgriTech": "agritech agriculture technology conference",
        "Automotive":            "automotive mobility technology expo",
        "Food & Beverage":       "food beverage processing conference",
        "Fashion / Apparel":     "fashion technology retail expo",
        "Construction / Infrastructure": "construction infrastructure technology expo",
        "Mining / Resources":    "mining resources technology conference",
        "Travel / Hospitality":  "travel hospitality technology conference",
    }
    kws = list(dict.fromkeys(_MAP.get(ind, f"{ind.lower()} conference") for ind in industries[:4]))
    return kws[:6] or ["technology conference", "business summit"]


# ── Sync wrapper for backward compatibility ───────────────────────────

def build_queries_sync(
    industries:   list[str],
    geographies:  list[str],
    personas:     list[str],
    event_types:  list[str],
    company_desc: str,
    date_from:    str,
    date_to:      str,
) -> QueryBundle:
    """
    Sync wrapper — uses fallback keywords (no Groq) since we can't
    safely run an event loop here.  Prefer calling build_queries() async.
    """
    today = date.today().isoformat()
    start = date_from or today
    end   = date_to   or "2028-12-31"
    year  = start[:4]
    keywords = _fallback_keywords(industries)

    resolved: list[tuple[str, dict]] = []
    is_global = any(g.lower() in ("global", "worldwide", "international", "any") for g in geographies)
    for geo in geographies:
        if geo in GEO_DATA:
            resolved.append((geo, GEO_DATA[geo]))
    if is_global or not resolved:
        for g in ["Singapore", "UK", "USA"]:
            resolved.append((g, GEO_DATA[g]))

    serp = [
        SerpAPIQuery(q=f"{kw} {year}", location=geo["serp"][0], year=year)
        for kw in keywords[:4]
        for _, geo in resolved[:2]
    ][:8]

    tm_cc = list({geo["tm"] for _, geo in resolved if geo.get("tm")}) or ["US", "GB"]
    start_dt = f"{start}T00:00:00Z"; end_dt = f"{end}T23:59:59Z"
    tm = [TicketmasterQuery(keyword=kw, country_code=cc, start_dt=start_dt, end_dt=end_dt)
          for kw in keywords[:4] for cc in tm_cc[:3]][:12]

    eb = [EventbriteQuery(keyword=kw, lat=geo["lat"], lon=geo["lon"],
                          radius=geo.get("eb_radius","100km"), date_from=start)
          for kw in keywords[:3] for _, geo in resolved[:3]][:9]

    phq_cc = list({geo["phq"] for _, geo in resolved if geo.get("phq")}) or ["US"]
    phq = [PredictHQQuery(q=kw, country_code=cc, start_gte=start, end_lte=end)
           for kw in keywords[:3] for cc in phq_cc[:2]][:6]

    return QueryBundle(serpapi=serp, ticketmaster=tm, eventbrite=eb,
                       predicthq=phq, year=year, keywords_used=keywords)


# ── Taxonomy expansion for crud.py DB queries ─────────────────────────

def _expand_industry_terms(industries: list[str]) -> list[str]:
    """
    Expand profile industry names into EventsEye taxonomy synonyms
    for SQL ILIKE queries in crud.py.
    """
    _SYNONYMS: list[tuple[str, list[str]]] = [
        ("manufactur",   ["manufactur", "metal work", "mechanical", "industrial machiner",
                          "machine tool", "welding", "casting", "forging", "cnc"]),
        ("engineering",  ["engineering", "manufactur", "metal", "mechanical component"]),
        ("industrial",   ["industrial", "manufactur", "metal work", "mechanical"]),
        ("technology",   ["technolog", "information technology", "software", "digital",
                          "compute", "network", "telecom", "electronic", "semiconductor",
                          "iot", "smart technolog", "multimedia", "cad", "cam"]),
        ("software",     ["software", "digital", "compute", "saas", "cloud"]),
        ("ai",           ["artificial intelligence", "machine learning", "deep learning",
                          "data science", "analytics"]),
        ("cloud",        ["cloud", "saas", "data center", "hosting"]),
        ("cybersecurity",["cyber", "information security", "network security", "data protection"]),
        ("fintech",      ["fintech", "financial technology", "digital banking", "payment"]),
        ("finance",      ["finance", "banking", "financial", "investment", "insurance"]),
        ("healthcare",   ["healthcare", "health", "medical", "medtech", "pharma",
                          "biotech", "hospital", "clinical", "life science"]),
        ("logistics",    ["logistic", "supply chain", "transport", "freight", "shipping",
                          "warehousing", "cargo", "handling", "distribution"]),
        ("retail",       ["retail", "ecommerce", "consumer", "fmcg", "fashion", "merchandise"]),
        ("food",         ["food processing", "food", "beverage", "catering", "hospitality",
                          "bakery", "dairy", "seafood", "wine", "spirits"]),
        ("energy",       ["energy", "oil", "gas", "petroleum", "renewable", "solar",
                          "wind", "power", "electricity"]),
        ("construction", ["construction", "build", "architect", "real estate", "civil",
                          "infrastructure", "contractor"]),
        ("mining",       ["mining", "mineral", "quarry", "ore", "coal", "metals", "extraction"]),
        ("marketing",    ["marketing", "advertising", "media", "digital marketing", "martech"]),
        ("fashion",      ["fashion", "textile", "cloth", "apparel", "fabric", "garment"]),
        ("education",    ["education", "training", "learning", "university", "academic"]),
        ("agriculture",  ["agriculture", "agri", "farming", "crop", "livestock",
                          "aquaculture", "fishery"]),
        ("travel",       ["travel", "tourism", "hospitality", "airline", "destination"]),
        ("automotive",   ["automotive", "vehicle", "car", "truck", "electric vehicle", "mobility"]),
        ("printing",     ["printing", "packaging", "graphic", "inkjet", "label"]),
        ("sustainability",["sustainab", "environmental", "cleantech", "green", "renewable",
                           "circular economy", "esg", "carbon"]),
        ("legal",        ["legal", "law", "compliance", "regulatory", "legaltech"]),
        ("telecom",      ["telecom", "5g", "network", "connectivity", "wireless"]),
    ]

    terms: list[str] = []
    seen: set[str]   = set()

    def _add(t: str):
        t = t.strip().lower()
        if t and t not in seen:
            seen.add(t); terms.append(t)

    for ind in industries:
        _add(ind)
        ind_lower = ind.lower()
        for key, synonyms in _SYNONYMS:
            if key in ind_lower or ind_lower in key:
                for s in synonyms:
                    _add(s)

    return terms
