"""
db/analytics_crud.py — writes/reads for the dashboard/monitoring tables
(models/analytics.py). Kept separate from db/crud.py (the events/search
domain) since this is a distinct concern: activity tracking for an
external dashboard, not the search pipeline itself.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.analytics import (
    AnalyticsEventORM, AnalyticsICPSubmissionORM,
    AnalyticsSearchResultORM, AnalyticsSessionORM,
)

# ── Sessions ─────────────────────────────────────────────────────────

async def start_session(
    db: AsyncSession, session_id: str, device_id: str = "", ip_address: str = "",
    user_agent: str = "", referrer: str = "", landing_page: str = "",
) -> AnalyticsSessionORM:
    existing = await db.get(AnalyticsSessionORM, session_id)
    if existing:
        existing.last_seen_at = datetime.utcnow()
        existing.page_views = (existing.page_views or 0) + 1
        await db.commit()
        return existing
    row = AnalyticsSessionORM(
        id=session_id, device_id=device_id, ip_address=ip_address,
        user_agent=user_agent[:500], referrer=referrer[:500], landing_page=landing_page[:500],
        page_views=1,
    )
    db.add(row)
    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.debug(f"start_session commit failed (non-fatal): {exc}")
    return row


async def touch_session(db: AsyncSession, session_id: str, delta_seconds: int = 0) -> bool:
    """Heartbeat — frontend calls this periodically while the tab is
    visible, reporting elapsed seconds since the last heartbeat."""
    row = await db.get(AnalyticsSessionORM, session_id)
    if not row:
        return False
    row.last_seen_at = datetime.utcnow()
    row.total_time_spent_seconds = (row.total_time_spent_seconds or 0) + max(0, int(delta_seconds))
    await db.commit()
    return True


# ── Generic event stream ──────────────────────────────────────────────

async def log_event(
    db: AsyncSession, session_id: str, event_type: str,
    submission_id: str = "", event_id: str = "", metadata: Optional[dict] = None,
) -> AnalyticsEventORM:
    row = AnalyticsEventORM(
        id=str(uuid.uuid4()), session_id=session_id, event_type=event_type,
        submission_id=submission_id, event_id=event_id,
        metadata_json=json.dumps(metadata or {})[:4000],
    )
    db.add(row)
    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.debug(f"log_event commit failed (non-fatal): {exc}")
    return row


# ── ICP submissions ────────────────────────────────────────────────────

async def create_icp_submission(
    db: AsyncSession, submission_id: str, session_id: str, ip_address: str,
    company_name: str, email: str, target_industries: List[str],
    target_personas: List[str], target_geographies: List[str],
    deal_size_bracket: str, date_from: str, date_to: str,
) -> AnalyticsICPSubmissionORM:
    row = AnalyticsICPSubmissionORM(
        id=submission_id, session_id=session_id, ip_address=ip_address,
        company_name=company_name, email=email,
        target_industries=", ".join(target_industries or []),
        target_personas=", ".join(target_personas or []),
        target_geographies=", ".join(target_geographies or []),
        deal_size_bracket=deal_size_bracket or "", date_from=date_from or "", date_to=date_to or "",
    )
    db.add(row)
    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.warning(f"create_icp_submission failed (non-fatal): {exc}")
    return row


async def complete_icp_submission(
    db: AsyncSession, submission_id: str, status: str, total_found: int = 0,
    go_count: int = 0, consider_count: int = 0, error: str = "",
) -> bool:
    row = await db.get(AnalyticsICPSubmissionORM, submission_id)
    if not row:
        return False
    now = datetime.utcnow()
    row.completed_at = now
    row.status = status
    row.total_found = total_found
    row.go_count = go_count
    row.consider_count = consider_count
    row.error = error[:2000]
    if row.submitted_at:
        row.latency_ms = int((now - row.submitted_at).total_seconds() * 1000)
    await db.commit()
    return True


# ── Results shown ──────────────────────────────────────────────────────

async def record_shown_results(db: AsyncSession, submission_id: str, events: List[dict]) -> int:
    """`events` — list of dicts with id/event_name/fit_verdict/relevance_score,
    in the order actually shown to the user (rank_position = list index)."""
    if not events:
        return 0
    rows = [
        AnalyticsSearchResultORM(
            id=f"{submission_id}:{e.get('id','')}",
            submission_id=submission_id,
            event_id=e.get("id", ""),
            event_name=(e.get("event_name") or e.get("name") or "")[:300],
            rank_position=i,
            fit_verdict=e.get("fit_verdict", ""),
            relevance_score=float(e.get("relevance_score") or 0.0),
        )
        for i, e in enumerate(events)
    ]
    db.add_all(rows)
    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.debug(f"record_shown_results failed (non-fatal): {exc}")
        return 0
    return len(rows)


async def mark_result_clicked(db: AsyncSession, submission_id: str, event_id: str) -> bool:
    row = await db.get(AnalyticsSearchResultORM, f"{submission_id}:{event_id}")
    if not row:
        return False
    row.clicked = True
    await db.commit()
    return True


# ── Dashboard reads ────────────────────────────────────────────────────

def _date_range(stmt, column, date_from: Optional[str], date_to: Optional[str]):
    if date_from:
        stmt = stmt.where(column >= date_from)
    if date_to:
        stmt = stmt.where(column <= date_to + " 23:59:59")
    return stmt


async def list_sessions(db: AsyncSession, page: int = 1, limit: int = 50,
                         date_from: str = "", date_to: str = "") -> Dict:
    stmt = select(AnalyticsSessionORM).order_by(AnalyticsSessionORM.last_seen_at.desc())
    stmt = _date_range(stmt, AnalyticsSessionORM.first_seen_at, date_from, date_to)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    rows = (await db.execute(stmt.offset((page - 1) * limit).limit(limit))).scalars().all()
    return {"total": total, "page": page, "limit": limit, "sessions": [
        {"id": r.id, "device_id": r.device_id, "ip_address": r.ip_address,
         "referrer": r.referrer, "first_seen_at": r.first_seen_at.isoformat() if r.first_seen_at else None,
         "last_seen_at": r.last_seen_at.isoformat() if r.last_seen_at else None,
         "total_time_spent_seconds": r.total_time_spent_seconds, "page_views": r.page_views}
        for r in rows
    ]}


async def list_icp_submissions(db: AsyncSession, page: int = 1, limit: int = 50,
                                status: str = "", date_from: str = "", date_to: str = "") -> Dict:
    stmt = select(AnalyticsICPSubmissionORM).order_by(AnalyticsICPSubmissionORM.submitted_at.desc())
    if status:
        stmt = stmt.where(AnalyticsICPSubmissionORM.status == status)
    stmt = _date_range(stmt, AnalyticsICPSubmissionORM.submitted_at, date_from, date_to)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    rows = (await db.execute(stmt.offset((page - 1) * limit).limit(limit))).scalars().all()
    return {"total": total, "page": page, "limit": limit, "submissions": [
        {"id": r.id, "session_id": r.session_id, "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
         "completed_at": r.completed_at.isoformat() if r.completed_at else None, "latency_ms": r.latency_ms,
         "status": r.status, "company_name": r.company_name, "email": r.email,
         "target_industries": r.target_industries, "target_personas": r.target_personas,
         "target_geographies": r.target_geographies, "deal_size_bracket": r.deal_size_bracket,
         "total_found": r.total_found, "go_count": r.go_count, "consider_count": r.consider_count,
         "error": r.error}
        for r in rows
    ]}


async def list_search_results(db: AsyncSession, submission_id: str) -> List[Dict]:
    rows = (await db.execute(
        select(AnalyticsSearchResultORM)
        .where(AnalyticsSearchResultORM.submission_id == submission_id)
        .order_by(AnalyticsSearchResultORM.rank_position.asc())
    )).scalars().all()
    return [
        {"event_id": r.event_id, "event_name": r.event_name, "rank_position": r.rank_position,
         "fit_verdict": r.fit_verdict, "relevance_score": r.relevance_score,
         "shown_at": r.shown_at.isoformat() if r.shown_at else None, "clicked": r.clicked}
        for r in rows
    ]


async def list_events(db: AsyncSession, page: int = 1, limit: int = 50,
                       event_type: str = "", date_from: str = "", date_to: str = "") -> Dict:
    stmt = select(AnalyticsEventORM).order_by(AnalyticsEventORM.created_at.desc())
    if event_type:
        stmt = stmt.where(AnalyticsEventORM.event_type == event_type)
    stmt = _date_range(stmt, AnalyticsEventORM.created_at, date_from, date_to)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    rows = (await db.execute(stmt.offset((page - 1) * limit).limit(limit))).scalars().all()
    return {"total": total, "page": page, "limit": limit, "events": [
        {"id": r.id, "session_id": r.session_id, "event_type": r.event_type,
         "submission_id": r.submission_id, "event_id": r.event_id,
         "metadata": json.loads(r.metadata_json) if r.metadata_json else {},
         "created_at": r.created_at.isoformat() if r.created_at else None}
        for r in rows
    ]}


async def get_summary(db: AsyncSession, date_from: str = "", date_to: str = "") -> Dict:
    sess_stmt = _date_range(select(AnalyticsSessionORM), AnalyticsSessionORM.first_seen_at, date_from, date_to)
    sub_stmt  = _date_range(select(AnalyticsICPSubmissionORM), AnalyticsICPSubmissionORM.submitted_at, date_from, date_to)

    total_sessions = (await db.execute(select(func.count()).select_from(sess_stmt.subquery()))).scalar() or 0
    avg_time = (await db.execute(select(func.avg(AnalyticsSessionORM.total_time_spent_seconds)).select_from(sess_stmt.subquery()))).scalar() or 0
    total_page_views = (await db.execute(select(func.sum(AnalyticsSessionORM.page_views)).select_from(sess_stmt.subquery()))).scalar() or 0

    total_submissions = (await db.execute(select(func.count()).select_from(sub_stmt.subquery()))).scalar() or 0
    status_rows = (await db.execute(
        sub_stmt.with_only_columns(AnalyticsICPSubmissionORM.status)
    )).all()
    by_status: Dict[str, int] = {}
    for (status,) in status_rows:
        by_status[status] = by_status.get(status, 0) + 1

    go_total = (await db.execute(select(func.sum(AnalyticsICPSubmissionORM.go_count)).select_from(sub_stmt.subquery()))).scalar() or 0
    consider_total = (await db.execute(select(func.sum(AnalyticsICPSubmissionORM.consider_count)).select_from(sub_stmt.subquery()))).scalar() or 0

    email_stmt = _date_range(
        select(func.count()).select_from(AnalyticsEventORM)
        .where(AnalyticsEventORM.event_type == "email_report_requested"),
        AnalyticsEventORM.created_at, date_from, date_to,
    )
    email_requests = (await db.execute(email_stmt)).scalar() or 0

    return {
        "date_from": date_from, "date_to": date_to,
        "total_sessions": total_sessions,
        "avg_time_spent_seconds": round(float(avg_time or 0), 1),
        "total_page_views": int(total_page_views or 0),
        "total_icp_submissions": total_submissions,
        "submissions_by_status": by_status,
        "total_go_results": int(go_total or 0),
        "total_consider_results": int(consider_total or 0),
        "email_report_requests": email_requests,
    }
