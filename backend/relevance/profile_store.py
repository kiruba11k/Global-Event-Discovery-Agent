"""
relevance/profile_store.py  —  Profile vector store + instant recall

PROBLEM this solves:
  Every search hits the API + DB cold. "fintech CFO Singapore" has been
  searched 40 times but the agent has no memory of which events converted.

SOLUTION:
  1. Hash each incoming ICP profile into a stable `profile_hash`
  2. Store (profile_hash, event_id, fit_score, user_action) in `profile_feedback`
  3. On new search: find similar profiles → pre-boost known high-converting events
     → full pipeline runs but starts with better prior knowledge

SMART EXPIRY — the key design challenge:
  A cached hit for "fintech CFO Singapore 2024" is useless in 2026.
  A hit for "fintech CFO Singapore, deal=$50K" is wrong for "$500K deal".
  But a hit for "fintech CFO any-date" from 3 months ago is very useful.

  We handle this with a TWO-PART hash:
  ─────────────────────────────────────────────────────────────────
  Part A — profile_core_hash (stable signals, rarely changes):
    industry_tags + target_personas + target_geographies + deal_size
    → Changes only when the ICP fundamentally changes
    → Used for "same buyer, different dates" matching

  Part B — profile_window_hash (volatile signals):
    date_from + date_to + search_year
    → Changes every time the date window shifts

  Match logic:
    profile_core_hash MATCH  +  window within 90 days  → full boost
    profile_core_hash MATCH  +  window older            → partial boost (events still exist)
    profile_core_hash NO MATCH but cosine_sim > 0.75    → weak boost
    No match                                             → cold search (normal pipeline)

VECTOR SIMILARITY (no GPU, no external ML library):
  We embed profiles as sparse TF-IDF vectors over a fixed vocabulary
  built from: industries, personas, geographies, deal sizes.
  Cosine similarity computed with pure Python/numpy.
  Vocabulary is derived from the actual profile fields — never hardcoded.

DB TABLE: profile_feedback
  profile_hash    VARCHAR(64)   — SHA256 of core profile
  profile_window  VARCHAR(32)   — SHA1 of date window
  event_id        VARCHAR(36)   — references events.id
  event_name      VARCHAR(500)  — denormalised for display without JOIN
  fit_score       FLOAT         — score from fit_scorer at time of search
  user_action     VARCHAR(20)   — 'viewed' | 'clicked_link' | 'emailed' | 'clicked_register'
  search_date     DATE          — when this result was served
  event_start_date DATE         — event's start_date at time of search
  profile_vector  TEXT          — JSON-serialised sparse vector (for cosine similarity)
  created_at      TIMESTAMP

INDICES:
  idx_pf_core_hash  → fast lookup by profile_core_hash
  idx_pf_event_id   → fast lookup by event_id (for feedback recording)
  idx_pf_search_date → fast expiry queries
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, datetime, timedelta
from typing import Optional

from loguru import logger
from sqlalchemy import Column, Date, DateTime, Float, Index, String, Text, select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

# ─────────────────────────────────────────────────────────────────
# ORM Model
# ─────────────────────────────────────────────────────────────────

class FeedbackBase(DeclarativeBase):
    pass


class ProfileFeedback(FeedbackBase):
    """Stores per-profile × per-event feedback for instant recall."""
    __tablename__ = "profile_feedback"

    # Composite PK: one row per (profile_hash, event_id)
    profile_hash    = Column(String(64),  primary_key=True, nullable=False,
                             comment="SHA256 of core ICP (industry+persona+geo+deal)")
    event_id        = Column(String(36),  primary_key=True, nullable=False,
                             comment="events.id — not FK to allow orphaned records")
    profile_window  = Column(String(32),  nullable=False, default="",
                             comment="SHA1 of date window — for freshness check")
    event_name      = Column(String(500), nullable=False, default="",
                             comment="Denormalised event name — no JOIN needed")
    fit_score       = Column(Float,       nullable=False, default=0.0,
                             comment="fit_scorer output at search time (0-100)")
    user_action     = Column(String(20),  nullable=False, default="viewed",
                             comment="viewed|clicked_link|emailed|clicked_register")
    search_date     = Column(Date,        nullable=False, default=date.today,
                             comment="Date this result was served")
    event_start_date= Column(Date,        nullable=True,
                             comment="Event start_date at time of search")
    profile_vector  = Column(Text,        nullable=False, default="{}",
                             comment="JSON sparse vector for cosine similarity")
    created_at      = Column(DateTime,    nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_pf_core_hash",   "profile_hash"),
        Index("idx_pf_event_id",    "event_id"),
        Index("idx_pf_search_date", "search_date"),
    )


# ─────────────────────────────────────────────────────────────────
# Profile hashing
# ─────────────────────────────────────────────────────────────────

def _normalise_list(vals: list) -> list[str]:
    """Sort + lowercase + strip for stable hashing."""
    return sorted({str(v).strip().lower() for v in (vals or []) if v})


def profile_core_hash(profile) -> str:
    """
    SHA256 of the stable ICP signals.
    Changes when: industry, persona, geography, or deal size changes.
    Does NOT change when: date window changes, company name changes.
    """
    core = {
        "industries":  _normalise_list(getattr(profile, "target_industries", []) or []),
        "personas":    _normalise_list(getattr(profile, "target_personas", []) or []),
        "geographies": _normalise_list(getattr(profile, "target_geographies", []) or []),
        "deal_size":   (getattr(profile, "avg_deal_size_category", "") or "").lower().strip(),
    }
    blob = json.dumps(core, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def profile_window_hash(profile) -> str:
    """
    SHA1 of the volatile date window.
    Used to detect stale cached results.
    """
    date_from = str(getattr(profile, "date_from", "") or "")[:7]  # YYYY-MM is enough
    date_to   = str(getattr(profile, "date_to",   "") or "")[:7]
    year      = date.today().strftime("%Y")
    blob      = f"{date_from}|{date_to}|{year}"
    return hashlib.sha1(blob.encode()).hexdigest()[:16]


# ─────────────────────────────────────────────────────────────────
# Sparse TF-IDF profile vector
# ─────────────────────────────────────────────────────────────────

def _tokenise(text: str) -> list[str]:
    """Split text into lowercase tokens ≥ 3 chars."""
    return [w for w in re.split(r"[\s,/\-&+|]+", text.lower()) if len(w) >= 3]


def build_profile_vector(profile) -> dict[str, float]:
    """
    Build a sparse TF-IDF-like vector from profile fields.
    No external libraries — pure Python dict of {token: weight}.

    Weights:
      industry token = 1.5  (highest — most discriminating)
      persona  token = 1.2
      geo      token = 0.8
      deal     token = 0.5
    """
    vec: dict[str, float] = {}

    def _add(tokens: list[str], weight: float) -> None:
        for t in tokens:
            vec[t] = vec.get(t, 0.0) + weight

    for ind in (getattr(profile, "target_industries", []) or []):
        _add(_tokenise(ind), 1.5)
    for per in (getattr(profile, "target_personas", []) or []):
        _add(_tokenise(per), 1.2)
    for geo in (getattr(profile, "target_geographies", []) or []):
        _add(_tokenise(geo), 0.8)

    deal = (getattr(profile, "avg_deal_size_category", "") or "").lower()
    if deal:
        _add([deal], 0.5)

    # L2-normalise
    norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
    return {k: round(v / norm, 4) for k, v in vec.items()}


def cosine_similarity(va: dict[str, float], vb: dict[str, float]) -> float:
    """Dot product of two sparse L2-normalised vectors."""
    shared = set(va) & set(vb)
    return sum(va[k] * vb[k] for k in shared)


# ─────────────────────────────────────────────────────────────────
# Store + retrieve
# ─────────────────────────────────────────────────────────────────

# How old a cached event can be before we distrust it
_FULL_BOOST_DAYS    = 90    # same window → full boost (×1.25 fit_score)
_PARTIAL_BOOST_DAYS = 365   # older but event hasn't passed → partial boost (×1.10)
_COSINE_THRESHOLD   = 0.72  # min similarity to count as "same ICP"


async def record_search_results(
    db:      AsyncSession,
    profile,
    events:  list[dict],   # serialised event dicts from routes_events
) -> None:
    """
    Store (profile_hash, event_id, fit_score, user_action="viewed") for
    each event shown in the search results.

    Called once at the end of a successful search — fire and forget.
    Upserts: if the same profile × event has been seen before, update
    fit_score and search_date (keeping the best score).
    """
    if not events:
        return

    core_hash  = profile_core_hash(profile)
    win_hash   = profile_window_hash(profile)
    vec        = build_profile_vector(profile)
    vec_json   = json.dumps(vec, separators=(",", ":"))
    today      = date.today()

    try:
        # Bulk upsert via INSERT … ON CONFLICT UPDATE
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        from sqlalchemy.dialects.sqlite     import insert as sqlite_insert
        from config import get_settings as _gs

        # Detect dialect from DATABASE_URL — no separate helper needed
        _db_url = str(_gs().database_url).lower()
        dialect = "postgresql" if "postgresql" in _db_url or "asyncpg" in _db_url else "sqlite"
        _insert = pg_insert if dialect == "postgresql" else sqlite_insert

        rows = []
        for ev in events[:20]:   # cap at 20 per search
            eid   = ev.get("id") or ev.get("event_id", "")
            ename = (ev.get("event_name") or ev.get("name") or "")[:500]
            fscore= float(ev.get("fit_score") or ev.get("relevance_score") or 0)
            edate_str = ev.get("start_date") or ev.get("date") or ""
            try:
                edate = date.fromisoformat(edate_str[:10]) if edate_str else None
            except ValueError:
                edate = None

            if not eid:
                continue

            rows.append({
                "profile_hash":     core_hash,
                "event_id":         eid,
                "profile_window":   win_hash,
                "event_name":       ename,
                "fit_score":        fscore,
                "user_action":      "viewed",
                "search_date":      today,
                "event_start_date": edate,
                "profile_vector":   vec_json,
                "created_at":       datetime.utcnow(),
            })

        if not rows:
            return

        stmt = _insert(ProfileFeedback).values(rows)

        if dialect == "postgresql":
            # On conflict: update score if new one is higher, always update search_date
            stmt = stmt.on_conflict_do_update(
                index_elements=["profile_hash", "event_id"],
                set_={
                    "fit_score":       func.greatest(
                        ProfileFeedback.fit_score, stmt.excluded.fit_score
                    ),
                    "search_date":     stmt.excluded.search_date,
                    "profile_window":  stmt.excluded.profile_window,
                    "profile_vector":  stmt.excluded.profile_vector,
                }
            )
        else:
            # SQLite: replace on conflict
            stmt = stmt.prefix_with("OR REPLACE")

        await db.execute(stmt)
        await db.commit()
        logger.debug(f"ProfileStore: recorded {len(rows)} events for hash={core_hash[:12]}")

    except Exception as exc:
        logger.debug(f"ProfileStore record error: {exc}")
        try:
            await db.rollback()
        except Exception:
            pass


async def record_user_action(
    db:         AsyncSession,
    profile_hash: str,
    event_id:   str,
    action:     str,       # 'clicked_link' | 'emailed' | 'clicked_register'
) -> None:
    """
    Update the user_action for a specific profile×event.
    Called from the frontend action endpoint (POST /api/event-action).
    """
    try:
        await db.execute(
            ProfileFeedback.__table__.update()
            .where(ProfileFeedback.profile_hash == profile_hash)
            .where(ProfileFeedback.event_id == event_id)
            .values(user_action=action)
        )
        await db.commit()
    except Exception as exc:
        logger.debug(f"ProfileStore action update error: {exc}")


async def get_recall_boosts(
    db:      AsyncSession,
    profile,
    today:   Optional[date] = None,
) -> dict[str, float]:
    """
    Find events with high fit_scores for this profile (or similar profiles).
    Returns {event_id: boost_multiplier} for pre-ranking known good events.

    Boost multipliers:
      Same core_hash + fresh window (≤90d)    → 1.30  (strong signal)
      Same core_hash + stale window (≤365d)   → 1.15  (event might still exist)
      Same core_hash + very old OR past event → 1.05  (weak prior)
      Cosine-similar profile (sim ≥ 0.72)     → 0.90 × sim  (proportional)

    A boost > 1.0 means "pre-sort this event higher".
    Events that the user clicked_register get an additional +0.15 multiplier.
    Events from profiles that clicked (not just viewed) count more.

    EXPIRY LOGIC:
      - event_start_date < today → event has passed → no boost (or 1.0 neutral)
      - search_date > _PARTIAL_BOOST_DAYS ago → signal too old → decay to 1.05
      - Date window changed (window_hash mismatch) → use partial boost only
    """
    if today is None:
        today = date.today()

    core_hash = profile_core_hash(profile)
    win_hash  = profile_window_hash(profile)
    vec       = build_profile_vector(profile)
    boosts:   dict[str, float] = {}

    try:
        # ── 1. Exact core hash match ──────────────────────────────────
        cutoff_date  = today - timedelta(days=_PARTIAL_BOOST_DAYS)
        result = await db.execute(
            select(ProfileFeedback)
            .where(ProfileFeedback.profile_hash == core_hash)
            .where(ProfileFeedback.search_date  >= cutoff_date)
            .order_by(ProfileFeedback.fit_score.desc())
            .limit(50)
        )
        rows = result.scalars().all()

        for row in rows:
            # Skip events that have already passed
            if row.event_start_date and row.event_start_date < today:
                continue
            if row.fit_score < 35:
                continue   # below grade-C threshold — not worth boosting

            days_old = (today - row.search_date).days
            # Determine boost based on freshness + window match
            if win_hash == row.profile_window and days_old <= _FULL_BOOST_DAYS:
                base = 1.30  # same date window, fresh
            elif days_old <= _FULL_BOOST_DAYS:
                base = 1.20  # fresh but date window shifted
            elif days_old <= _PARTIAL_BOOST_DAYS:
                base = 1.10  # older but within a year
            else:
                base = 1.05  # very old, weak signal

            # Action multiplier — engagement quality matters
            action = (row.user_action or "viewed").lower()
            action_mult = {
                "clicked_register": 1.20,
                "emailed":          1.15,
                "clicked_link":     1.10,
                "viewed":           1.00,
            }.get(action, 1.00)

            final = min(base * action_mult, 1.50)   # cap at 1.5× to not overwhelm scoring
            existing = boosts.get(row.event_id, 1.0)
            boosts[row.event_id] = max(existing, final)

        # ── 2. Cosine-similar profile search ─────────────────────────
        # Check recent rows from OTHER profiles and see if they're similar
        # to the current profile. Only run if we found < 5 exact matches.
        if len(boosts) < 5:
            recent_cutoff = today - timedelta(days=60)   # last 2 months only
            other_result = await db.execute(
                select(ProfileFeedback)
                .where(ProfileFeedback.profile_hash != core_hash)
                .where(ProfileFeedback.search_date  >= recent_cutoff)
                .where(ProfileFeedback.fit_score    >= 50)
                .order_by(ProfileFeedback.fit_score.desc())
                .limit(200)
            )
            other_rows = other_result.scalars().all()

            seen_hashes: dict[str, float] = {}  # hash → sim score
            for row in other_rows:
                if row.event_start_date and row.event_start_date < today:
                    continue

                # Compute cosine similarity if not already done
                h = row.profile_hash
                if h not in seen_hashes:
                    try:
                        other_vec = json.loads(row.profile_vector or "{}")
                        sim = cosine_similarity(vec, other_vec)
                    except Exception:
                        sim = 0.0
                    seen_hashes[h] = sim
                else:
                    sim = seen_hashes[h]

                if sim < _COSINE_THRESHOLD:
                    continue

                # Proportional boost: sim=1.0 → 1.20, sim=0.72 → ~0.86
                cosine_boost = 0.85 + (sim - _COSINE_THRESHOLD) * 1.25
                existing = boosts.get(row.event_id, 1.0)
                boosts[row.event_id] = max(existing, cosine_boost)

        if boosts:
            strong = sum(1 for v in boosts.values() if v >= 1.20)
            logger.info(
                f"ProfileStore recall: {len(boosts)} events boosted "
                f"({strong} strong ≥1.20) for hash={core_hash[:12]}"
            )

    except Exception as exc:
        logger.debug(f"ProfileStore recall error: {exc}")

    return boosts


# ─────────────────────────────────────────────────────────────────
# Table init (called once at startup)
# ─────────────────────────────────────────────────────────────────

async def init_profile_feedback_table(engine) -> None:
    """Create profile_feedback table if it doesn't exist."""
    try:
        async with engine.begin() as conn:
            await conn.run_sync(FeedbackBase.metadata.create_all)
        logger.info("ProfileStore: profile_feedback table ready")
    except Exception as exc:
        logger.warning(f"ProfileStore init error: {exc}")


# ─────────────────────────────────────────────────────────────────
# Cleanup job (call from a periodic task or admin endpoint)
# ─────────────────────────────────────────────────────────────────

async def cleanup_expired_feedback(
    db:          AsyncSession,
    keep_days:   int = 365,
) -> int:
    """
    Delete feedback rows where:
      - search_date is older than keep_days ago  AND
      - event_start_date has already passed

    Keeps: recent rows + future events, regardless of age.
    Returns number of rows deleted.
    """
    try:
        cutoff = date.today() - timedelta(days=keep_days)
        result = await db.execute(
            ProfileFeedback.__table__.delete()
            .where(ProfileFeedback.search_date  < cutoff)
            .where(ProfileFeedback.event_start_date < date.today())
        )
        await db.commit()
        n = result.rowcount or 0
        logger.info(f"ProfileStore cleanup: deleted {n} expired rows (>{keep_days}d old + past events)")
        return n
    except Exception as exc:
        logger.debug(f"ProfileStore cleanup error: {exc}")
        return 0
