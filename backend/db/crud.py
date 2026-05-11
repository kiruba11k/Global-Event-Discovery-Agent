"""
CRUD helpers — dialect-aware upsert for SQLite (dev) and PostgreSQL (prod).

Key changes vs previous version:
  - _dialect_insert() detects the configured database and returns the right
    SQLAlchemy dialect insert (sqlite or postgresql).  Both dialects support
    .on_conflict_do_nothing(index_elements=["dedup_hash"]) identically.
  - Removed the hard import of sqlalchemy.dialects.sqlite.insert so the same
    code works against Neon / Supabase / any PostgreSQL without changes.
  - rowcount semantics are identical for both dialects:
      0  → conflict (duplicate ignored)
      N  → N rows actually inserted
     -1  → driver doesn't report (treat as inserted)
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func, or_
from models.event import EventORM, EventCreate
from models.company_profile import CompanyProfileORM, CompanyProfileCreate
from datetime import datetime, date, timedelta
from typing import List, Optional, Tuple
import uuid
from loguru import logger


# ── Dialect-aware insert helper ────────────────────────────────────

def _dialect_insert(orm_class):
    """
    Return an INSERT statement object for the correct SQL dialect.

    SQLite  → sqlalchemy.dialects.sqlite.insert
    Postgres→ sqlalchemy.dialects.postgresql.insert

    Both expose the same .on_conflict_do_nothing() API, so callers
    don't need to know which dialect is active.
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
    """
    Insert event or silently skip if dedup_hash already exists.
    Returns True  → row was actually inserted (new event).
    Returns False → conflict ignored (duplicate) or error.
    """
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

        # rowcount == 1  → inserted
        # rowcount == 0  → conflict ignored (duplicate)
        # rowcount == -1 → driver doesn't report → assume inserted
        inserted = result.rowcount != 0
        return inserted

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
    Upsert a list of events in a single transaction.
    Much faster than calling upsert_event() in a loop.

    Args:
        skip_past: if True, silently drop events whose start_date < today.

    Returns:
        (inserted_count, skipped_count)
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
        # Insert in chunks of 500 to stay within SQLite / PG parameter limits
        chunk_size = 500
        for i in range(0, len(rows), chunk_size):
            chunk = rows[i : i + chunk_size]
            stmt  = (
                _dialect_insert(EventORM)
                .values(chunk)
                .on_conflict_do_nothing(index_elements=["dedup_hash"])
            )
            result = await db.execute(stmt)
            # rowcount for bulk insert = number of rows actually inserted
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


async def purge_past_events(db: AsyncSession, grace_days: int = 7) -> int:
    """
    Delete events whose end_date is older than `grace_days` days ago.
    Seed events (source_platform='Seed') are NEVER purged — guaranteed baseline.
    Events with empty/null end_date are NEVER purged (can't know if passed).
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
        logger.info(f"Purged {purged} events that ended before {cutoff}.")
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
