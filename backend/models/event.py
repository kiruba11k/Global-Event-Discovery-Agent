from __future__ import annotations
from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel, HttpUrl, field_validator
from sqlalchemy import Column, String, Float, Integer, Boolean, Text, DateTime
from sqlalchemy.orm import DeclarativeBase


# ─── SQLAlchemy ORM ───────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


class EventORM(Base):
    __tablename__ = "events"

    id               = Column(String, primary_key=True)          # UUID
    source_platform  = Column(String, nullable=False)
    source_url       = Column(String, nullable=False)
    dedup_hash       = Column(String, unique=True, index=True)

    # Basic
    name             = Column(String, nullable=False, index=True)
    description      = Column(Text, default="")
    short_summary    = Column(Text, default="")
    edition_number   = Column(String, default="")

    # Temporal
    start_date       = Column(String, nullable=False, index=True)
    end_date         = Column(String, default="")
    duration_days    = Column(Integer, default=1)
    timezone         = Column(String, default="UTC")
    is_annual        = Column(Boolean, default=False)

    # Location
    venue_name       = Column(String, default="")
    address          = Column(String, default="")
    city             = Column(String, default="", index=True)
    country          = Column(String, default="", index=True)
    lat              = Column(Float, default=0.0)
    lng              = Column(Float, default=0.0)
    is_virtual       = Column(Boolean, default=False)
    is_hybrid        = Column(Boolean, default=False)

    # Scale
    est_attendees    = Column(Integer, default=0)
    est_buyer_orgs   = Column(Integer, default=0)
    vip_count        = Column(Integer, default=0)
    exhibitor_count  = Column(Integer, default=0)
    speaker_count    = Column(Integer, default=0)

    # Classification
    category         = Column(String, default="")          # tech/health/finance/etc
    industry_tags    = Column(Text, default="")            # comma-separated
    audience_personas = Column(Text, default="")           # comma-separated

    # Commercial
    ticket_price_usd      = Column(Float, default=0.0)
    price_description     = Column(String, default="")
    registration_url      = Column(String, default="")
    sponsors              = Column(Text, default="")
    speakers_url          = Column(String, default="")
    agenda_url            = Column(String, default="")

    # Relevance (filled per-query)
    relevance_score  = Column(Float, default=0.0)
    relevance_tier   = Column(String, default="")          # GO/CONSIDER/SKIP
    rationale        = Column(Text, default="")

    # Provenance
    ingested_at      = Column(DateTime, default=datetime.utcnow)
    last_verified_at = Column(DateTime, default=datetime.utcnow)
    confidence_score = Column(Float, default=0.8)

    # Vector embedding stored externally in FAISS; index key = id


# ─── Pydantic read/write models ───────────────────────────────────
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
    """What the API returns to the frontend — matches the sample output columns."""
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
    fit_verdict: str                    # GO / CONSIDER / SKIP
    verdict_notes: str
    sponsors: str
    speakers_link: str
    agenda_link: str
    relevance_score: float
    source_platform: str
