"""
models/cache.py — EnrichmentCache table.

Keyed by dedup_hash (the same stable event identity used across the
catalog, see models/event.py) rather than event.id, so a cache hit
survives an event being re-ingested with a new id from a different
source run. Shares Base with EventORM so db.database.init_db()'s
`EventBase.metadata.create_all` picks this table up automatically.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, String, Text

from models.event import Base


class EnrichmentCacheORM(Base):
    __tablename__ = "enrichment_cache"

    dedup_hash  = Column(String, primary_key=True)
    data_json   = Column(Text, nullable=False, default="{}")
    cached_at   = Column(DateTime, default=datetime.utcnow)
