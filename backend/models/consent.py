"""
models/consent.py — durable record of every consent a visitor has given
(cookie banner accept/reject, contact-form consent checkbox, ICP-form
consent checkbox), plus the CAPTCHA / bot-protection outcome for ICP
form submissions.

Kept as its own table (not folded into analytics_icp_submissions) since
cookie consent happens on page load, before any form exists — it needs
a home independent of a submission row.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, String, Text

from models.event import Base


class ConsentRecordORM(Base):
    """One row per consent action. `consent_type` distinguishes what was
    consented to: 'cookie_banner' | 'contact_form' | 'icp_form'."""
    __tablename__ = "consent_records"

    id             = Column(String, primary_key=True)
    session_id      = Column(String, index=True, default="")
    consent_type    = Column(String, index=True, default="")   # cookie_banner|contact_form|icp_form
    accepted        = Column(Boolean, default=False)           # True=accepted/consented, False=rejected/declined
    categories      = Column(Text, default="")                 # comma-joined, cookie banner only: "necessary,analytics,marketing"
    ip_address      = Column(String, default="")
    user_agent      = Column(Text, default="")
    policy_version  = Column(String, default="1.0")
    created_at      = Column(DateTime, default=datetime.utcnow, index=True)


class BotProtectionEventORM(Base):
    """One row per ICP-form submission attempt's bot-protection outcome —
    kept separate from analytics_icp_submissions so a rejected (never
    actually processed) submission is still recorded for monitoring."""
    __tablename__ = "bot_protection_events"

    id                  = Column(String, primary_key=True)
    submission_id        = Column(String, index=True, default="")  # set only if it passed through to a real submission
    session_id           = Column(String, index=True, default="")
    ip_address           = Column(String, default="")
    fingerprint           = Column(String, index=True, default="")
    captcha_verified      = Column(Boolean, default=False)
    honeypot_triggered    = Column(Boolean, default=False)
    duplicate_detected     = Column(Boolean, default=False)
    outcome               = Column(String, default="")   # allowed|blocked_honeypot|blocked_captcha|blocked_duplicate
    created_at            = Column(DateTime, default=datetime.utcnow, index=True)
