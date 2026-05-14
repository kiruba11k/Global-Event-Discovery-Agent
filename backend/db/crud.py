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
    ("manufactur",  ["manufactur", "metal work", "mechanical", "industrial machiner",
                     "machine tool", "welding", "casting", "forging", "cnc",
                     "production technolog", "stamping", "sheet metal"]),
    ("engineering", ["engineering", "manufactur", "metal", "mechanical component",
                     "structural", "civil engineering"]),
    ("industrial",  ["industrial", "manufactur", "metal work", "mechanical"]),
    ("technology",  ["technolog", "information technology", "software", "digital",
                     "compute", "network", "telecom", "electronic", "semiconductor",
                     "iot", "smart technolog", "multimedia", "cad", "cam"]),
    ("information technology", ["information technology", "telecom", "compute", "network"]),
    ("software",    ["software", "digital", "compute", "saas", "cloud"]),
    ("ai",          ["artificial intelligence", "machine learning", "deep learning",
                     "data science", "analytics"]),
    ("cloud",       ["cloud", "saas", "data center", "hosting"]),
    ("cybersecurity", ["cyber", "information security", "network security", "data protection"]),
    ("fintech",     ["fintech", "financial technology", "digital banking", "payment"]),
    ("finance",     ["finance", "banking", "financial", "investment", "insurance"]),
    ("healthcare",  ["healthcare", "health", "medical", "medtech", "pharma",
                     "biotech", "hospital", "clinical", "life science"]),
    ("pharma",      ["pharma", "pharmaceutical", "biotech", "life science", "clinical"]),
    ("logistics",   ["logistic", "supply chain", "transport", "freight", "shipping",
                     "warehousing", "cargo", "handling", "distribution"]),
    ("supply chain",["supply chain", "logistic", "procurement", "warehousing"]),
    ("retail",      ["retail", "ecommerce", "consumer", "fmcg", "fashion", "merchandise"]),
    ("food",        ["food processing", "food", "beverage", "catering", "hospitality",
                     "bakery", "dairy", "seafood", "wine", "spirits"]),
    ("hospitality", ["hospitality", "catering", "hotel", "restaurant", "food service"]),
    ("energy",      ["energy", "oil", "gas", "petroleum", "renewable", "solar",
                     "wind", "power", "electricity"]),
    ("cleantech",   ["cleantech", "renewable", "solar", "wind", "green energy",
                     "environmental", "waste", "water treatment"]),
    ("construction",["construction", "build", "architect", "real estate", "civil",
                     "infrastructure", "contractor"]),
    ("mining",      ["mining", "mineral", "quarry", "ore", "coal", "metals", "extraction"]),
    ("marketing",   ["marketing", "advertising", "media", "digital marketing",
                     "martech", "brand", "pr"]),
    ("fashion",     ["fashion", "textile", "cloth", "apparel", "fabric", "garment"]),
    ("education",   ["education", "training", "learning", "university", "academic"]),
    ("agriculture", ["agriculture", "agri", "farming", "crop", "livestock",
                     "aquaculture", "fishery"]),
    ("travel",      ["travel", "tourism", "hospitality", "airline", "destination"]),
    ("automotive",  ["automotive", "vehicle", "car", "truck", "electric vehicle", "mobility"]),
    ("printing",    ["printing", "packaging", "graphic", "inkjet", "label"]),
    ("hr",          ["human resource", "hr ", "talent", "recruitment", "workforce"]),
]


def _expand_industry_terms(industries: List[str]) -> List[str]:
    """
    Given a list of profile industry names, return a deduplicated list of
    search terms (each used in ILIKE) that covers the EventsEye taxonomy.
    Always includes the original terms as well.
    """
    terms: list[str] = []
    seen:  set[str]  = set()

    def _add(t: str):
        t = t.strip().lower()
        if t and t not in seen:
            seen.add(t)
            terms.append(t)

    for ind in industries:
        _add(ind)  # always include the raw profile value
        ind_lower = ind.lower()
        for key, synonyms in _INDUSTRY_SYNONYMS:
            if key in ind_lower or ind_lower in key:
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

async def upsert_event(db: AsyncSession, event: EventCreate) -> bool:
    """Insert or skip-on-conflict. Returns True if a new row was inserted."""
    try:
        stmt = (
            _dialect_insert(EventORM)
            .values(
                id=event.id, source_platform=event.source_platform,
                source_url=event.source_url, dedup_hash=event.dedup_hash,
                name=event.name, description=event.description,
                short_summary=event.short_summary, edition_number=event.edition_number,
                start_date=event.start_date, end_date=event.end_date,
                duration_days=event.duration_days, venue_name=event.venue_name,
                address=event.address, city=event.city, country=event.country,
                is_virtual=event.is_virtual, is_hybrid=event.is_hybrid,
                est_attendees=event.est_attendees, category=event.category,
                industry_tags=event.industry_tags, audience_personas=event.audience_personas,
                ticket_price_usd=event.ticket_price_usd,
                price_description=event.price_description,
                registration_url=event.registration_url, sponsors=event.sponsors,
                speakers_url=event.speakers_url, agenda_url=event.agenda_url,
                event_cities=event.event_cities, event_venues=event.event_venues,
                related_industries=event.related_industries, website=event.website,
                ingested_at=datetime.utcnow(), last_verified_at=datetime.utcnow(),
            )
            .on_conflict_do_nothing(index_elements=["dedup_hash"])
        )
        result = await db.execute(stmt)
        await db.commit()
        return result.rowcount != 0
    except Exception as exc:
        logger.error(f"upsert_event error [{event.name[:40]}]: {exc}")
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
        if skip_past and event.start_date and event.start_date < today:
            skipped += 1
            continue
        if not event.start_date:
            skipped += 1
            continue
        rows.append(dict(
            id=event.id, source_platform=event.source_platform,
            source_url=event.source_url, dedup_hash=event.dedup_hash,
            name=event.name, description=event.description,
            short_summary=event.short_summary, edition_number=event.edition_number,
            start_date=event.start_date, end_date=event.end_date,
            duration_days=event.duration_days, venue_name=event.venue_name,
            address=event.address, city=event.city, country=event.country,
            is_virtual=event.is_virtual, is_hybrid=event.is_hybrid,
            est_attendees=event.est_attendees, category=event.category,
            industry_tags=event.industry_tags, audience_personas=event.audience_personas,
            ticket_price_usd=event.ticket_price_usd,
            price_description=event.price_description,
            registration_url=event.registration_url, sponsors=event.sponsors,
            speakers_url=event.speakers_url, agenda_url=event.agenda_url,
            event_cities=event.event_cities, event_venues=event.event_venues,
            related_industries=event.related_industries, website=event.website,
            ingested_at=datetime.utcnow(), last_verified_at=datetime.utcnow(),
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
