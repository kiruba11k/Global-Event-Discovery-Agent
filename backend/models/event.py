"""
Event ORM — updated to include extra columns that EventsEye / external
seed scripts insert (event_cities, event_venues, related_industries, website).
All new columns are nullable so existing rows without them don't break.
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from sqlalchemy import Column, String, Float, Integer, Boolean, Text, DateTime
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class EventORM(Base):
    __tablename__ = "events"

    id               = Column(String, primary_key=True)
    source_platform  = Column(String, nullable=False)
    source_url       = Column(String, nullable=False, default="")
    dedup_hash       = Column(String, unique=True, index=True)

    name             = Column(String, nullable=False, index=True)
    description      = Column(Text, default="")
    short_summary    = Column(Text, default="")
    edition_number   = Column(String, default="")

    start_date       = Column(String, nullable=False, index=True)
    end_date         = Column(String, default="")
    duration_days    = Column(Integer, default=1)
    timezone         = Column(String, default="UTC")
    is_annual        = Column(Boolean, default=False)

    # ── Core location ──────────────────────────────────────────
    venue_name       = Column(String, default="")
    address          = Column(String, default="")
    city             = Column(String, default="", index=True)
    country          = Column(String, default="", index=True)
    lat              = Column(Float, default=0.0)
    lng              = Column(Float, default=0.0)
    is_virtual       = Column(Boolean, default=False)
    is_hybrid        = Column(Boolean, default=False)

    # ── Extended location (EventsEye / external sources) ───────
    # e.g. "Jakarta (Indonesia)" or "Frankfurt am Main (Germany)"
    event_cities     = Column(Text, nullable=True, default="")
    # e.g. "Messe Frankfurt, Hall 8"
    event_venues     = Column(Text, nullable=True, default="")

    # ── Audience ───────────────────────────────────────────────
    est_attendees    = Column(Integer, default=0)
    est_buyer_orgs   = Column(Integer, default=0)
    vip_count        = Column(Integer, default=0)
    exhibitor_count  = Column(Integer, default=0)
    speaker_count    = Column(Integer, default=0)

    # ── Classification ─────────────────────────────────────────
    category         = Column(String, default="")
    industry_tags    = Column(Text, default="")
    audience_personas= Column(Text, default="")

    # ── Extended industry tags (EventsEye / external) ──────────
    # e.g. "Adhesion, Paints and Coating Technologies, Plastics, Rubber"
    related_industries = Column(Text, nullable=True, default="")

    # ── Pricing & registration ─────────────────────────────────
    ticket_price_usd      = Column(Float, default=0.0)
    price_description     = Column(String, default="")
    registration_url      = Column(String, default="")

    # ── Official website (separate from registration URL) ───────
    # EventsEye often provides the event's own website separately
    website               = Column(String, nullable=True, default="")

    # ── Extra detail ───────────────────────────────────────────
    sponsors              = Column(Text, default="")
    speakers_url          = Column(String, default="")
    agenda_url            = Column(String, default="")

    # ── Relevance (computed at query time, not stored long-term) ─
    relevance_score  = Column(Float, default=0.0)
    relevance_tier   = Column(String, default="")
    rationale        = Column(Text, default="")

    ingested_at      = Column(DateTime, default=datetime.utcnow)
    last_verified_at = Column(DateTime, default=datetime.utcnow)
    confidence_score = Column(Float, default=0.8)


# ─────────────────────────────────────────────────────────────
# Pydantic schemas
# ─────────────────────────────────────────────────────────────

class EventBase(BaseModel):
    name: str
    description: str = ""
    short_summary: str = ""
    start_date: str
    end_date: str = ""
    duration_days: int = 1
    venue_name: str = ""
    address: str = ""
    city: str = ""
    country: str = ""
    is_virtual: bool = False
    is_hybrid: bool = False
    est_attendees: int = 0
    category: str = ""
    industry_tags: str = ""
    audience_personas: str = ""
    ticket_price_usd: float = 0.0
    price_description: str = ""
    registration_url: str = ""
    source_url: str = ""
    source_platform: str = ""
    sponsors: str = ""
    speakers_url: str = ""
    agenda_url: str = ""
    edition_number: str = ""
    # Extended columns (optional — populated by some sources)
    event_cities: str = ""
    event_venues: str = ""
    related_industries: str = ""
    website: str = ""


class EventCreate(EventBase):
    id: str
    dedup_hash: str


class EventRead(EventBase):
    id: str
    relevance_score: float = 0.0
    relevance_tier: str = ""
    rationale: str = ""
    ingested_at: datetime

    class Config:
        from_attributes = True


class RankedEvent(BaseModel):
    """What the API returns to the frontend after ranking."""
    id: str
    event_name: str
    date: str
    place: str
    event_link: str
    what_its_about: str
    key_numbers: str
    industry: str
    buyer_persona: str
    pricing: str
    pricing_link: str
    fit_verdict: str                 # GO / CONSIDER / SKIP
    verdict_notes: str
    sponsors: str
    speakers_link: str
    agenda_link: str
    relevance_score: float
    source_platform: str
    est_attendees: int = 0
    # Enrichment flags (set True when SerpAPI filled a missing field)
    enriched_attendees:   bool = False
    enriched_price:       bool = False
    enriched_description: bool = False
