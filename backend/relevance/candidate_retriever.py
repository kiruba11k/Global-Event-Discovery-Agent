"""
relevance/candidate_retriever.py — SQL keyword-match + embedding
candidate retrieval (Layers 1, 2 and 4 of the new pipeline).

Gated behind settings.use_keyword_pipeline — additive, does not replace
relevance/scorer.py's score_candidates() unless the caller opts in.

Flow: resolve_region() -> get_region_candidate_count()/should_widen_geo()
(internal control signal only) -> sql_keyword_match() + semantic_recall()
-> blend_and_rank() -> get_top_candidates() returns the top N (default 12).
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models.event import EventORM
from relevance import pgvector_store
from relevance.icp_extractor import normalize_geo
from relevance.scorer import _PROFILE_TO_EVENTSEYE

settings = get_settings()

# Cap how many synonyms one industry can contribute to the search term
# list — _PROFILE_TO_EVENTSEYE entries run 10-30 synonyms each; sending
# all of them per industry would blow up the tsquery for multi-industry
# ICPs and dilute the match toward generic terms.
_MAX_SYNONYMS_PER_INDUSTRY = 8


def _expand_industry_synonyms(industry: str) -> list[str]:
    """
    Same taxonomy bridge scorer.py's _score_industry() Pass 2 uses
    (EventsEye's industry vocabulary rarely says "Fintech" verbatim — it
    says "Financial Technology", "Digital Banking", "Payment Systems",
    etc.) — reused here, not duplicated, so the keyword-match layer gets
    the same synonym coverage the old rule scorer had. Without this, the
    keyword-match layer only ever searched for the LLM's canonical label
    itself, missing events whose related_industries/relevant_keywords
    use a synonym instead of that exact word.
    """
    ind_lower = industry.lower().strip()
    if not ind_lower:
        return []
    ind_tokens = [t for t in re.split(r"[^a-z0-9]+", ind_lower) if len(t) > 2]

    for key, synonyms in _PROFILE_TO_EVENTSEYE.items():
        key_words = [kw for kw in key.split() if len(kw) > 2]
        if not key_words:
            continue
        if all(any(t == kw or t.startswith(kw) for t in ind_tokens) for kw in key_words):
            return synonyms[:_MAX_SYNONYMS_PER_INDUSTRY]
    return []


def _to_tsquery_string(terms: list[str]) -> str:
    """
    Build a to_tsquery-safe OR-of-ANDs string: each term's own words are
    ANDed together (a multi-word term must match as a phrase-ish unit),
    terms are OR'd against each other (matching any one term is enough).
    Strips punctuation to_tsquery would otherwise choke on (unbalanced
    quotes/operators raise a syntax error, not an empty result).
    """
    clauses = []
    for t in terms:
        words = re.sub(r"[^a-zA-Z0-9\s]", " ", t or "").split()
        if not words:
            continue
        clauses.append(" & ".join(words))
    return " | ".join(f"({c})" for c in clauses if c)


# ── Layer 1: region resolution ──────────────────────────────────────

def resolve_region(geo_input: dict) -> dict:
    """geo_input: {"raw": str} or already-shaped {"city","country"}.
    Returns {"city", "country", "canonical_geo"}."""
    raw = geo_input.get("raw") if "raw" in geo_input else None
    if raw is not None:
        return normalize_geo(raw)
    return {
        "city": geo_input.get("city", ""),
        "country": geo_input.get("country", ""),
        "canonical_geo": f"{geo_input.get('city', '')}, {geo_input.get('country', '')}".strip(", "),
    }


# ── Layer 2: region candidate count (internal control signal only) ──

async def get_region_candidate_count(
    db: AsyncSession, geo: dict, industries: list[str],
) -> int:
    """Lightweight COUNT(*) — never returned to the user, only used to
    decide whether to widen the geo filter before the real retrieval
    query runs in Layer 4."""
    where = ["1=1"]
    params: dict = {}
    if geo.get("city"):
        where.append("(city ILIKE :city OR event_cities ILIKE :city_like)")
        params["city"] = geo["city"]
        params["city_like"] = f"%{geo['city']}%"
    elif geo.get("country"):
        where.append("(country ILIKE :country OR event_cities ILIKE :country_like)")
        params["country"] = geo["country"]
        params["country_like"] = f"%{geo['country']}%"
    if industries:
        where.append("(related_industries ILIKE ANY(:inds) OR relevant_keywords ILIKE ANY(:inds))")
        params["inds"] = [f"%{i}%" for i in industries if i]

    try:
        row = (await db.execute(
            text(f"SELECT COUNT(*) FROM events WHERE {' AND '.join(where)}"),
            params,
        )).fetchone()
        return int(row[0]) if row else 0
    except Exception as exc:
        logger.warning(f"candidate_retriever: region count failed ({exc})")
        return 0


def should_widen_geo(count: int, threshold: Optional[int] = None) -> bool:
    threshold = threshold if threshold is not None else settings.region_widen_threshold
    return count < threshold


# ── Layer 4: SQL keyword match ───────────────────────────────────────

async def sql_keyword_match(
    db: AsyncSession, icp_profile: dict, widen_geo: bool = False,
) -> list[EventORM]:
    """
    Full-text/ILIKE match against relevant_keywords + related_industries.
    Uses plainto_tsquery on Postgres (backed by the GIN indexes ensured in
    db.database.init_db()); falls back to ILIKE on SQLite/dev.
    """
    industries = [p["industry"] for p in icp_profile.get("pairs", []) if p.get("industry")]
    keywords   = icp_profile.get("extra_keywords", []) or []
    synonyms: list[str] = []
    for industry in industries:
        synonyms.extend(_expand_industry_synonyms(industry))
    search_terms = list(dict.fromkeys(industries + keywords + synonyms))
    if not search_terms:
        return []

    geo = icp_profile.get("region", {})
    where = ["1=1"]
    params: dict = {}

    is_postgres = db.bind.dialect.name == "postgresql" if db.bind else False
    if is_postgres:
        # OR across terms (any industry/synonym/keyword can match), AND
        # within a multi-word term's own words. plainto_tsquery has no OR
        # operator — it silently ANDs every word across every term, which
        # would require an event to match EVERY industry/synonym at once.
        # to_tsquery supports '|' (OR) / '&' (AND) explicitly instead.
        tsquery = _to_tsquery_string(search_terms)
        if not tsquery:
            return []
        where.append(
            "(to_tsvector('english', coalesce(relevant_keywords,'')) @@ to_tsquery('english', :raw_q) "
            "OR to_tsvector('english', coalesce(related_industries,'')) @@ to_tsquery('english', :raw_q))"
        )
        params["raw_q"] = tsquery
    else:
        like_clauses = []
        for i, term in enumerate(search_terms):
            key = f"kw{i}"
            like_clauses.append(f"(relevant_keywords LIKE :{key} OR related_industries LIKE :{key})")
            params[key] = f"%{term}%"
        where.append("(" + " OR ".join(like_clauses) + ")")

    if not widen_geo and geo.get("country"):
        where.append("(country ILIKE :country OR event_cities ILIKE :country_like)"
                      if is_postgres else
                      "(country LIKE :country OR event_cities LIKE :country_like)")
        params["country"] = geo["country"] if is_postgres else f"%{geo['country']}%"
        params["country_like"] = f"%{geo['country']}%"

    try:
        rows = (await db.execute(
            text(f"SELECT * FROM events WHERE {' AND '.join(where)} LIMIT 200"),
            params,
        )).mappings().all()
    except Exception as exc:
        logger.warning(f"candidate_retriever: keyword match failed ({exc})")
        return []

    events = [EventORM(**{k: v for k, v in dict(r).items() if k in EventORM.__table__.columns.keys()})
              for r in rows]
    return dedupe_by_hash(events)


def embed_event_context(event: EventORM) -> str:
    """
    Richer embedding input than pgvector_store.build_event_text() alone —
    folds in relevant_keywords + related_industries explicitly so the
    embedding-backfill job captures the curated keyword signal, not just
    free-text description.
    """
    parts = [
        getattr(event, "description", "") or "",
        getattr(event, "related_industries", "") or "",
        getattr(event, "relevant_keywords", "") or "",
    ]
    return " ".join(p for p in parts if p)[:2000]


async def semantic_recall(
    db: AsyncSession, icp_profile: dict, exclude_ids: set,
) -> list[tuple[EventORM, float]]:
    """Runs pgvector semantic search over the whole index, then filters
    out anything sql_keyword_match already caught — the residual pool."""
    from models.icp_profile import ICPProfile

    profile_obj = icp_profile.get("_profile_obj")
    if profile_obj is None or not isinstance(profile_obj, ICPProfile):
        return []

    scores = await pgvector_store.semantic_scores(db, profile_obj)
    if not scores:
        return []

    residual_ids = [eid for eid in scores if eid not in exclude_ids]
    if not residual_ids:
        return []

    rows = (await db.execute(
        text("SELECT * FROM events WHERE id = ANY(:ids)"),
        {"ids": residual_ids},
    )).mappings().all()
    events = {r["id"]: EventORM(**{k: v for k, v in dict(r).items()
                                    if k in EventORM.__table__.columns.keys()})
              for r in rows}
    return [(events[eid], scores[eid]) for eid in residual_ids if eid in events]


def dedupe_by_hash(events: Iterable[EventORM]) -> list[EventORM]:
    seen: set = set()
    out: list[EventORM] = []
    for e in events:
        h = getattr(e, "dedup_hash", None) or e.id
        if h in seen:
            continue
        seen.add(h)
        out.append(e)
    return out


def blend_and_rank(
    keyword_hits: list[EventORM],
    semantic_hits: list[tuple[EventORM, float]],
) -> list[tuple[EventORM, float]]:
    """
    score = keyword_weight * keyword_match_score + semantic_weight * cosine_score
    Keyword hits get a flat match score of 1.0 (they matched the curated
    keyword/industry index directly — treated as maximal keyword signal);
    semantic-only hits get 0.0 keyword component. Deduped by dedup_hash
    before scoring so a keyword+semantic double-hit isn't counted twice.
    """
    kw_weight  = settings.keyword_match_weight
    sem_weight = settings.semantic_match_weight

    scored: dict[str, tuple[EventORM, float]] = {}
    for e in keyword_hits:
        h = getattr(e, "dedup_hash", None) or e.id
        scored[h] = (e, kw_weight * 1.0)
    for e, cos in semantic_hits:
        h = getattr(e, "dedup_hash", None) or e.id
        if h in scored:
            existing_event, existing_score = scored[h]
            scored[h] = (existing_event, existing_score + sem_weight * cos)
        else:
            scored[h] = (e, sem_weight * cos)

    ranked = sorted(scored.values(), key=lambda pair: -pair[1])
    return ranked


# ── Public entry point ────────────────────────────────────────────

async def get_top_candidates(
    db: AsyncSession, icp_profile: dict, top_n: Optional[int] = None,
) -> list[tuple[EventORM, float]]:
    """
    Orchestrates Layer 1/2/4: resolve region -> count check -> widen if
    thin -> keyword match + semantic recall -> blend -> top N.
    Returns [(event, blended_score), ...] sorted descending.
    """
    top_n = top_n or settings.candidate_pool_size
    region = icp_profile.get("region", {})
    industries = [p["industry"] for p in icp_profile.get("pairs", []) if p.get("industry")]

    count = await get_region_candidate_count(db, region, industries)
    widen = should_widen_geo(count)
    if widen:
        logger.info(f"candidate_retriever: region candidate count={count} "
                     f"< threshold — widening geo filter")

    keyword_hits = await sql_keyword_match(db, icp_profile, widen_geo=widen)
    exclude_ids = {e.id for e in keyword_hits}
    semantic_hits = await semantic_recall(db, icp_profile, exclude_ids)

    ranked = blend_and_rank(keyword_hits, semantic_hits)
    top = ranked[:top_n]
    logger.info(f"candidate_retriever: {len(keyword_hits)} keyword hits, "
                f"{len(semantic_hits)} semantic-only hits -> top {len(top)} candidates")
    return top
