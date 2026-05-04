from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func, or_
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from models.event import EventORM, EventCreate
from models.company_profile import CompanyProfileORM, CompanyProfileCreate
from datetime import datetime, date
from typing import List, Optional
import uuid
from loguru import logger


# ═══════════════════════════════════════════════════════════
# Event CRUD
# ═══════════════════════════════════════════════════════════

async def upsert_event(db: AsyncSession, event: EventCreate) -> bool:
    """Insert or ignore duplicate (by dedup_hash)."""
    try:
        stmt = sqlite_insert(EventORM).values(
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
        ).on_conflict_do_nothing(index_elements=["dedup_hash"])
        await db.execute(stmt)
        await db.commit()
        return True
    except Exception as e:
        logger.error(f"upsert_event error: {e}")
        await db.rollback()
        return False


async def get_candidate_events(
    db: AsyncSession,
    geographies: List[str],
    industries: List[str],
    date_from: Optional[str],
    date_to: Optional[str],
    min_attendees: int = 0,
    limit: int = 300,
) -> List[EventORM]:
    today = date.today().isoformat()
    date_from = date_from or today
    date_to = date_to or "2027-12-31"

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
        stmt = stmt.where(or_(*geo_filters))

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


async def purge_past_events(db: AsyncSession) -> int:
    cutoff = date.today().isoformat()
    result = await db.execute(
        delete(EventORM).where(EventORM.end_date < cutoff, EventORM.end_date != "")
    )
    await db.commit()
    return result.rowcount


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
        deck_text=deck_text[:8000],   # limit stored text
        deck_filename=deck_filename,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    logger.info(f"Company profile created: {profile.id}")
    return profile


async def get_company_profile(db: AsyncSession, profile_id: str) -> Optional[CompanyProfileORM]:
    result = await db.execute(
        select(CompanyProfileORM).where(CompanyProfileORM.id == profile_id)
    )
    return result.scalar_one_or_none()
