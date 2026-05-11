"""
CRUD helpers — v3 (portable + safe purge).

Key fixes:
  1. Dialect-aware INSERT OR IGNORE — works for both SQLite and PostgreSQL
  2. purge_past_events: only deletes events that ended 30+ days ago
     AND whose start_date is also in the past (prevents deleting
     events with bad end_date but valid future start_date)
  3. Seed events (source_platform='Seed') are NEVER purged
  4. batch_upsert_events: chunks of 200 rows, committed per-chunk
     so partial progress is saved even if an error occurs mid-batch
"""
import os
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func, or_, text
from datetime import datetime, date, timedelta
from typing import List, Optional, Tuple
import uuid
from loguru import logger

from models.event import EventORM, EventCreate
from models.company_profile import CompanyProfileORM, CompanyProfileCreate


# ── Dialect detection ──────────────────────────────────────────────────────────

def _is_sqlite() -> bool:
    db_url = os.environ.get("DATABASE_URL", "sqlite")
    return "sqlite" in db_url


def _make_insert(model):
    """Return the dialect-correct INSERT statement factory."""
    if _is_sqlite():
        from sqlalchemy.dialects.sqlite import insert
    else:
        from sqlalchemy.dialects.postgresql import insert
    return insert(model)


# ═══════════════════════════════════════════════════════════
# Event CRUD
# ═══════════════════════════════════════════════════════════

async def upsert_event(db: AsyncSession, event: EventCreate) -> bool:
    """
    Insert one event; silently skip if dedup_hash already exists.
    Returns True if actually inserted, False if duplicate or error.
    """
    try:
        stmt = (
            _make_insert(EventORM)
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
    Bulk upsert with per-chunk commits so partial progress is never lost.

    Args:
        skip_past: skip events whose start_date < today (default True)

    Returns:
        (inserted_count, skipped_count)
    """
    if not events:
        return 0, 0

    today    = date.today().isoformat()
    inserted = 0
    skipped  = 0

    # Build list of row dicts, filtering as we go
    rows = []
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
            source_url=event.source_url or "",
            dedup_hash=event.dedup_hash,
            name=event.name,
            description=event.description or "",
            short_summary=event.short_summary or "",
            edition_number=event.edition_number or "",
            start_date=event.start_date,
            end_date=event.end_date or event.start_date,
            duration_days=event.duration_days or 1,
            venue_name=event.venue_name or "",
            address=event.address or "",
            city=event.city or "",
            country=event.country or "",
            is_virtual=event.is_virtual or False,
            is_hybrid=event.is_hybrid or False,
            est_attendees=event.est_attendees or 0,
            category=event.category or "",
            industry_tags=event.industry_tags or "",
            audience_personas=event.audience_personas or "",
            ticket_price_usd=event.ticket_price_usd or 0.0,
            price_description=event.price_description or "",
            registration_url=event.registration_url or "",
            sponsors=event.sponsors or "",
            speakers_url=event.speakers_url or "",
            agenda_url=event.agenda_url or "",
            ingested_at=datetime.utcnow(),
            last_verified_at=datetime.utcnow(),
        ))

    if not rows:
        return 0, skipped

    # Insert in chunks of 200 — commit each chunk independently
    # so a failure on chunk 3 doesn't lose chunks 1 and 2
    chunk_size = 200
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i : i + chunk_size]
        try:
            stmt = (
                _make_insert(EventORM)
                .values(chunk)
                .on_conflict_do_nothing(index_elements=["dedup_hash"])
            )
            result = await db.execute(stmt)
            await db.commit()
            # rowcount = rows actually inserted (0 = all duplicates, -1 = unknown)
            chunk_ins = max(result.rowcount, 0)
            inserted += chunk_ins
        except Exception as e:
            logger.error(f"batch_upsert chunk {i//chunk_size + 1} error: {e}")
            await db.rollback()
            # Continue with next chunk — don't abort the whole batch

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
    result = await db.execute(
        select(EventORM).where(EventORM.id == event_id)
    )
    return result.scalar_one_or_none()


async def count_events(db: AsyncSession) -> int:
    result = await db.execute(select(func.count(EventORM.id)))
    return result.scalar() or 0


async def purge_past_events(db: AsyncSession, grace_days: int = 30) -> int:
    """
    Safely delete events that are clearly in the past.

    Rules (ALL must be true to delete):
      1. end_date is set (not empty/null)
      2. end_date < (today - grace_days)   ← 30 days grace, not 7
      3. start_date < today                ← start must also be past
      4. source_platform != 'Seed'         ← never delete seed events

    This means:
      - Events with future start_date are NEVER deleted even if end_date is wrong
      - Events from the last 30 days are kept even if technically ended
      - Seed events are permanent
    """
    cutoff      = (date.today() - timedelta(days=grace_days)).isoformat()
    today_iso   = date.today().isoformat()

    result = await db.execute(
        delete(EventORM).where(
            EventORM.end_date.isnot(None),
            EventORM.end_date != "",
            EventORM.end_date < cutoff,           # ended 30+ days ago
            EventORM.start_date < today_iso,       # started in the past too
            EventORM.source_platform != "Seed",    # never delete seed
        )
    )
    await db.commit()
    purged = result.rowcount
    if purged:
        logger.info(f"Purged {purged} events that ended before {cutoff}.")
    return purged


async def count_by_source(db: AsyncSession) -> dict:
    """Return event counts grouped by source_platform — useful for diagnostics."""
    from sqlalchemy import func as sqlfunc
    result = await db.execute(
        select(EventORM.source_platform, sqlfunc.count(EventORM.id))
        .group_by(EventORM.source_platform)
        .order_by(sqlfunc.count(EventORM.id).desc())
    )
    return {row[0]: row[1] for row in result.fetchall()}


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
    db: AsyncSession,
    profile_id: str,
) -> Optional[CompanyProfileORM]:
    result = await db.execute(
        select(CompanyProfileORM).where(CompanyProfileORM.id == profile_id)
    )
    return result.scalar_one_or_none()
