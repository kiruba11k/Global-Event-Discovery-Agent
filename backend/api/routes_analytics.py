"""
api/routes_analytics.py — user/session tracking (write) + dashboard
read API for an external monitoring app (Kibana-style: filter/aggregate
by date, event_type, industry, geography, status, etc.).

Write endpoints (session/*, /event) are called by the frontend and are
intentionally unauthenticated — same trust boundary as the rest of the
public API. Read endpoints expose aggregate + per-user activity data
(emails, IPs) and are gated behind ANALYTICS_API_TOKEN.
"""
from __future__ import annotations

import csv
import io
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from db import analytics_crud as crud
from db.database import get_db

router = APIRouter()
settings = get_settings()


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "")


def _require_analytics_token(x_analytics_token: str = Header(default="")):
    """Dashboard read endpoints are gated behind a shared token — this
    data includes emails/IPs and shouldn't be publicly queryable. If no
    token is configured, access is left open (matches this app's other
    optional-auth admin patterns) — set ANALYTICS_API_TOKEN to lock it
    down before pointing an external dashboard at this API."""
    if settings.analytics_api_token and x_analytics_token != settings.analytics_api_token:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Analytics-Token")


# ══════════════════════════════════════════════════════════════════════
# Write — called by the frontend
# ══════════════════════════════════════════════════════════════════════

class SessionStartBody(BaseModel):
    session_id: str = ""
    device_id: str = ""
    referrer: str = ""
    landing_page: str = ""


@router.post("/analytics/session/start")
async def session_start(body: SessionStartBody, request: Request, db: AsyncSession = Depends(get_db)):
    session_id = body.session_id or str(uuid.uuid4())
    await crud.start_session(
        db, session_id, device_id=body.device_id, ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent", ""), referrer=body.referrer,
        landing_page=body.landing_page,
    )
    return {"session_id": session_id}


class HeartbeatBody(BaseModel):
    session_id: str
    delta_seconds: int = 0


@router.post("/analytics/session/heartbeat")
async def session_heartbeat(body: HeartbeatBody, db: AsyncSession = Depends(get_db)):
    ok = await crud.touch_session(db, body.session_id, body.delta_seconds)
    return {"ok": ok}


class EventBody(BaseModel):
    session_id: str
    event_type: str
    submission_id: str = ""
    event_id: str = ""
    metadata: dict = {}


@router.post("/analytics/event")
async def track_event(body: EventBody, db: AsyncSession = Depends(get_db)):
    row = await crud.log_event(
        db, body.session_id, body.event_type,
        submission_id=body.submission_id, event_id=body.event_id, metadata=body.metadata,
    )
    if body.event_type == "result_clicked" and body.submission_id and body.event_id:
        await crud.mark_result_clicked(db, body.submission_id, body.event_id)
    return {"id": row.id}


# ══════════════════════════════════════════════════════════════════════
# Read — for the external dashboard app (token-gated)
# ══════════════════════════════════════════════════════════════════════

@router.get("/analytics/summary", dependencies=[Depends(_require_analytics_token)])
async def summary(date_from: str = Query(""), date_to: str = Query(""), db: AsyncSession = Depends(get_db)):
    return await crud.get_summary(db, date_from, date_to)


@router.get("/analytics/sessions", dependencies=[Depends(_require_analytics_token)])
async def sessions(page: int = Query(1, ge=1), limit: int = Query(50, ge=1, le=200),
                    date_from: str = Query(""), date_to: str = Query(""),
                    db: AsyncSession = Depends(get_db)):
    return await crud.list_sessions(db, page, limit, date_from, date_to)


@router.get("/analytics/icp-submissions", dependencies=[Depends(_require_analytics_token)])
async def icp_submissions(page: int = Query(1, ge=1), limit: int = Query(50, ge=1, le=200),
                           status: str = Query(""), date_from: str = Query(""), date_to: str = Query(""),
                           db: AsyncSession = Depends(get_db)):
    return await crud.list_icp_submissions(db, page, limit, status, date_from, date_to)


# ══════════════════════════════════════════════════════════════════════
# GET /api/analytics/icp-submissions/export — CSV lead list
#
# The dashboard-facing JSON endpoint above is paginated and trimmed for
# UI display; this is the "give me every lead as a spreadsheet" export
# a sales team actually works from (open in Excel/Sheets, import to a
# CRM). Same ANALYTICS_API_TOKEN gate — this is real PII (names, emails,
# buyer descriptions), not aggregate data.
# ══════════════════════════════════════════════════════════════════════

_EXPORT_COLUMNS = [
    "submitted_at", "status", "company_name", "email",
    "target_industries", "target_personas", "target_geographies",
    "preferred_event_types", "extra_keywords", "buyer_description",
    "deal_size_bracket", "budget_usd", "date_from", "date_to",
    "min_attendees", "differentiator_score", "client_count_range", "client_names",
    "total_found", "go_count", "consider_count",
    "captcha_verified", "consent_given", "ip_address", "session_id", "id",
]


@router.get("/analytics/icp-submissions/export", dependencies=[Depends(_require_analytics_token)])
async def icp_submissions_export(status: str = Query(""), date_from: str = Query(""), date_to: str = Query(""),
                                  db: AsyncSession = Depends(get_db)):
    rows = await crud.list_icp_submissions_for_export(db, status, date_from, date_to)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(_EXPORT_COLUMNS)
    for r in rows:
        writer.writerow([
            r.submitted_at.isoformat() if r.submitted_at else "",
            r.status, r.company_name, r.email,
            r.target_industries, r.target_personas, r.target_geographies,
            r.preferred_event_types, r.extra_keywords, r.buyer_description,
            r.deal_size_bracket, r.budget_usd, r.date_from, r.date_to,
            r.min_attendees, r.differentiator_score, r.client_count_range, r.client_names,
            r.total_found, r.go_count, r.consider_count,
            r.captcha_verified, r.consent_given, r.ip_address, r.session_id, r.id,
        ])
    buf.seek(0)

    filename = f"icp-leads-{date_from or 'all'}-to-{date_to or 'all'}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/analytics/search-results", dependencies=[Depends(_require_analytics_token)])
async def search_results(submission_id: str = Query(...), db: AsyncSession = Depends(get_db)):
    return {"submission_id": submission_id, "results": await crud.list_search_results(db, submission_id)}


@router.get("/analytics/events", dependencies=[Depends(_require_analytics_token)])
async def events(page: int = Query(1, ge=1), limit: int = Query(50, ge=1, le=200),
                  event_type: str = Query(""), date_from: str = Query(""), date_to: str = Query(""),
                  db: AsyncSession = Depends(get_db)):
    return await crud.list_events(db, page, limit, event_type, date_from, date_to)
