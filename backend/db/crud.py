"""
CRUD helpers — dialect-aware upsert (SQLite dev / PostgreSQL prod).

Key fixes:
  - _dialect_insert() picks sqlite or postgresql dialect automatically
  - count_by_source() ADDED  ← fixes ImportError in ingestion_manager
  - batch_upsert_events() uses correct rowcount fallback for asyncpg
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func, or_
from models.event import EventORM, EventCreate
from models.company_profile import CompanyProfileORM, CompanyProfileCreate
from datetime import datetime, date, timedelta
from typing import List, Optional, Tuple, Dict
import uuid
from loguru import logger


# ── Dialect-aware INSERT ───────────────────────────────────────────

def _dialect_insert(orm_class):
    """
    Return an INSERT object for the correct SQL dialect.
    Both dialects expose .on_conflict_do_nothing(index_elements=[...]).
    """
    from config import get_settings
    url = get_settings().database_url
    if url.startswith(("postgresql", "postgres")):
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    return insert(orm_class)


# ═══════════════════════════════════════════════════════════
# Event CRUD
# ═══════════════════════════════════════════════════════════

async def upsert_event(db: AsyncSession, event: EventCreate) -> bool:
    """Insert or skip-on-conflict. True = new row inserted."""
    try:
        stmt = (
            _dialect_insert(EventORM)
            .values(
                id=event.id,
                source_platform=event.source_platform,
                source_url=event.source_url,
                dedup_hash=event.dedup_hash,
                name=event.name,
                description=event.description,
                short_summary=event.short_summary,
                edition_number=event.edition_number,
                start_date=event.start_date,
                end_date=event.end_date,
                duration_days=event.duration_days,
                venue_name=event.venue_name,
                address=event.address,
                city=event.city,
                country=event.country,
                is_virtual=event.is_virtual,
                is_hybrid=event.is_hybrid,
                est_attendees=event.est_attendees,
                category=event.category,
                industry_tags=event.industry_tags,
                audience_personas=event.audience_personas,
                ticket_price_usd=event.ticket_price_usd,
                price_description=event.price_description,
                registration_url=event.registration_url,
                sponsors=event.sponsors,
                speakers_url=event.speakers_url,
                agenda_url=event.agenda_url,
                ingested_at=datetime.utcnow(),
                last_verified_at=datetime.utcnow(),
            )
            .on_conflict_do_nothing(index_elements=["dedup_hash"])
        )
        result = await db.execute(stmt)
        await db.commit()
        # rowcount==1→inserted; 0→conflict; -1→driver unknown (treat as inserted)
        return result.rowcount != 0
    except Exception as e:
        logger.error(f"upsert_event error [{event.name[:40]}]: {e}")
        await db.rollback()
        return False


async def batch_upsert_events(
    db: AsyncSession,
    events: List[EventCreate],
    skip_past: bool = True,
) -> Tuple[int, int]:
    """
    Upsert a list of events in chunked transactions.
    Returns (inserted_count, skipped_count).
    """
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
            id=event.id,
            source_platform=event.source_platform,
            source_url=event.source_url,
            dedup_hash=event.dedup_hash,
            name=event.name,
            description=event.description,
            short_summary=event.short_summary,
            edition_number=event.edition_number,
            start_date=event.start_date,
            end_date=event.end_date,
            duration_days=event.duration_days,
            venue_name=event.venue_name,
            address=event.address,
            city=event.city,
            country=event.country,
            is_virtual=event.is_virtual,
            is_hybrid=event.is_hybrid,
            est_attendees=event.est_attendees,
            category=event.category,
            industry_tags=event.industry_tags,
            audience_personas=event.audience_personas,
            ticket_price_usd=event.ticket_price_usd,
            price_description=event.price_description,
            registration_url=event.registration_url,
            sponsors=event.sponsors,
            speakers_url=event.speakers_url,
            agenda_url=event.agenda_url,
            ingested_at=datetime.utcnow(),
            last_verified_at=datetime.utcnow(),
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
            # asyncpg may return -1 for unknown rowcount → fall back to chunk len
            chunk_inserted = result.rowcount if result.rowcount >= 0 else len(chunk)
            inserted += chunk_inserted
        await db.commit()
    except Exception as e:
        logger.error(f"batch_upsert_events error: {e}")
        await db.rollback()
        return 0, skipped

    return inserted, skipped


async def get_candidate_events(
    db: AsyncSession,
    geographies: List[str],
    industries: List[str],
    date_from: Optional[str],
    date_to: Optional[str],
    min_attendees: int = 0,
    limit: int = 300,
) -> List[EventORM]:
    today     = date.today().isoformat()
    date_from = date_from or today
    date_to   = date_to or "2028-12-31"

    stmt = select(EventORM).where(
        EventORM.start_date >= date_from,
        EventORM.start_date <= date_to,
        EventORM.est_attendees >= min_attendees,
    )
    if geographies and "global" not in [g.lower() for g in geographies]:
        geo_filters = []
        for geo in geographies:
            geo_filters.append(EventORM.country.ilike(f"%{geo}%"))
            geo_filters.append(EventORM.city.ilike(f"%{geo}%"))
            geo_filters.append(EventORM.event_cities.ilike(f"%{geo}%"))
        stmt = stmt.where(or_(*geo_filters))

    if industries:
        industry_filters = []
        for industry in industries:
            industry_filters.append(EventORM.related_industries.ilike(f"%{industry}%"))
            industry_filters.append(EventORM.industry_tags.ilike(f"%{industry}%"))
            industry_filters.append(EventORM.category.ilike(f"%{industry}%"))
            industry_filters.append(EventORM.name.ilike(f"%{industry}%"))
            industry_filters.append(EventORM.description.ilike(f"%{industry}%"))
        stmt = stmt.where(or_(*industry_filters))

    result = await db.execute(stmt.limit(limit))
    return list(result.scalars().all())


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
    """
    Return {source_platform: event_count} for every source in the DB.
    Required by ingestion_manager.py — was missing, causing ImportError.
    """
    result = await db.execute(
        select(EventORM.source_platform, func.count(EventORM.id))
        .group_by(EventORM.source_platform)
        .order_by(func.count(EventORM.id).desc())
    )
    return {row[0]: row[1] for row in result.all()}


async def purge_past_events(db: AsyncSession, grace_days: int = 7) -> int:
    """
    Delete events whose end_date is older than grace_days.
    Seed events (source_platform='Seed') are NEVER purged.
    """
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


# ═══════════════════════════════════════════════════════════
# Company Profile CRUD
# ═══════════════════════════════════════════════════════════

async def create_company_profile(
    db: AsyncSession,
    data: CompanyProfileCreate,
    deck_text: str = "",
    deck_filename: str = "",
) -> CompanyProfileORM:
    profile = CompanyProfileORM(
        id=str(uuid.uuid4()),
        company_name=data.company_name,
        founded_year=data.founded_year,
        location=data.location,
        what_we_do=data.what_we_do,
        what_we_need=data.what_we_need,
        deck_text=deck_text[:8000],
        deck_filename=deck_filename,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
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
