"""
relevance/pgvector_store.py - semantic event matching on Neon pgvector.

Free-tier semantic search without FAISS/torch:
  - Vectors live IN the existing Postgres (Neon ships pgvector) - no
    separate index files, survives restarts, shared across dynos.
  - Embeddings come from a pluggable provider chain:
      1. fastembed  - local ONNX (BAAI/bge-small-en-v1.5, 384-dim),
                      no API key, ~200MB RAM, CPU-only
      2. Jina API   - free tier, JINA_API_KEY, dimensions forced to 384
                      so both providers are interchangeable in the DB
      3. none       - module is inert; callers get {} / no-ops
  - Events are embedded lazily at search time (bounded per request)
    plus via scripts/backfill_embeddings.py for bulk.

Everything degrades silently: SQLite deploys, missing extension,
missing provider - all paths return empty results, never errors.
"""
from __future__ import annotations

import asyncio
from typing import Iterable, List, Optional, Sequence

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings

settings = get_settings()

_DIM = settings.embedding_dim  # 384 for both bge-small and Jina v3 @ dims=384


# ── Embedding providers ────────────────────────────────────────────

class _FastEmbedProvider:
    name = "fastembed"

    def __init__(self) -> None:
        from fastembed import TextEmbedding
        self._model = TextEmbedding("BAAI/bge-small-en-v1.5")

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        return [v.tolist() for v in self._model.embed(list(texts))]


class _JinaProvider:
    name = "jina"

    def __init__(self, api_key: str) -> None:
        self._key = api_key

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        import httpx
        resp = httpx.post(
            "https://api.jina.ai/v1/embeddings",
            headers={"Authorization": f"Bearer {self._key}",
                     "Content-Type": "application/json"},
            json={"model": settings.jina_embedding_model,
                  "dimensions": _DIM,
                  "input": list(texts)},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        return [d["embedding"] for d in sorted(data, key=lambda d: d["index"])]


_provider: Optional[object] = None
_provider_resolved = False


def get_provider():
    """
    Resolve the embedding provider once; None = semantic disabled.

    Jina (a network call, no local model) is tried first because it has
    zero resident-memory cost. fastembed loads a ~250-300MB ONNX model
    into process memory on first use, which alone is enough to OOM a
    Render free instance (512MB total) — it only runs when the operator
    has explicitly opted in via pgvector_allow_local_embeddings, on top
    of pgvector_enabled.
    """
    global _provider, _provider_resolved
    if _provider_resolved:
        return _provider
    _provider_resolved = True
    if not settings.pgvector_enabled:
        return None

    if settings.jina_api_key:
        _provider = _JinaProvider(settings.jina_api_key)
        logger.info("pgvector: Jina API provider ready (no local model loaded)")
        return _provider

    if settings.pgvector_allow_local_embeddings:
        try:
            _provider = _FastEmbedProvider()
            logger.info("pgvector: fastembed provider ready (bge-small-en-v1.5, "
                        "local ONNX model loaded into memory)")
            return _provider
        except Exception as exc:
            logger.debug(f"pgvector: fastembed unavailable ({exc})")

    logger.info("pgvector: no embedding provider configured - semantic matching off "
                "(set JINA_API_KEY, or PGVECTOR_ALLOW_LOCAL_EMBEDDINGS=true if the "
                "instance has spare RAM for a local model)")
    return None


def _is_postgres() -> bool:
    return settings.database_url.startswith(("postgresql", "postgres"))


def is_active() -> bool:
    """
    Cheap synchronous check — never triggers provider init (which can
    block on a model load or network call). Safe to call from anywhere.
    """
    if not (_is_postgres() and settings.pgvector_enabled):
        return False
    if _provider_resolved:
        return _provider is not None
    return bool(settings.jina_api_key or settings.pgvector_allow_local_embeddings)


async def is_active_async() -> bool:
    """Full check including provider resolution, run off the event loop."""
    if not _is_postgres():
        return False
    provider = await asyncio.to_thread(get_provider)
    return provider is not None


async def _embed(texts: Sequence[str]) -> List[List[float]]:
    """Run the (sync) provider off the event loop."""
    provider = await asyncio.to_thread(get_provider)
    if provider is None:
        return []
    return await asyncio.to_thread(provider.embed, texts)


def _vec_literal(vec: Sequence[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


# ── Schema ─────────────────────────────────────────────────────────

_schema_ready = False


async def ensure_schema(db: AsyncSession) -> bool:
    """Create the vector extension/column/index. True when usable."""
    global _schema_ready
    if not _is_postgres():
        return False
    if _schema_ready:
        return True
    try:
        await db.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await db.execute(text(
            f"ALTER TABLE events ADD COLUMN IF NOT EXISTS embedding vector({_DIM})"
        ))
        # HNSW: good recall at Neon-free scale, no training step needed
        await db.execute(text(
            "CREATE INDEX IF NOT EXISTS idx_events_embedding "
            "ON events USING hnsw (embedding vector_cosine_ops)"
        ))
        await db.commit()
        _schema_ready = True
        logger.info("pgvector: schema ready (extension + column + hnsw index)")
        return True
    except Exception as exc:
        await db.rollback()
        logger.warning(f"pgvector: schema setup failed - semantic off ({exc})")
        return False


# ── Event text (mirrors relevance/embedder.py fields) ──────────────

def build_event_text(event) -> str:
    parts = [
        getattr(event, "name", "") or "",
        getattr(event, "description", "") or "",
        getattr(event, "short_summary", "") or "",
        getattr(event, "industry_tags", "") or "",
        getattr(event, "audience_personas", "") or "",
        getattr(event, "category", "") or "",
        getattr(event, "city", "") or "",
        getattr(event, "country", "") or "",
    ]
    return " ".join(p for p in parts if p)[:2000]


def build_profile_text(profile) -> str:
    parts = [
        getattr(profile, "buyer_description", "") or "",
        getattr(profile, "company_description", "") or "",
        " ".join(getattr(profile, "target_industries", []) or []),
        " ".join(getattr(profile, "target_personas", []) or []),
        " ".join(getattr(profile, "extra_keywords", []) or []),
    ]
    return " ".join(p for p in parts if p)[:1000]


# ── Write path ─────────────────────────────────────────────────────

async def embed_missing(db: AsyncSession, events: Iterable, limit: Optional[int] = None) -> int:
    """
    Embed events whose embedding is NULL. Bounded by `limit`
    (settings.pgvector_embed_batch by default) so a search request
    never stalls on a huge backfill - the rest is picked up next time
    or by scripts/backfill_embeddings.py.
    """
    if not is_active() or not await ensure_schema(db):
        return 0
    limit = limit if limit is not None else settings.pgvector_embed_batch

    ids = [e.id for e in events]
    if not ids:
        return 0
    rows = (await db.execute(
        text("SELECT id FROM events WHERE id = ANY(:ids) AND embedding IS NULL"),
        {"ids": ids},
    )).scalars().all()
    todo_ids = set(rows[:limit])
    todo = [e for e in events if e.id in todo_ids]
    if not todo:
        return 0

    vecs = await _embed([build_event_text(e) for e in todo])
    if not vecs:
        return 0
    for e, v in zip(todo, vecs):
        await db.execute(
            text("UPDATE events SET embedding = CAST(:v AS vector) WHERE id = :id"),
            {"v": _vec_literal(v), "id": e.id},
        )
    await db.commit()
    logger.info(f"pgvector: embedded {len(todo)} events "
                f"({len(rows) - len(todo)} left for backfill)")
    return len(todo)


# ── Read path ──────────────────────────────────────────────────────

async def semantic_matches(
    db:         AsyncSession,
    query_text: str,
    date_from:  Optional[str] = None,
    top_k:      Optional[int] = None,
    min_cosine: float = 0.55,
) -> List[dict]:
    """
    Whole-index semantic search that also returns each hit's geo fields
    (country/city/event_cities), so a caller can filter by region itself
    — used by /api/geo-hint so its live counts include events a semantic
    match would surface even without a literal keyword hit, the same
    recall the main search pipeline already gets via semantic_scores().
    Empty list on any unavailability or empty query text.
    """
    if not query_text.strip() or not is_active() or not await ensure_schema(db):
        return []
    top_k = top_k or settings.pgvector_top_k

    vecs = await _embed([query_text])
    if not vecs:
        return []
    q = _vec_literal(vecs[0])

    try:
        rows = (await db.execute(
            text(
                "SELECT id, country, city, event_cities, "
                "1 - (embedding <=> CAST(:q AS vector)) AS cos "
                "FROM events "
                "WHERE embedding IS NOT NULL "
                "  AND start_date >= :dfrom "
                "ORDER BY embedding <=> CAST(:q AS vector) "
                "LIMIT :k"
            ),
            {"q": q, "dfrom": date_from or "0000-01-01", "k": top_k},
        )).fetchall()
    except Exception as exc:
        logger.warning(f"pgvector: geo semantic search failed ({exc})")
        return []

    return [
        {"id": row[0], "country": row[1] or "", "city": row[2] or "",
         "event_cities": row[3] or "", "cosine": max(0.0, float(row[4]))}
        for row in rows if float(row[4]) >= min_cosine
    ]


async def semantic_scores(
    db: AsyncSession,
    profile,
    date_from: Optional[str] = None,
    date_to:   Optional[str] = None,
    top_k:     Optional[int] = None,
) -> dict[str, float]:
    """
    Whole-index semantic search: {event_id: cosine_similarity} for the
    top_k future events closest to the ICP profile text. Empty dict on
    any unavailability - callers treat that as 'no semantic signal'.
    """
    if not is_active() or not await ensure_schema(db):
        return {}
    top_k = top_k or settings.pgvector_top_k

    vecs = await _embed([build_profile_text(profile)])
    if not vecs:
        return {}
    q = _vec_literal(vecs[0])

    try:
        rows = (await db.execute(
            text(
                "SELECT id, 1 - (embedding <=> CAST(:q AS vector)) AS cos "
                "FROM events "
                "WHERE embedding IS NOT NULL "
                "  AND start_date >= :dfrom "
                "  AND (:dto = '' OR start_date <= :dto) "
                "ORDER BY embedding <=> CAST(:q AS vector) "
                "LIMIT :k"
            ),
            {"q": q, "dfrom": date_from or "0000-01-01",
             "dto": date_to or "", "k": top_k},
        )).fetchall()
    except Exception as exc:
        logger.warning(f"pgvector: search failed ({exc})")
        return {}

    return {row[0]: max(0.0, float(row[1])) for row in rows}
