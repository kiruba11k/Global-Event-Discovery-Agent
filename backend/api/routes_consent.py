"""
api/routes_consent.py — records cookie-banner choices and form consent
checkboxes (contact form, ICP form) to the DB. Unauthenticated, same
trust boundary as api/routes_analytics.py's write endpoints — this is a
public site collecting its own visitors' consent, not sensitive data.
"""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from db import consent_crud as crud
from db.database import get_db

router = APIRouter()


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "")


class ConsentBody(BaseModel):
    consent_type:    str            # "cookie_banner" | "contact_form" | "icp_form"
    accepted:        bool
    session_id:      str = ""
    categories:      List[str] = []  # cookie banner only: which categories were accepted
    policy_version:  str = "1.0"


@router.post("/consent")
async def submit_consent(body: ConsentBody, request: Request, db: AsyncSession = Depends(get_db)):
    session_id = body.session_id or request.headers.get("x-session-id", "")
    row = await crud.record_consent(
        db, consent_type=body.consent_type, accepted=body.accepted, session_id=session_id,
        categories=body.categories, ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent", ""), policy_version=body.policy_version,
    )
    return {"status": "recorded", "id": row.id}
