"""
db/crud.py — fixed for actual Neon DB schema.

Critical fix:
  est_attendees = 0 in the DB means UNKNOWN attendance, NOT "0 attendees".
  The old filter  EventORM.est_attendees >= min_attendees  excluded ALL events
  because every EventsEye event has est_attendees=0.

  Fix: always include events where est_attendees=0 (unknown), regardless of
  the min_attendees filter.  Only filter out events where attendance is known
  AND below the threshold.
"""
import os
from datetime import datetime, date, timedelta
from typing import List, Optional, Tuple
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func, or_
from loguru import logger

from models.event import EventORM, EventCreate
from models.company_profile import CompanyProfileORM, CompanyProfileCreate


# ── Dialect-aware INSERT ───────────────────────────────────
def _insert(model):
    url = os.environ.get("DATABASE_URL", "sqlite")
    if "postgresql" in url or "postgres" in url:
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    return insert(model)


# ═══════════════════════════════════════════════════════════
# Event CRUD
# ═══════════════════════════════════════════════════════════

async def upsert_event(db: AsyncSession, event: EventCreate) -> bool:
    try:
        stmt = (
            _insert(EventORM)
            .values(
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
                # new columns — use getattr for backward compat
                event_venues    =getattr(event, "event_venues",     "") or "",
                event_cities    =getattr(event, "event_cities",     "") or "",
                related_industries=getattr(event, "related_industries", "") or "",
                website         =getattr(event, "website",          "") or "",
                organizer       =getattr(event, "organizer",        "") or "",
                audience_personas=event.audience_personas or "",
                ticket_price_usd=event.ticket_price_usd or 0.0,
                price_description=event.price_description or "",
                registration_url=event.registration_url or "",
                sponsors=event.sponsors or "",
                speakers_url=event.speakers_url or "",
                agenda_url=event.agenda_url or "",
                ingested_at=datetime.utcnow(),
                last_verified_at=datetime.utcnow(),
            )
            .on_conflict_do_nothing(index_elements=["dedup_hash"])
        )
        result = await db.execute(stmt)
        await db.commit()
        return result.rowcount != 0
    except Exception as e:
        logger.error(f"upsert_event [{event.name[:40]}]: {e}")
        await db.rollback()
        return False


async def batch_upsert_events(
    db: AsyncSession,
    events: List[EventCreate],
    skip_past: bool = True,
) -> Tuple[int, int]:
    if not events:
        return 0, 0

    today    = date.today().isoformat()
    inserted = 0
    skipped  = 0
    rows     = []

    for ev in events:
        if skip_past and ev.start_date and ev.start_date < today:
            skipped += 1
            continue
        if not ev.start_date:
            skipped += 1
            continue
        rows.append(dict(
            id=ev.id,
            source_platform=ev.source_platform,
            source_url=ev.source_url or "",
            dedup_hash=ev.dedup_hash,
            name=ev.name,
            description=ev.description or "",
            short_summary=ev.short_summary or "",
            edition_number=ev.edition_number or "",
            start_date=ev.start_date,
            end_date=ev.end_date or ev.start_date,
            duration_days=ev.duration_days or 1,
            venue_name=ev.venue_name or "",
            address=ev.address or "",
            city=ev.city or "",
            country=ev.country or "",
            is_virtual=ev.is_virtual or False,
            is_hybrid=ev.is_hybrid or False,
            est_attendees=ev.est_attendees or 0,
            category=ev.category or "",
            industry_tags=ev.industry_tags or "",
            event_venues    =getattr(ev, "event_venues",     "") or "",
            event_cities    =getattr(ev, "event_cities",     "") or "",
            related_industries=getattr(ev, "related_industries", "") or "",
            website         =getattr(ev, "website",          "") or "",
            organizer       =getattr(ev, "organizer",        "") or "",
            audience_personas=ev.audience_personas or "",
            ticket_price_usd=ev.ticket_price_usd or 0.0,
            price_description=ev.price_description or "",
            registration_url=ev.registration_url or "",
            sponsors=ev.sponsors or "",
            speakers_url=ev.speakers_url or "",
            agenda_url=ev.agenda_url or "",
            ingested_at=datetime.utcnow(),
            last_verified_at=datetime.utcnow(),
        ))

    if not rows:
        return 0, skipped

    for i in range(0, len(rows), 200):
        chunk = rows[i: i + 200]
        try:
            stmt   = _insert(EventORM).values(chunk).on_conflict_do_nothing(index_elements=["dedup_hash"])
            result = await db.execute(stmt)
            await db.commit()
            inserted += max(result.rowcount, 0)
        except Exception as e:
            logger.error(f"batch_upsert chunk error: {e}")
            await db.rollback()

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
    date_to   = date_to   or "2028-12-31"

    filters = [
        EventORM.start_date >= date_from,
        EventORM.start_date <= date_to,
    ]

    # ── Attendees filter — FIXED ──────────────────────────
    # est_attendees=0 means UNKNOWN (not "zero attendees").
    # Never exclude events just because attendance isn't recorded.
    # Only filter out events where attendance IS known AND below threshold.
    if min_attendees and min_attendees > 0:
        filters.append(
            or_(
                EventORM.est_attendees == 0,           # unknown → always include
                EventORM.est_attendees >= min_attendees # known and meets threshold
            )
        )

    # ── Geography filter ──────────────────────────────────
    geo_lower = [g.lower() for g in (geographies or [])]
    is_global = any(g in ("global", "worldwide", "international", "any") for g in geo_lower)

    if geographies and not is_global:
        geo_filters = []
        for geo in geographies:
            geo_filters.append(EventORM.country.ilike(f"%{geo}%"))
            geo_filters.append(EventORM.city.ilike(f"%{geo}%"))
        filters.append(or_(*geo_filters))

    stmt   = select(EventORM).where(*filters).limit(limit)
    result = await db.execute(stmt)
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


async def count_by_source(db: AsyncSession) -> dict:
    result = await db.execute(
        select(EventORM.source_platform, func.count(EventORM.id))
        .group_by(EventORM.source_platform)
        .order_by(func.count(EventORM.id).desc())
    )
    return {row[0]: row[1] for row in result.fetchall()}


async def purge_past_events(db: AsyncSession, grace_days: int = 30) -> int:
    cutoff    = (date.today() - timedelta(days=grace_days)).isoformat()
    today_iso = date.today().isoformat()
    result    = await db.execute(
        delete(EventORM).where(
            EventORM.end_date.isnot(None),
            EventORM.end_date != "",
            EventORM.end_date < cutoff,
            EventORM.start_date < today_iso,
            EventORM.source_platform != "Seed",
        )
    )
    await db.commit()
    purged = result.rowcount
    if purged:
        logger.info(f"Purged {purged} past events (ended before {cutoff}).")
    return purged


# ═══════════════════════════════════════════════════════════
# Company Profile CRUD
# ═══════════════════════════════════════════════════════════

async def create_company_profile(
    db: AsyncSession, data: CompanyProfileCreate,
    deck_text: str = "", deck_filename: str = "",
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
    return profile


async def get_company_profile(db: AsyncSession, profile_id: str) -> Optional[CompanyProfileORM]:
    result = await db.execute(
        select(CompanyProfileORM).where(CompanyProfileORM.id == profile_id)
    )
    return result.scalar_one_or_none()
