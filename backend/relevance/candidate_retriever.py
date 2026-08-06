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
from datetime import date as _date
from typing import Iterable, Optional

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models.event import EventORM
from relevance import pgvector_store
from relevance.icp_extractor import normalize_geo
from relevance.scorer import expand_industry_synonyms as _expand_industry_synonyms

settings = get_settings()


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

_GLOBAL_TOKENS = {"global", "worldwide", "international", "any", "anywhere"}


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


def resolve_regions(geo_list: list[str]) -> list[dict]:
    """
    Resolve EVERY selected geography, not just the first — a user who
    picks "India, Singapore, UAE" expects all three searched, not just
    the first one silently used while the rest are dropped. "Global"/
    "Worldwide"/etc. resolve to an empty list (no geo restriction at
    all), matching how scorer.py and the rest of this codebase already
    treat those tokens.
    """
    regions: list[dict] = []
    for raw in geo_list or []:
        if not raw or raw.strip().lower() in _GLOBAL_TOKENS:
            continue
        regions.append(normalize_geo(raw))
    return regions


def _geo_where_clause(
    regions: list[dict], match_op: str, is_postgres: bool, widen_geo: bool, prefix: str,
) -> tuple[str, dict]:
    """
    Builds "(region1 clause) OR (region2 clause) OR ..." across every
    selected region — any one of them matching is enough, mirroring how
    industry/keyword terms are already OR'd together. Each region uses
    city-level matching when available and not widening, else country-
    level. Returns ("", {}) when there's nothing to filter on (no
    regions selected, or all resolved to "Global"/widen_geo=True with no
    country to fall back to).
    """
    if not regions:
        return "", {}
    clauses: list[str] = []
    params: dict = {}
    for i, geo in enumerate(regions):
        if not widen_geo and geo.get("city"):
            key = f"{prefix}city{i}"
            clauses.append(f"(city {match_op} :{key} OR event_cities {match_op} :{key}_like)")
            params[key] = geo["city"] if is_postgres else f"%{geo['city']}%"
            params[f"{key}_like"] = f"%{geo['city']}%"
        elif geo.get("country"):
            key = f"{prefix}country{i}"
            clauses.append(f"(country {match_op} :{key} OR event_cities {match_op} :{key}_like)")
            params[key] = geo["country"] if is_postgres else f"%{geo['country']}%"
            params[f"{key}_like"] = f"%{geo['country']}%"
    if not clauses:
        return "", {}
    return "(" + " OR ".join(clauses) + ")", params


# ── Layer 2: region candidate count (internal control signal only) ──

async def get_region_candidate_count(
    db: AsyncSession, regions: list[dict], industries: list[str],
) -> int:
    """Lightweight COUNT(*) — never returned to the user, only used to
    decide whether to widen the geo filter before the real retrieval
    query runs in Layer 4. `regions`: list of resolved geo dicts (see
    resolve_regions()) — ORs across all of them, not just the first.

    ILIKE is Postgres-only (SQLite has no case-insensitive LIKE operator
    by that name) and ILIKE ANY(:array) doubly so — both raised on
    SQLite, silently caught below, always returning 0 and forcing
    should_widen_geo() to fire regardless of actual data. Dialect-aware
    (mirrors sql_keyword_match's own is_postgres branch) so this signal
    is meaningful in local/SQLite dev too, not just production Postgres.
    """
    is_postgres = db.bind.dialect.name == "postgresql" if db.bind else False
    match_op = "ILIKE" if is_postgres else "LIKE"

    where = ["1=1"]
    params: dict = {}
    geo_clause, geo_params = _geo_where_clause(regions, match_op, is_postgres, widen_geo=False, prefix="cnt_")
    if geo_clause:
        where.append(geo_clause)
        params.update(geo_params)
    # OR of individual clauses, not ILIKE ANY(:array) (Postgres-only).
    ind_terms = [i for i in industries if i]
    if ind_terms:
        ind_clauses = []
        for i, term in enumerate(ind_terms):
            key = f"ind{i}"
            ind_clauses.append(f"(related_industries {match_op} :{key} OR relevant_keywords {match_op} :{key})")
            params[key] = f"%{term}%"
        where.append("(" + " OR ".join(ind_clauses) + ")")

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
    Full-text/ILIKE match against relevant_keywords + related_industries +
    industry_relevant_for (curated CSV's "who this event is relevant for"
    field — a direct buyer-industry-fit signal, arguably stronger than
    related_industries which describes the event's own vertical rather
    than its intended audience). Uses to_tsquery on Postgres (backed by
    the GIN indexes ensured in db.database.init_db()); falls back to
    ILIKE on SQLite/dev.
    """
    industries = [p["industry"] for p in icp_profile.get("pairs", []) if p.get("industry")]
    keywords   = icp_profile.get("extra_keywords", []) or []
    synonyms: list[str] = []
    for industry in industries:
        synonyms.extend(_expand_industry_synonyms(industry))
    search_terms = list(dict.fromkeys(industries + keywords + synonyms))
    if not search_terms:
        return []

    regions = icp_profile.get("regions", [])
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
            "OR to_tsvector('english', coalesce(related_industries,'')) @@ to_tsquery('english', :raw_q) "
            "OR to_tsvector('english', coalesce(industry_relevant_for,'')) @@ to_tsquery('english', :raw_q))"
        )
        params["raw_q"] = tsquery
    else:
        like_clauses = []
        for i, term in enumerate(search_terms):
            key = f"kw{i}"
            like_clauses.append(
                f"(relevant_keywords LIKE :{key} OR related_industries LIKE :{key} "
                f"OR industry_relevant_for LIKE :{key})"
            )
            params[key] = f"%{term}%"
        where.append("(" + " OR ".join(like_clauses) + ")")

    # Upcoming events only, and within the ICP's requested date window
    # when one was given. Previously unfiltered — the only date-related
    # thing this query did was ORDER BY start_date, which sorts but
    # doesn't exclude anything, so already-past or out-of-window events
    # (e.g. a July event when the ICP asked for Sep 2026-Aug 2027) could
    # surface just as easily as a genuinely upcoming one.
    today = _date.today().isoformat()
    date_from = icp_profile.get("date_from") or today
    date_to   = icp_profile.get("date_to") or "2099-12-31"
    where.append("start_date >= :date_from AND start_date <= :date_to")
    params["date_from"] = date_from
    params["date_to"]   = date_to

    # Two-tier geo, OR'd across every selected region: city-level when
    # we have one and aren't widening, else country-level, else
    # (widen_geo=True) no geo filter at all. Any ONE of the selected
    # regions matching is enough — a user who picks "India, Singapore"
    # expects candidates from either, not just the first one selected.
    match_op = "ILIKE" if is_postgres else "LIKE"
    geo_clause, geo_params = _geo_where_clause(regions, match_op, is_postgres, widen_geo, prefix="kw_")
    if geo_clause:
        where.append(geo_clause)
        params.update(geo_params)

    try:
        rows = (await db.execute(
            text(f"SELECT * FROM events WHERE {' AND '.join(where)} "
                 f"ORDER BY start_date ASC LIMIT 200"),
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
        getattr(event, "industry_relevant_for", "") or "",
    ]
    return " ".join(p for p in parts if p)[:2000]


async def semantic_recall(
    db: AsyncSession, icp_profile: dict, exclude_ids: set,
) -> list[tuple[EventORM, float]]:
    """Runs pgvector semantic search over the whole index, then filters
    out anything sql_keyword_match already caught — the residual pool.

    Passes date_from/date_to through to semantic_scores() — that function
    already supports a date window (its own SQL filters start_date), but
    this caller was never actually passing them, so semantic recall could
    surface events from any date at all regardless of what the ICP asked
    for, same bug as sql_keyword_match's missing date filter.
    """
    from models.icp_profile import ICPProfile

    profile_obj = icp_profile.get("_profile_obj")
    if profile_obj is None or not isinstance(profile_obj, ICPProfile):
        return []

    today = _date.today().isoformat()
    date_from = icp_profile.get("date_from") or today
    date_to   = icp_profile.get("date_to") or None

    scores = await pgvector_store.semantic_scores(db, profile_obj, date_from=date_from, date_to=date_to)
    if not scores:
        return []

    residual_ids = [eid for eid in scores if eid not in exclude_ids]
    if not residual_ids:
        return []

    # id = ANY(:ids) is Postgres-only syntax. In practice this is only
    # ever reached when scores is non-empty, which pgvector_store.
    # semantic_scores() only returns on an active Postgres+pgvector setup
    # (it gates on is_active()/ensure_schema() first) — so this should
    # never actually run against SQLite. Wrapped anyway, consistent with
    # every other DB call in this file, rather than relying on that
    # invariant holding forever.
    try:
        rows = (await db.execute(
            text("SELECT * FROM events WHERE id = ANY(:ids)"),
            {"ids": residual_ids},
        )).mappings().all()
    except Exception as exc:
        logger.warning(f"candidate_retriever: semantic recall event lookup failed ({exc})")
        return []
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


async def _fallback_recent_events(
    db: AsyncSession, regions: list[dict], top_n: int,
    date_from: Optional[str] = None, date_to: Optional[str] = None,
) -> list[tuple[EventORM, float]]:
    """
    Last-resort retrieval when the ICP has genuinely no industry/keyword
    signal at all (e.g. "industry-agnostic" — icp_parser.py deliberately
    returns an empty industries list for that rather than guessing a
    vertical) AND semantic recall found nothing (no embedding provider
    active, or no embeddings backfilled yet). Without this,
    sql_keyword_match() short-circuits on an empty search_terms list and
    semantic_recall() needs pgvector active — an industry-agnostic ICP
    with no embedding provider configured would otherwise get zero
    candidates every time, even though the region may have plenty of
    upcoming events worth showing the LLM selector.

    Filters by region only (best-effort ILIKE, no hard requirement — an
    empty region still returns something, and multiple regions are OR'd
    together via _geo_where_clause), ordered by soonest start_date, given
    a flat neutral score so it never outranks a real keyword or semantic
    match when both are combined elsewhere.
    """
    is_postgres = db.bind.dialect.name == "postgresql" if db.bind else False
    match_op = "ILIKE" if is_postgres else "LIKE"
    today = _date.today().isoformat()
    where = ["start_date >= :date_from AND start_date <= :date_to"]
    params: dict = {
        "date_from": date_from or today,
        "date_to":   date_to or "2099-12-31",
    }
    geo_clause, geo_params = _geo_where_clause(regions, match_op, is_postgres, widen_geo=False, prefix="fb_")
    if geo_clause:
        where.append(geo_clause)
        params.update(geo_params)

    try:
        rows = (await db.execute(
            text(f"SELECT * FROM events WHERE {' AND '.join(where)} "
                 f"ORDER BY start_date ASC LIMIT :n"),
            {**params, "n": top_n},
        )).mappings().all()
    except Exception as exc:
        logger.warning(f"candidate_retriever: fallback recall failed ({exc})")
        return []

    events = dedupe_by_hash(
        EventORM(**{k: v for k, v in dict(r).items() if k in EventORM.__table__.columns.keys()})
        for r in rows
    )
    logger.info(f"candidate_retriever: no keyword/semantic signal — "
                f"fell back to {len(events)} region/date-ordered events")
    return [(e, 0.10) for e in events]  # flat neutral score — never a real match, just a fill


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
    regions = icp_profile.get("regions", [])
    industries = [p["industry"] for p in icp_profile.get("pairs", []) if p.get("industry")]
    keywords   = icp_profile.get("extra_keywords", []) or []

    count = await get_region_candidate_count(db, regions, industries)
    widen = should_widen_geo(count)
    if widen:
        logger.info(f"candidate_retriever: region candidate count={count} "
                     f"< threshold — widening geo filter")

    keyword_hits = await sql_keyword_match(db, icp_profile, widen_geo=widen)
    exclude_ids = {e.id for e in keyword_hits}
    semantic_hits = await semantic_recall(db, icp_profile, exclude_ids)

    ranked = blend_and_rank(keyword_hits, semantic_hits)

    if not ranked and not industries and not keywords:
        # Genuinely no signal to search on (industry-agnostic ICP) and
        # semantic recall found nothing — fall back to region/date rather
        # than returning zero candidates to the LLM selector.
        ranked = await _fallback_recent_events(
            db, regions, top_n,
            date_from=icp_profile.get("date_from"), date_to=icp_profile.get("date_to"),
        )

    top = ranked[:top_n]
    logger.info(f"candidate_retriever: {len(keyword_hits)} keyword hits, "
                f"{len(semantic_hits)} semantic-only hits -> top {len(top)} candidates")
    return top
