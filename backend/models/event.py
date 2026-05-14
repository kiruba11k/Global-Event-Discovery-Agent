"""
models/event.py — updated to match actual Neon DB schema.

New columns added (matching what EventsEye scraper stores):
  event_cities      — "Guangzhou (China)" style location strings
  event_venues      — actual venue names
  related_industries — industry categories from the source
  website           — official event website (separate from source_url)
  organizer         — event organiser / company

All new columns are nullable so existing rows keep working.
The init_db() in database.py runs ALTER TABLE IF NOT EXISTS to add them.
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
    source_platform  = Column(String, nullable=False, default="")
    source_url       = Column(String, nullable=False, default="")
    dedup_hash       = Column(String, unique=True, index=True)

    # ── Core fields ─────────────────────────────────────────
    name             = Column(String, nullable=False, index=True)
    description      = Column(Text, default="")
    short_summary    = Column(Text, default="")
    edition_number   = Column(String, default="")

    start_date       = Column(String, nullable=False, index=True)
    end_date         = Column(String, default="")
    duration_days    = Column(Integer, default=1)

    # ── Location — support both old schema and new EventsEye schema ──
    venue_name       = Column(String, default="")    # old field
    address          = Column(String, default="")    # old field
    city             = Column(String, default="", index=True)
    country          = Column(String, default="", index=True)
    is_virtual       = Column(Boolean, default=False)
    is_hybrid        = Column(Boolean, default=False)

    # NEW: EventsEye-style rich location fields
    event_venues     = Column(Text, default="")      # "China Import and Export Fair Complex"
    event_cities     = Column(Text, default="")      # "Guangzhou (China)"

    # ── Attendance & pricing ─────────────────────────────────
    est_attendees    = Column(Integer, default=0)
    vip_count        = Column(Integer, default=0)
    exhibitor_count  = Column(Integer, default=0)
    speaker_count    = Column(Integer, default=0)
    ticket_price_usd = Column(Float, default=0.0)
    price_description = Column(String, default="")

    # ── Links ────────────────────────────────────────────────
    registration_url = Column(String, default="")    # old field
    website          = Column(String, default="")    # NEW: official event website
    sponsors         = Column(Text, default="")
    speakers_url     = Column(String, default="")
    agenda_url       = Column(String, default="")

    # ── Classification ───────────────────────────────────────
    category         = Column(String, default="")
    industry_tags    = Column(Text, default="")      # old field
    related_industries = Column(Text, default="")    # NEW: rich industry list from source
    audience_personas = Column(Text, default="")
    organizer        = Column(String, default="")    # NEW: event organiser

    # ── AI scoring (written back by groq ranker) ─────────────
    relevance_score  = Column(Float, default=0.0)
    relevance_tier   = Column(String, default="")
    rationale        = Column(Text, default="")

    # ── Metadata ─────────────────────────────────────────────
    ingested_at      = Column(DateTime, default=datetime.utcnow)
    last_verified_at = Column(DateTime, default=datetime.utcnow)
    confidence_score = Column(Float, default=0.8)

    # ── Enrichment tracking ──────────────────────────────────
    serpapi_enriched = Column(Boolean, default=False)  # was SerpAPI used to fill gaps?

    # ── Helpers ──────────────────────────────────────────────

    @property
    def effective_industries(self) -> str:
        """Return whichever industry field has data."""
        return self.related_industries or self.industry_tags or self.category or ""

    @property
    def effective_website(self) -> str:
        """Return best link for this event."""
        return self.website or self.registration_url or self.source_url or ""

    @property
    def effective_city(self) -> str:
        return self.event_cities or self.city or ""

    @property
    def effective_venue(self) -> str:
        return self.event_venues or self.venue_name or ""

    @property
    def effective_place(self) -> str:
        parts = filter(None, [
            self.effective_venue,
            self.effective_city,
            self.country,
        ])
        return ", ".join(parts)


# ── Pydantic models ────────────────────────────────────────

class EventBase(BaseModel):
    name:              str
    description:       str = ""
    short_summary:     str = ""
    start_date:        str
    end_date:          str = ""
    duration_days:     int = 1

    venue_name:        str = ""
    address:           str = ""
    city:              str = ""
    country:           str = ""
    is_virtual:        bool = False
    is_hybrid:         bool = False

    event_venues:      str = ""        # NEW
    event_cities:      str = ""        # NEW

    est_attendees:     int = 0
    ticket_price_usd:  float = 0.0
    price_description: str = ""

    registration_url:  str = ""
    website:           str = ""        # NEW
    source_url:        str = ""
    source_platform:   str = ""
    sponsors:          str = ""
    speakers_url:      str = ""
    agenda_url:        str = ""
    edition_number:    str = ""

    category:          str = ""
    industry_tags:     str = ""
    related_industries: str = ""       # NEW
    audience_personas: str = ""
    organizer:         str = ""        # NEW


class EventCreate(EventBase):
    id:         str
    dedup_hash: str


class EventRead(EventBase):
    id:              str
    relevance_score: float = 0.0
    relevance_tier:  str   = ""
    rationale:       str   = ""
    ingested_at:     datetime

    class Config:
        from_attributes = True


class RankedEvent(BaseModel):
    """What the API returns to the frontend."""
    id:              str
    event_name:      str
    date:            str
    place:           str
    event_link:      str
    what_its_about:  str
    key_numbers:     str
    industry:        str
    buyer_persona:   str
    pricing:         str
    pricing_link:    str
    fit_verdict:     str          # GO / CONSIDER / SKIP
    verdict_notes:   str
    sponsors:        str
    speakers_link:   str
    agenda_link:     str
    relevance_score: float
    source_platform: str
    est_attendees:   int  = 0
    organizer:       str  = ""
    website:         str  = ""
    serpapi_enriched: bool = False  # frontend can show "ⓘ enriched" badge
