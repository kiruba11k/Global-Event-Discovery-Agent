"""
models/analytics.py — dashboard/monitoring tables (sessions, ICP form
submissions, search results shown, generic activity stream).

Purpose-built to be queried by an external dashboard app (Kibana-style
slicing by date/industry/geography/status) via api/routes_analytics.py.
Shares Base with EventORM (models/event.py) so db.database.init_db()'s
`EventBase.metadata.create_all` picks these tables up automatically —
importing this module anywhere before init_db() runs is enough to
register them (see db/database.py's import list).

Common key: `session_id` (AnalyticsSessionORM.id) links a visitor to
every submission and event they generate; `submission_id`
(AnalyticsICPSubmissionORM.id) links a search to every result it
produced. Both are enforced with real ForeignKey constraints — NULL
when unknown (e.g. session tracking failed client-side), never an
empty string, so the constraint stays meaningful instead of silently
accepting orphaned "" values.

`event_id` (the catalog event referenced by AnalyticsSearchResultORM
and AnalyticsEventORM) is deliberately NOT a ForeignKey to events.id —
the live `events` table has no PRIMARY KEY/UNIQUE constraint on `id`
in production (only `dedup_hash` does), so Postgres rejects it as an
FK target outright; referencing it crashes table creation at app
startup. Join it at query time instead (events.id = analytics_*.event_id).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text

from models.event import Base


class AnalyticsSessionORM(Base):
    """One row per visitor session. session_id is generated client-side
    (frontend) and persisted in localStorage, so the same visitor keeps
    the same session_id across page reloads within a browser."""
    __tablename__ = "analytics_sessions"

    id                       = Column(String, primary_key=True)   # session_id
    device_id                = Column(String, index=True, default="")
    ip_address               = Column(String, default="")
    user_agent               = Column(Text, default="")
    referrer                 = Column(Text, default="")
    landing_page              = Column(Text, default="")

    first_seen_at             = Column(DateTime, default=datetime.utcnow, index=True)
    last_seen_at               = Column(DateTime, default=datetime.utcnow, index=True)
    total_time_spent_seconds  = Column(Integer, default=0)
    page_views                = Column(Integer, default=0)


class AnalyticsICPSubmissionORM(Base):
    """One row per ICP form submission — normalized columns (not just a
    JSON blob) so an external dashboard can filter/aggregate by
    industry, persona, geography, deal size, status, etc. directly in
    SQL without parsing JSON. Captures every field the ICP form
    actually collects (models/icp_profile.py's ICPProfile), not just a
    subset."""
    __tablename__ = "analytics_icp_submissions"

    id                    = Column(String, primary_key=True)
    session_id             = Column(String, ForeignKey("analytics_sessions.id"), nullable=True, index=True)

    submitted_at           = Column(DateTime, default=datetime.utcnow, index=True)
    completed_at           = Column(DateTime, nullable=True)
    latency_ms             = Column(Integer, default=0)
    status                  = Column(String, default="queued", index=True)  # queued|processing|done|error
    error                   = Column(Text, default="")

    ip_address              = Column(String, default="")
    company_name            = Column(String, default="")
    email                    = Column(String, default="", index=True)
    company_description      = Column(Text, default="")
    buyer_description        = Column(Text, default="")

    target_industries        = Column(Text, default="")   # comma-joined, for quick display
    target_personas          = Column(Text, default="")
    target_geographies       = Column(Text, default="")
    preferred_event_types    = Column(Text, default="")
    extra_keywords           = Column(Text, default="")

    deal_size_bracket        = Column(String, default="")
    budget_usd                = Column(Float, nullable=True)
    date_from                = Column(String, default="")
    date_to                  = Column(String, default="")
    min_attendees             = Column(Integer, default=0)
    max_results               = Column(Integer, default=30)

    # ── Meeting-potential calculator inputs ──────────────────────
    differentiator_score      = Column(Integer, default=5)     # 1-10 slider
    client_count_range        = Column(String, default="")     # "0-10"|"11-50"|...
    client_names              = Column(Text, default="")       # comma-joined — "Who are some of your clients?"

    total_found              = Column(Integer, default=0)
    go_count                 = Column(Integer, default=0)
    consider_count           = Column(Integer, default=0)


class AnalyticsSearchResultORM(Base):
    """One row per event actually shown to a user for a given
    submission — fixes the gap where results only ever lived in the
    ephemeral in-memory `_last_results` dict (routes_events.py),
    never durably persisted per-user."""
    __tablename__ = "analytics_search_results"

    id                = Column(String, primary_key=True)   # f"{submission_id}:{event_id}"
    submission_id      = Column(String, ForeignKey("analytics_icp_submissions.id"), nullable=False, index=True)
    # NOT a ForeignKey to events.id — the live events table's `id` column
    # has no PRIMARY KEY/UNIQUE constraint in production (only dedup_hash
    # does), so Postgres can't accept it as an FK target. Referencing it
    # anyway breaks table creation outright (InvalidForeignKeyError,
    # crashes app startup). Indexed String, enforced at the app layer.
    event_id           = Column(String, index=True, nullable=True)
    event_name         = Column(String, default="")        # denormalized, avoids a join for display
    rank_position       = Column(Integer, default=0)
    fit_verdict         = Column(String, default="")        # GO | CONSIDER | SKIP
    relevance_score     = Column(Float, default=0.0)
    shown_at            = Column(DateTime, default=datetime.utcnow, index=True)
    clicked              = Column(Boolean, default=False)


class AnalyticsEventORM(Base):
    """Generic append-only activity stream — one row per user action.
    Deliberately flexible (event_type + metadata_json) rather than one
    narrow table per action, so new event types don't need a schema
    migration; the dashboard app can filter/group by event_type like a
    Kibana index."""
    __tablename__ = "analytics_events"

    id             = Column(String, primary_key=True)
    session_id      = Column(String, ForeignKey("analytics_sessions.id"), nullable=True, index=True)
    event_type      = Column(String, index=True, default="")   # page_view | icp_form_submitted | results_viewed | result_clicked | email_report_requested | ...
    submission_id   = Column(String, ForeignKey("analytics_icp_submissions.id"), nullable=True, index=True)
    # NOT a ForeignKey — see the identical note on AnalyticsSearchResultORM.event_id above.
    event_id        = Column(String, index=True, nullable=True)   # catalog event, when relevant (e.g. result_clicked)
    metadata_json   = Column(Text, default="")
    created_at       = Column(DateTime, default=datetime.utcnow, index=True)
