"""
db/crud.py — fixed for Neon DB with EventsEye trade show data.

Key fixes:
  1. get_candidate_events: min_attendees ALWAYS treated as 0 because all DB events
     have est_attendees=0 (unknown, not actually zero attendees).
  2. get_candidate_events: industry search now expands profile industry names into
     EventsEye taxonomy synonyms so "Manufacturing" matches
     "Metal Working Industries, Mechanical Components".
  3. geo filter searches city, country AND event_cities (the new column).
"""
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
import json as _json
import uuid
from loguru import logger
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.company_profile import CompanyProfileCreate, CompanyProfileORM
from models.event import EventCreate, EventORM


# ══════════════════════════════════════════════════════════════════════
# Taxonomy expansion for get_candidate_events industry filter
#
# Profile industry names → EventsEye-style tags to search in industry_tags.
# This allows "Manufacturing" to match "Metal Working Industries" etc.
# Each entry: (lowercase profile term, list of ILIKE search patterns)
# ══════════════════════════════════════════════════════════════════════
_INDUSTRY_SYNONYMS: list[tuple[str, list[str]]] = [
  ("manufactur",        ["manufactur", "metal work", "mechanical", "industrial machiner",
                           "machine tool", "welding", "casting", "forging", "cnc",
                           "production technolog", "stamping", "sheet metal", "factory",
                           "automation", "robotics", "alloy", "steel", "aluminium"]),
    ("engineering",       ["engineering", "manufactur", "metal", "mechanical component",
                           "structural", "civil engineering", "aerospace", "process engineering"]),
    ("industrial",        ["industrial", "manufactur", "metal work", "mechanical", "factory",
                           "production", "process industry", "heavy industry"]),
    # Technology
    ("technology",        ["technolog", "information technology", "software", "digital",
                           "compute", "network", "telecom", "electronic", "semiconductor",
                           "iot", "smart technolog", "multimedia", "cad", "cam", "tech"]),
    ("information technology", ["information technology", "telecom", "compute", "network",
                                "it service", "it solution", "digital transformation"]),
    ("software",          ["software", "digital", "compute", "saas", "cloud", "application",
                           "platform", "enterprise software", "b2b software"]),
    ("it",                ["information technology", "it ", "it service", "software",
                           "compute", "network", "digital"]),
    ("tech",              ["technolog", "software", "digital", "compute", "iot", "smart"]),
    # AI / Data
    ("ai",                ["artificial intelligence", "machine learning", "deep learning",
                           "data science", "analytics", "automation", "robotics", "nlp",
                           "computer vision", "predictive", "generative ai"]),
    ("artificial intelligence", ["artificial intelligence", "machine learning", "deep learning",
                                 "data science", "analytics", "nlp", "computer vision"]),
    ("machine learning",  ["machine learning", "deep learning", "artificial intelligence",
                           "data science", "analytics", "predictive analytics"]),
    ("data",              ["data science", "analytics", "data management", "big data",
                           "data engineering", "business intelligence", "data platform"]),
    ("analytics",         ["analytics", "data science", "business intelligence", "big data",
                           "data analytics", "reporting"]),
    ("cloud computing",   ["cloud", "saas", "paas", "iaas", "data center", "hosting",
                           "cloud platform", "cloud infrastructure", "virtualisation"]),
    ("cloud",             ["cloud", "saas", "data center", "hosting", "cloud platform"]),
    ("saas",              ["saas", "software as a service", "cloud", "b2b software", "platform"]),
    # Cybersecurity
    ("cybersecurity",     ["cyber", "information security", "network security", "data protection",
                           "cybersecurity", "infosec", "identity", "zero trust", "siem",
                           "endpoint security", "vulnerability", "compliance"]),
    ("security",          ["security", "cyber", "information security", "network security",
                           "data protection", "infosec", "privacy"]),
    ("infosec",           ["information security", "cybersecurity", "cyber", "network security"]),
    # Finance
    ("fintech",           ["fintech", "financial technology", "digital banking", "payment",
                           "insurtech", "regtech", "blockchain", "cryptocurrency",
                           "digital finance", "open banking", "neobank", "lending tech"]),
    ("finance",           ["finance", "banking", "financial", "investment", "capital market",
                           "insurance", "treasury", "fintech", "accounting", "wealth management",
                           "asset management", "private equity", "hedge fund", "fund management"]),
    ("financial",         ["finance", "financial", "banking", "investment", "capital market",
                           "insurance", "treasury", "fintech", "accounting"]),
    ("banking",           ["banking", "finance", "financial", "payment", "fintech",
                           "digital banking", "retail banking", "commercial banking"]),
    ("insurance",         ["insurance", "insurtech", "risk management", "reinsurance",
                           "underwriting", "actuarial", "claims"]),
    ("investment",        ["investment", "capital market", "private equity", "venture capital",
                           "asset management", "wealth management", "fund"]),
    ("accounting",        ["accounting", "finance", "audit", "taxation", "cpa",
                           "financial reporting", "bookkeeping"]),
    ("payments",          ["payment", "fintech", "digital payment", "transaction",
                           "remittance", "card payment", "wallet"]),
    # Healthcare / Life Sciences
    ("healthcare",        ["healthcare", "health", "medical", "medtech", "pharma",
                           "biotech", "hospital", "clinical", "life science", "dental",
                           "optical", "nursing", "diagnostic", "telemedicine", "digital health"]),
    ("health",            ["health", "healthcare", "medical", "hospital", "clinical",
                           "wellness", "public health", "preventive health"]),
    ("medtech",           ["medtech", "medical device", "medical equipment", "diagnostic",
                           "imaging", "surgical", "medical technology"]),
    ("pharma",            ["pharma", "pharmaceutical", "drug", "biotech", "life science",
                           "clinical", "laboratory", "clinical trial", "regulatory"]),
    ("biotech",           ["biotech", "life science", "pharmaceutical", "genomics",
                           "bioinformatics", "drug discovery", "medical research"]),
    ("medical",           ["medical", "healthcare", "medtech", "clinical", "hospital",
                           "diagnostic", "medical device"]),
    # Logistics / Supply Chain
    ("logistics",         ["logistic", "supply chain", "transport", "freight", "shipping",
                           "warehousing", "cargo", "courier", "last mile", "fleet",
                           "handling", "intralogistic", "distribution", "port", "3pl"]),
    ("supply chain",      ["supply chain", "logistic", "procurement", "sourcing",
                           "warehousing", "inventory", "distribution", "vendor management"]),
    ("transportation",    ["transport", "logistic", "freight", "shipping", "truck",
                           "rail", "aviation", "maritime", "fleet management", "mobility"]),
    ("procurement",       ["procurement", "supply chain", "sourcing", "purchasing",
                           "vendor management", "category management", "strategic sourcing"]),
    ("warehousing",       ["warehousing", "logistics", "distribution", "fulfillment",
                           "warehouse management", "storage"]),
    # Retail / E-commerce / Consumer
    ("retail",            ["retail", "ecommerce", "consumer", "fmcg", "fashion",
                           "merchandise", "shopping", "omnichannel", "pos",
                           "direct-to-consumer", "d2c", "brand"]),
    ("ecommerce",         ["ecommerce", "e-commerce", "online retail", "digital commerce",
                           "marketplace", "d2c", "shopify", "amazon seller"]),
    ("consumer goods",    ["consumer", "fmcg", "household", "appliance", "personal care",
                           "food", "beverage", "retail", "cpg"]),
    ("fmcg",              ["fmcg", "consumer goods", "cpg", "household", "personal care",
                           "food", "beverage", "retail"]),
    # Food & Beverage / Hospitality
    ("food & beverage",   ["food processing", "food", "beverage", "catering", "hospitality",
                           "restaurant", "hotel", "bakery", "dairy", "meat", "seafood",
                           "organic", "wine", "spirits", "packaging", "food safety"]),
    ("food",              ["food processing", "food", "beverage", "catering", "bakery",
                           "dairy", "seafood", "agri", "fmcg", "food retail"]),
    ("hospitality",       ["hospitality", "catering", "hotel", "restaurant", "food service",
                           "tourism", "travel", "mice", "events industry"]),
    ("restaurant",        ["restaurant", "catering", "food service", "hospitality",
                           "food & beverage", "hotel"]),
    ("beverage",          ["beverage", "food & beverage", "wine", "spirits", "beer",
                           "soft drink", "drink industry"]),
    # Energy / Environment
    ("energy",            ["energy", "oil", "gas", "petroleum", "renewable", "solar",
                           "wind", "nuclear", "power", "electricity", "utility",
                           "energy storage", "battery", "grid"]),
    ("cleantech",         ["cleantech", "renewable", "solar", "wind", "green energy",
                           "sustainable", "environmental", "waste", "water treatment",
                           "clean energy", "green tech", "sustainability"]),
    ("sustainability",    ["sustainab", "environmental", "cleantech", "green", "renewable",
                           "circular economy", "esg", "carbon", "net zero", "climate",
                           "decarbonisation", "green building"]),
    ("esg",               ["esg", "sustainability", "environmental", "governance",
                           "corporate responsibility", "csr", "climate", "carbon"]),
    ("renewable energy",  ["renewable", "solar", "wind", "green energy", "clean energy",
                           "hydro", "geothermal", "energy storage"]),
    ("oil and gas",       ["oil", "gas", "petroleum", "upstream", "downstream", "midstream",
                           "refinery", "drilling", "exploration"]),
    # Real Estate / Construction
    ("construction",      ["construction", "build", "architect", "real estate", "civil",
                           "infrastructure", "contractor", "property", "build material"]),
    ("real estate",       ["real estate", "property", "construction", "land", "housing",
                           "commercial real estate", "residential", "proptech"]),
    ("proptech",          ["proptech", "real estate", "property technology", "smart building",
                           "building management", "facility management"]),
    # Mining / Resources
    ("mining",            ["mining", "mineral", "quarry", "ore", "coal", "metals",
                           "extraction", "petroleum", "resources", "geolog"]),
    # Media / Print / Marketing
    ("marketing",         ["marketing", "advertising", "media", "digital marketing",
                           "martech", "brand", "pr", "communication", "promotion",
                           "content marketing", "demand generation", "lead generation"]),
    ("media",             ["media", "publishing", "broadcast", "print", "graphic",
                           "content", "advertising", "news", "journalism"]),
    ("advertising",       ["advertising", "marketing", "adtech", "digital advertising",
                           "media buying", "programmatic", "brand"]),
    ("martech",           ["martech", "marketing technology", "crm", "marketing automation",
                           "analytics", "digital marketing", "demand generation"]),
    # HR / People / Workforce
    ("hr tech",           ["human resource", "hr", "talent", "recruitment", "workforce",
                           "payroll", "people management", "future of work", "hris",
                           "employee experience", "talent acquisition"]),
    ("hr",                ["human resource", "hr ", "talent", "recruitment", "workforce",
                           "people management", "employee", "hris"]),
    ("human resources",   ["human resource", "hr", "talent management", "recruitment",
                           "workforce", "people ops", "payroll"]),
    ("talent management", ["talent", "recruitment", "hr", "workforce", "learning",
                           "people development", "succession planning"]),
    # Education
    ("education",         ["education", "training", "learning", "university", "academic",
                           "e-learning", "professional development", "edtech", "school",
                           "corporate training", "upskilling", "reskilling"]),
    ("edtech",            ["edtech", "education technology", "e-learning", "lms",
                           "online learning", "education"]),
    # Agriculture
    ("agriculture",       ["agriculture", "agri", "farming", "crop", "livestock",
                           "aquaculture", "fishery", "agritech", "smart farming",
                           "precision agriculture", "food production"]),
    ("agritech",          ["agritech", "agriculture technology", "smart farming",
                           "precision agriculture", "agri", "farming tech"]),
    # Travel / Tourism
    ("travel",            ["travel", "tourism", "hospitality", "airline", "hotel",
                           "destination", "mice", "business travel", "ota"]),
    # Automotive
    ("automotive",        ["automotive", "vehicle", "car", "truck", "electric vehicle",
                           "ev", "mobility", "fleet", "auto", "connected vehicle",
                           "autonomous vehicle", "telematics"]),
    ("electric vehicle",  ["electric vehicle", "ev", "battery", "charging", "mobility",
                           "automotive", "clean transport"]),
    # Fashion / Textile
    ("fashion",           ["fashion", "textile", "clothing", "apparel", "fabric",
                           "garment", "leather", "footwear", "luxury", "fast fashion"]),
    ("textile",           ["textile", "fabric", "garment", "apparel", "fashion",
                           "yarn", "weaving", "knitting"]),
    # Printing / Packaging
    ("printing",          ["printing", "packaging", "graphic", "inkjet", "label",
                           "flexo", "offset", "digital print", "wide format"]),
    ("packaging",         ["packaging", "printing", "label", "flexible packaging",
                           "rigid packaging", "sustainability packaging"]),
    # Telecom
    ("telecom",           ["telecom", "5g", "network", "connectivity", "wireless",
                           "fibre", "broadband", "isp", "mobile", "carrier", "mvno"]),
    ("telecommunications", ["telecom", "telecommunications", "5g", "network", "wireless",
                            "mobile", "connectivity", "broadband"]),
    # Legal Tech
    ("legal",             ["legal tech", "legal", "law", "compliance", "regulatory",
                           "governance", "contract management", "litigation"]),
    ("legaltech",         ["legal tech", "legal", "law", "compliance", "contract"]),
    # Government / Public Sector
    ("government",        ["government", "public sector", "smart city", "civic tech",
                           "e-government", "policy", "public administration"]),
    ("public sector",     ["public sector", "government", "municipal", "smart city",
                           "public service", "civic"]),
    # Defence / Aerospace
    ("defence",           ["defence", "defense", "aerospace", "military", "security",
                           "space", "aviation", "unmanned", "drone"]),
    ("aerospace",         ["aerospace", "aviation", "space", "defence", "aircraft",
                           "satellite", "uav", "drone"]),
    # Sports Technology
    ("sports",            ["sports technology", "sport", "esports", "fitness",
                           "wearable", "sports analytics", "stadium tech"]),
    # Business / Professional Services
    ("business services", ["business service", "professional service", "consulting",
                           "management consulting", "outsourcing", "bpo", "shared service"]),
    ("consulting",        ["consulting", "management consulting", "advisory", "professional service"]),
  ]


def _expand_industry_terms(industries: List[str]) -> List[str]:
    """
    Given a list of profile industry names, return a deduplicated list of
    search terms (each used in ILIKE) that covers the EventsEye taxonomy.
    Uses prefix-stem matching so "financial" activates "finance" synonyms.
    """
    terms: list[str] = []
    seen:  set[str]  = set()

    def _add(t: str):
        t = t.strip().lower()
        if t and len(t) >= 2 and t not in seen:
            seen.add(t)
            terms.append(t)

    for ind in industries:
        _add(ind)  # always include the raw profile value
        ind_lower = ind.lower().strip()
        # Generate sub-tokens from the profile value (handles multi-word like "supply chain")
        ind_tokens = [w for w in ind_lower.replace("/", " ").replace("-", " ").split() if len(w) > 2]
        for token in ind_tokens:
            _add(token)
        # Match taxonomy synonyms by exact key or prefix-stem overlap
        for key, synonyms in _INDUSTRY_SYNONYMS:
            # Check if profile industry activates this synonym group
            key_match = (
                key in ind_lower or
                ind_lower in key or
                any(t in key or key.startswith(t[:min(len(t), 6)]) for t in ind_tokens if len(t) >= 4)
            )
            if key_match:
                for syn in synonyms:
                    _add(syn)

    return terms


# ── Dialect-aware INSERT ───────────────────────────────────────────

def _dialect_insert(orm_class):
    from config import get_settings
    url = get_settings().database_url
    if url.startswith(("postgresql", "postgres")):
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    return insert(orm_class)


# ══════════════════════════════════════════════════════════════════════
# Event CRUD
# ══════════════════════════════════════════════════════════════════════

async def upsert_event(db: AsyncSession, event) -> bool:
    """
    Insert or skip-on-conflict (dedup_hash).
    Accepts either an EventCreate Pydantic model OR a plain dict
    (from platform_normaliser.normalise()).
    Returns True if a new row was inserted.
    """
    # Support both Pydantic model and raw dict (from normaliser)
    if isinstance(event, dict):
        d = event
    else:
        d = event.dict() if hasattr(event, "dict") else vars(event)

    try:
        stmt = (
            _dialect_insert(EventORM)
            .values(
                id                = d.get("id") or str(uuid.uuid4()),
                source_platform   = d.get("source_platform", ""),
                source_url        = d.get("source_url", ""),
                dedup_hash        = d.get("dedup_hash", ""),
                name              = d.get("name", ""),
                description       = d.get("description", ""),
                category          = d.get("category", ""),
                start_date        = d.get("start_date", ""),
                end_date          = d.get("end_date", ""),
                venue_name        = d.get("venue_name", ""),
                city              = d.get("city", ""),
                country           = d.get("country", ""),
                industry_tags     = d.get("industry_tags", ""),
                audience_personas = d.get("audience_personas", ""),
                est_attendees     = int(d.get("est_attendees") or 0),
                price_description = d.get("price_description", ""),
                registration_url  = d.get("registration_url", ""),
                website           = d.get("website", ""),
                sponsors          = d.get("sponsors", ""),
                speakers_url      = d.get("speakers_url", ""),
                agenda_url        = d.get("agenda_url", ""),
                relevance_score   = float(d.get("relevance_score") or 0.0),
                relevance_tier    = d.get("relevance_tier", ""),
                rationale         = d.get("rationale", ""),
                confidence_score  = float(d.get("confidence_score") or 0.8),
                ingested_at       = datetime.utcnow(),
                last_verified_at  = datetime.utcnow(),
                serpapi_enriched  = bool(d.get("serpapi_enriched", False)),
            )
            .on_conflict_do_nothing(index_elements=["dedup_hash"])
        )
        result = await db.execute(stmt)
        await db.commit()
        return result.rowcount != 0
    except Exception as exc:
        logger.error(f"upsert_event error [{d.get('name','?')[:40]}]: {exc}")
        await db.rollback()
        return False


async def batch_upsert_events(
    db:         AsyncSession,
    events:     List[EventCreate],
    skip_past:  bool = True,
) -> Tuple[int, int]:
    if not events:
        return 0, 0

    today    = date.today().isoformat()
    inserted = 0
    skipped  = 0
    rows: list = []

    for event in events:
        # Resolve to dict first — handles both Pydantic models and plain dicts
        d = event if isinstance(event, dict) else (event.dict() if hasattr(event, "dict") else vars(event))
        if skip_past and d.get("start_date") and d.get("start_date") < today:
            skipped += 1
            continue
        if not d.get("start_date"):
            skipped += 1
            continue
        rows.append(dict(
            id                = d.get("id") or str(uuid.uuid4()),
            source_platform   = d.get("source_platform", ""),
            source_url        = d.get("source_url", ""),
            dedup_hash        = d.get("dedup_hash", ""),
            name              = d.get("name", ""),
            description       = d.get("description", ""),
            category          = d.get("category", ""),
            start_date        = d.get("start_date", ""),
            end_date          = d.get("end_date", ""),
            venue_name        = d.get("venue_name", ""),
            city              = d.get("city", ""),
            country           = d.get("country", ""),
            industry_tags     = d.get("industry_tags", ""),
            audience_personas = d.get("audience_personas", ""),
            est_attendees     = int(d.get("est_attendees") or 0),
            price_description = d.get("price_description", ""),
            registration_url  = d.get("registration_url", ""),
            website           = d.get("website", ""),
            sponsors          = d.get("sponsors", ""),
            speakers_url      = d.get("speakers_url", ""),
            agenda_url        = d.get("agenda_url", ""),
            relevance_score   = float(d.get("relevance_score") or 0.0),
            relevance_tier    = d.get("relevance_tier", ""),
            rationale         = d.get("rationale", ""),
            confidence_score  = float(d.get("confidence_score") or 0.8),
            ingested_at       = datetime.utcnow(),
            last_verified_at  = datetime.utcnow(),
            serpapi_enriched  = bool(d.get("serpapi_enriched", False)),
        ))

    if not rows:
        return 0, skipped

    try:
        chunk_size = 500
        for i in range(0, len(rows), chunk_size):
            chunk  = rows[i: i + chunk_size]
            stmt   = (
                _dialect_insert(EventORM)
                .values(chunk)
                .on_conflict_do_nothing(index_elements=["dedup_hash"])
            )
            result = await db.execute(stmt)
            chunk_inserted = result.rowcount if result.rowcount >= 0 else len(chunk)
            inserted += chunk_inserted
        await db.commit()
    except Exception as exc:
        logger.error(f"batch_upsert_events error: {exc}")
        await db.rollback()
        return 0, skipped

    return inserted, skipped


async def get_candidate_events(
    db:           AsyncSession,
    geographies:  List[str],
    industries:   List[str],
    date_from:    Optional[str],
    date_to:      Optional[str],
    min_attendees: int = 0,
    limit:        int = 400,
) -> List[EventORM]:
    """
    Fetch candidate events from the DB.

    IMPORTANT: min_attendees is IGNORED — all DB events have est_attendees=0
    (meaning unknown, not actually zero). The scorer handles relevance ranking.

    Industry filter uses expanded taxonomy synonyms so that profile industries
    like "Manufacturing" correctly match DB tags like "Metal Working Industries".
    """
    today     = date.today().isoformat()
    date_from = date_from or today
    date_to   = date_to   or "2030-12-31"

    # Base date filter — NEVER filter by attendees (all are 0 in DB)
    stmt = select(EventORM).where(
        EventORM.start_date >= date_from,
        EventORM.start_date <= date_to,
    )

    # Geography filter
    if geographies and "global" not in [g.lower().strip() for g in geographies]:
        geo_filters = []
        for geo in geographies:
            geo_lower = geo.strip().lower()
            # Strip "UK - United Kingdom" → search both parts
            geo_parts = [geo_lower]
            if " - " in geo_lower:
                geo_parts.extend(p.strip() for p in geo_lower.split(" - "))
            for part in geo_parts:
                if len(part) > 1:
                    geo_filters.append(EventORM.country.ilike(f"%{part}%"))
                    geo_filters.append(EventORM.city.ilike(f"%{part}%"))
                    geo_filters.append(EventORM.event_cities.ilike(f"%{part}%"))
        if geo_filters:
            stmt = stmt.where(or_(*geo_filters))

    # Industry filter with taxonomy expansion
    # Searches: industry_tags (primary), related_industries, category, name, description
    if industries:
        expanded_terms = _expand_industry_terms(industries)
        industry_filters = []
        for term in expanded_terms:
            # Use industry_tags as the PRIMARY search target (it's populated)
            industry_filters.append(EventORM.industry_tags.ilike(f"%{term}%"))
            # Also check related_industries (NULL in current DB but may be populated later)
            industry_filters.append(EventORM.related_industries.ilike(f"%{term}%"))
            # And description for richer matching
            industry_filters.append(EventORM.description.ilike(f"%{term}%"))
            industry_filters.append(EventORM.name.ilike(f"%{term}%"))
        stmt = stmt.where(or_(*industry_filters))

    result = await db.execute(stmt.limit(limit))
    rows   = list(result.scalars().all())
    logger.debug(
        f"get_candidate_events: geo={geographies} ind={industries[:3]} "
        f"date={date_from}..{date_to} → {len(rows)} rows"
    )
    return rows


async def get_all_events(db: AsyncSession, limit: int = 500) -> List[EventORM]:
    result = await db.execute(select(EventORM).limit(limit))
    return list(result.scalars().all())


async def get_event_by_id(db: AsyncSession, event_id: str) -> Optional[EventORM]:
    result = await db.execute(select(EventORM).where(EventORM.id == event_id))
    return result.scalar_one_or_none()


async def count_events(db: AsyncSession) -> int:
    result = await db.execute(select(func.count(EventORM.id)))
    return result.scalar() or 0


async def update_event_enrichment(
    db:       AsyncSession,
    event_id: str,
    updates:  dict,
) -> bool:
    """
    Update enrichment fields on an existing event row.
    Only updates non-None values.  Marks serpapi_enriched=True.

    `description` and `audience_personas` feed the pgvector embedding
    text (relevance/pgvector_store.py build_event_text). If either
    changes here, the event's existing embedding no longer reflects its
    content, so it's cleared back to NULL — the next search that touches
    this event will lazily re-embed it (embed_missing() only fills rows
    WHERE embedding IS NULL). Harmless no-op when pgvector is off or the
    column doesn't exist (SQLite, or Postgres before ensure_schema runs).
    """
    from sqlalchemy import update as _update, text as _text
    allowed = {
        "est_attendees", "registration_url", "website",
        "start_date", "end_date", "price_description",
        "audience_personas", "description",
    }
    payload: dict = {k: v for k, v in updates.items() if k in allowed and v is not None}
    if not payload:
        return False
    payload["serpapi_enriched"] = True
    payload["last_verified_at"] = datetime.utcnow()
    from config import get_settings as _get_settings
    embedding_stale = (
        ("description" in payload or "audience_personas" in payload)
        and _get_settings().pgvector_enabled
    )
    try:
        await db.execute(
            _update(EventORM).where(EventORM.id == event_id).values(**payload)
        )
        if embedding_stale:
            # Best-effort, in its own SAVEPOINT: if the embedding column
            # doesn't exist yet (schema not provisioned), this rolls back
            # to the savepoint only — it can't poison the enrichment
            # update above or force it to be discarded too.
            try:
                async with db.begin_nested():
                    await db.execute(
                        _text("UPDATE events SET embedding = NULL WHERE id = :id"),
                        {"id": event_id},
                    )
            except Exception as exc:
                logger.debug(f"embedding invalidation skipped [{event_id[:8]}]: {exc}")
        await db.commit()
        return True
    except Exception as exc:
        logger.error(f"update_event_enrichment [{event_id[:8]}]: {exc}")
        await db.rollback()
        return False

async def count_by_source(db: AsyncSession) -> Dict[str, int]:
    result = await db.execute(
        select(EventORM.source_platform, func.count(EventORM.id))
        .group_by(EventORM.source_platform)
        .order_by(func.count(EventORM.id).desc())
    )
    return {row[0]: row[1] for row in result.all()}


async def purge_past_events(db: AsyncSession, grace_days: int = 7) -> int:
    cutoff = (date.today() - timedelta(days=grace_days)).isoformat()
    result = await db.execute(
        delete(EventORM).where(
            EventORM.end_date < cutoff,
            EventORM.end_date != "",
            EventORM.end_date.isnot(None),
            EventORM.source_platform != "Seed",
        )
    )
    await db.commit()
    purged = result.rowcount
    if purged:
        logger.info(f"Purged {purged} events ended before {cutoff}.")
    return purged


# ══════════════════════════════════════════════════════════════════════
# Company Profile CRUD
# ══════════════════════════════════════════════════════════════════════

async def create_company_profile(
    db:            AsyncSession,
    data:          CompanyProfileCreate,
    deck_text:     str = "",
    deck_filename: str = "",
) -> CompanyProfileORM:
    profile = CompanyProfileORM(
        id           = str(uuid.uuid4()),
        company_name = data.company_name,
        founded_year = data.founded_year,
        location     = data.location,
        what_we_do   = data.what_we_do,
        what_we_need = data.what_we_need,
        deck_text    = deck_text[:8000],
        deck_filename= deck_filename,
        client_names = _json.dumps(data.client_names or []),
        created_at   = datetime.utcnow(),
        updated_at   = datetime.utcnow(),
    )

    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    logger.info(f"Company profile created: {profile.id}")
    return profile


async def get_company_profile(
    db: AsyncSession, profile_id: str
) -> Optional[CompanyProfileORM]:
    result = await db.execute(
        select(CompanyProfileORM).where(CompanyProfileORM.id == profile_id)
    )
    return result.scalar_one_or_none()


async def update_company_profile_client_names(
    db: AsyncSession, profile_id: str, client_names: list
) -> None:
    """Merge new client names into an existing company profile record."""
    import json as _json
    cp = await get_company_profile(db, profile_id)
    if not cp:
        return
    existing = []
    try:
        existing = _json.loads(cp.client_names or "[]")
        if not isinstance(existing, list):
            existing = []
    except Exception:
        pass
    merged = list(dict.fromkeys(existing + client_names))  # dedupe, preserve order
    cp.client_names = _json.dumps(merged)
    cp.updated_at   = datetime.utcnow()
    await db.commit()


# ── Search submissions (durable ICP form log — see models/search_submission.py) ──

async def create_search_submission(
    db: AsyncSession,
    *,
    ip_address: str,
    profile_json: str,
    company_name: str,
    email: str,
    company_profile_id: str,
    job_id: str,
) -> "SearchSubmissionORM":
    from models.search_submission import SearchSubmissionORM
    row = SearchSubmissionORM(
        id                 = str(uuid.uuid4()),
        ip_address         = ip_address,
        profile_json       = profile_json,
        company_name       = company_name,
        email              = email,
        company_profile_id = company_profile_id or "",
        job_id             = job_id or "",
        status             = "queued",
        submitted_at       = datetime.utcnow(),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def update_search_submission_status(
    db: AsyncSession,
    row_id: str,
    *,
    status: str,
    result_total_found: Optional[int] = None,
    error: str = "",
) -> None:
    from models.search_submission import SearchSubmissionORM
    result = await db.execute(
        select(SearchSubmissionORM).where(SearchSubmissionORM.id == row_id)
    )
    row = result.scalar_one_or_none()
    if not row:
        return
    row.status = status
    if result_total_found is not None:
        row.result_total_found = result_total_found
    if error:
        row.error = error[:2000]
    if status in ("done", "error"):
        row.completed_at = datetime.utcnow()
    await db.commit()
