"""
models/search_submission.py — durable log of every ICP form submission.

Previously the ICP form data (company name, industries, personas,
geographies, deal size, etc.) that a user types into the search form
was never actually saved anywhere as a distinct record — only derived
signals (a profile hash + per-event feedback rows in `profile_feedback`,
see relevance/profile_store.py) were persisted, not the raw submission
itself. This table is the actual "here's what this user searched for,
and when" record.

Shares Base with EventORM (models/event.py) so db.database.init_db()'s
`EventBase.metadata.create_all` picks up this table automatically —
importing this module anywhere before init_db() runs is enough to
register it (see db/database.py's import list).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from models.event import Base


class SearchSubmissionORM(Base):
    __tablename__ = "search_submissions"

    id                  = Column(String, primary_key=True)

    # ── Who / when ───────────────────────────────────────────
    ip_address          = Column(String, index=True, default="")
    submitted_at         = Column(DateTime, default=datetime.utcnow, index=True)
    completed_at         = Column(DateTime, nullable=True)

    # ── The actual ICP form submission ──────────────────────
    # Full JSON dump of the ICPProfile the user submitted — every field,
    # not just the ones used for hashing/matching elsewhere.
    profile_json         = Column(Text, default="")
    company_name         = Column(String, default="")
    email                = Column(String, default="")
    company_profile_id   = Column(String, default="")

    # ── Job tracking (see queueing/search_queue.py) ─────────
    job_id                = Column(String, index=True, default="")
    status                = Column(String, default="queued")   # queued|processing|done|error
    result_total_found   = Column(Integer, default=0)
    error                 = Column(Text, default="")
