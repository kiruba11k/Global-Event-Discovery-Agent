"""
db/models.py  —  Clean EventORM (28 columns, no dead weight)

Dropped from original 47-column schema:
  short_summary, edition_number, duration_days, timezone, is_annual,
  address, lat, lng, is_virtual, is_hybrid, est_buyer_orgs, vip_count,
  exhibitor_count, speaker_count, ticket_price_usd, event_cities,
  event_venues, related_industries, organizer

Column order mirrors events_clean.csv exactly so CSV re-imports align
without specifying column names.
"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import (
    Boolean, Column, Float, Integer, String, Text, DateTime, Index
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class EventORM(Base):
    __tablename__ = "events"

    # ── Identity ───────────────────────────────────────────────────
    id              = Column(String,   primary_key=True)
    source_platform = Column(String,   nullable=False, default="",
                             comment="Normalised: EventsEye | Ticketmaster | PredictHQ | Eventbrite | Seed | TechCrunch | Wikipedia")
    source_url      = Column(Text,     nullable=False, default="",
                             comment="Original scraping URL — EventsEye event page, Ticketmaster event URL, etc. Used as primary link for known platforms.")
    dedup_hash      = Column(String,   nullable=False, default="",
                             comment="SHA-1 of normalised name+date+city for deduplication")

    # ── Core event info ─────────────────────────────────────────────
    name            = Column(String,   nullable=False, default="")
    description     = Column(Text,     nullable=False, default="",
                             comment="EventsEye prefix 'EVENT NAME - ' stripped at ingestion")
    category        = Column(String,   nullable=False, default="",
                             comment="conference | summit | expo | trade show | fair | etc.")
    start_date      = Column(String,   nullable=False, default="",
                             comment="ISO date YYYY-MM-DD")
    end_date        = Column(String,   nullable=False, default="",
                             comment="ISO date YYYY-MM-DD; may equal start_date for 1-day events")
    venue_name      = Column(String,   nullable=False, default="")
    city            = Column(String,   nullable=False, default="")
    country         = Column(String,   nullable=False, default="")

    # ── Classification ──────────────────────────────────────────────
    industry_tags   = Column(Text,     nullable=False, default="",
                             comment="Comma-separated industry tags, e.g. 'fintech,cloud,AI'")
    audience_personas = Column(Text,   nullable=False, default="",
                             comment="Comma-separated buyer roles, e.g. 'CIO,CTO,VP IT'")

    # ── Attendance ──────────────────────────────────────────────────
    est_attendees   = Column(Integer,  nullable=False, default=0,
                             comment="Estimated total attendees; 0 = unknown. SerpAPI enriches this.")

    # ── Pricing ─────────────────────────────────────────────────────
    price_description = Column(String, nullable=False, default="",
                             comment="Free text: 'From $299', 'By invitation', 'See website', etc.")

    # ── Links ───────────────────────────────────────────────────────
    registration_url = Column(Text,    nullable=False, default="",
                             comment="Event registration/official site URL. Venue-domain URLs cleared at ingestion.")
    website          = Column(Text,    nullable=False, default="",
                             comment="SerpAPI-enriched official URL. Takes priority over registration_url in _best_link().")
    sponsors         = Column(Text,    nullable=False, default="",
                             comment="Comma-separated sponsor / exhibiting company names")
    speakers_url     = Column(Text,    nullable=False, default="")
    agenda_url       = Column(Text,    nullable=False, default="")

    # ── Agent scoring (written by groq_ranker after search) ─────────
    relevance_score  = Column(Float,   nullable=False, default=0.0,
                             comment="0–100 weighted relevance score set by groq_ranker")
    relevance_tier   = Column(String,  nullable=False, default="",
                             comment="GO | CONSIDER | SKIP")
    rationale        = Column(Text,    nullable=False, default="",
                             comment="LLM-generated rationale for the score")
    confidence_score = Column(Float,   nullable=False, default=0.8,
                             comment="Source confidence 0–1; EventsEye=0.8, Seed=0.95, TM=0.9")

    # ── Timestamps + flags ──────────────────────────────────────────
    ingested_at      = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_verified_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    serpapi_enriched = Column(Boolean,  nullable=False, default=False,
                             comment="True once SerpAPI enrichment has run for this event")

    # ── Indexes for search performance ──────────────────────────────
    __table_args__ = (
        Index("ix_events_start_date",      "start_date"),
        Index("ix_events_country",         "country"),
        Index("ix_events_source_platform", "source_platform"),
        Index("ix_events_relevance_score", "relevance_score"),
        Index("ix_events_dedup_hash",      "dedup_hash", unique=True),
    )

    def __repr__(self) -> str:
        return f"<Event {self.id[:8]} | {self.name[:40]} | {self.start_date}>"

    # ── Convenience property ─────────────────────────────────────────
    @property
    def best_link(self) -> str:
        """
        Quick in-model best-link resolver (no SerpAPI).
        Full resolution lives in groq_ranker._best_link().
        Used only for admin views and health checks.
        """
        from urllib.parse import urlparse

        def _is_platform_url(url: str) -> bool:
            if not url: return False
            PLATFORMS = {
                "eventseye.com", "ticketmaster.com", "ticketmaster.co.uk",
                "eventbrite.com", "luma.com", "lu.ma", "konfhub.com",
                "townscript.com", "10times.com", "techcrunch.com",
            }
            try:
                host  = urlparse(url).netloc.lower().lstrip("www.")
                path  = urlparse(url).path.strip("/")
                return any(host == p or host.endswith("." + p) for p in PLATFORMS) and bool(path)
            except Exception:
                return False

        if _is_platform_url(self.source_url): return self.source_url
        if self.website and not self.website.startswith("https://www.google.com"):
            return self.website
        if self.registration_url and not self.registration_url.startswith("https://www.google.com"):
            return self.registration_url
        return ""
