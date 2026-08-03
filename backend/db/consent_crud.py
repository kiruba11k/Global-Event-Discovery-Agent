"""
db/consent_crud.py — writes for models/consent.py (cookie banner,
contact/ICP form consent checkboxes, and bot-protection outcomes).
Mirrors the best-effort commit pattern in db/analytics_crud.py: consent
logging must never block or fail the request it's attached to.
"""
from __future__ import annotations

import uuid
from typing import List, Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from models.consent import BotProtectionEventORM, ConsentRecordORM


async def record_consent(
    db: AsyncSession, consent_type: str, accepted: bool, session_id: str = "",
    categories: Optional[List[str]] = None, ip_address: str = "", user_agent: str = "",
    policy_version: str = "1.0",
) -> ConsentRecordORM:
    row = ConsentRecordORM(
        id=str(uuid.uuid4()), session_id=session_id, consent_type=consent_type,
        accepted=accepted, categories=", ".join(categories or []),
        ip_address=ip_address, user_agent=user_agent[:500], policy_version=policy_version,
    )
    db.add(row)
    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.warning(f"record_consent failed (non-fatal): {exc}")
    return row


async def record_bot_protection_event(
    db: AsyncSession, session_id: str, ip_address: str, fingerprint: str,
    captcha_verified: bool, honeypot_triggered: bool, duplicate_detected: bool,
    outcome: str, submission_id: str = "",
) -> BotProtectionEventORM:
    row = BotProtectionEventORM(
        id=str(uuid.uuid4()), submission_id=submission_id, session_id=session_id,
        ip_address=ip_address, fingerprint=fingerprint, captcha_verified=captcha_verified,
        honeypot_triggered=honeypot_triggered, duplicate_detected=duplicate_detected,
        outcome=outcome,
    )
    db.add(row)
    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.warning(f"record_bot_protection_event failed (non-fatal): {exc}")
    return row
