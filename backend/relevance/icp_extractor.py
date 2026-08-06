"""
relevance/icp_extractor.py — Layer 0 of the keyword+embedding pipeline
(candidate_retriever.py / llm_selector.py, gated behind
settings.use_keyword_pipeline).

Deliberately does NOT re-implement LLM industry/persona extraction —
relevance/icp_parser.py already does that (canonical taxonomy, segment
pairing, caching, graceful degradation). extract_industry_persona_pairs()
is a thin adapter: it calls parse_icp_text(), reshapes the result into
[{"industry": ..., "persona": ...}] pairs, and adds the one thing
icp_parser.py doesn't do — validating each industry against the DB's
actual `related_industries` vocabulary (not just the static canonical
list), so a segment can't reference an industry label no event in the
catalog has ever used.
"""
from __future__ import annotations

from typing import Optional

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from relevance.geo_aliases import canonical_geo
from relevance.icp_parser import parse_icp_text
from relevance.scorer import expand_industry_synonyms


async def _db_industry_vocab(db: AsyncSession) -> list[str]:
    """Distinct non-empty related_industries values actually present in
    the catalog. Cheap — this is a small distinct-value set, not a scan
    of every row's contents."""
    try:
        rows = (await db.execute(
            text("SELECT DISTINCT related_industries FROM events "
                 "WHERE related_industries IS NOT NULL AND related_industries != ''")
        )).scalars().all()
    except Exception as exc:
        logger.warning(f"icp_extractor: industry vocab query failed ({exc})")
        return []
    # related_industries is often a comma-separated blob per row
    # ("Metal Working Industries, Mechanical Components") — split it out
    # into individual vocabulary terms.
    vocab: set[str] = set()
    for row in rows:
        for part in (row or "").split(","):
            p = part.strip()
            if p:
                vocab.add(p)
    return sorted(vocab)


def _industry_present_in_catalog(industry: str, vocab: list[str]) -> bool:
    """
    True if `industry` (or one of its taxonomy-bridge synonyms) appears
    as a substring of ANY vocab term actually present in the catalog.

    NOT character-similarity fuzzy matching (e.g. difflib) — a canonical
    LLM label like "Fintech" and a real DB vocab term like "Digital
    Banking" or "Insurance" describe the same industry but share almost
    no characters, so string-similarity scoring against raw catalog text
    would fail to match on virtually every real industry (verified
    against this catalog's actual related_industries values — every
    canonical label tested returned no fuzzy match at all). Checking
    substring presence of the SAME synonym list candidate_retriever.py's
    keyword search already uses is both correct and consistent: if this
    says "present", the keyword-match query will actually find rows.
    """
    if not vocab:
        return True  # no vocab to validate against — don't block
    ind_lower = industry.lower().strip()
    if not ind_lower:
        return False
    candidates = [ind_lower] + [s.lower() for s in expand_industry_synonyms(industry)]
    vocab_lower = " | ".join(v.lower() for v in vocab)
    return any(c in vocab_lower for c in candidates)


async def extract_industry_persona_pairs(
    raw_text: str,
    db: Optional[AsyncSession] = None,
) -> list[dict]:
    """
    Returns [{"industry": str, "persona": str}, ...] — the flat pairing
    the SQL keyword-match/candidate_retriever layer scores against.

    industry is validated against the DB's actual related_industries
    vocabulary when a `db` session is given: dropped (with a logged
    warning) if neither the label nor any of its taxonomy-bridge
    synonyms appears anywhere in the catalog. Without a db session (or
    on a DB error) the LLM's canonical label passes through unchecked —
    degrade gracefully rather than block extraction on a vocab lookup.

    Returns EXACTLY ONE pair — this pipeline only ever targets a single
    industry + persona, never icp_parser.py's multi-segment pairing
    ("CEO at BFSI, CIO at Medtech" -> two groups). When the input names
    multiple industries/personas/segments, only the PRIMARY one (first
    named — icp_parser.py's system prompt already orders industries with
    the primary first) is kept; the rest are intentionally dropped, not
    silently unioned into a cross-product that could cross-match a
    persona from one group with an industry from another.
    """
    parsed = await parse_icp_text(raw_text)
    if parsed is None:
        return [{"industry": "", "persona": ""}]

    vocab = await _db_industry_vocab(db) if db is not None else []

    segments = parsed.segments or []
    if segments:
        primary_industry = (segments[0].industries or [""])[0]
        primary_persona  = (segments[0].personas or [""])[0]
    else:
        primary_industry = (parsed.industries or [""])[0]
        primary_persona  = (parsed.personas or [""])[0]

    if primary_industry and vocab and not _industry_present_in_catalog(primary_industry, vocab):
        logger.warning(f"icp_extractor: dropping '{primary_industry}' — "
                        "not present in catalog (no matching event data at all)")
        primary_industry = ""

    return [{"industry": primary_industry, "persona": primary_persona}]


def normalize_geo(raw_geo: str) -> dict:
    """
    Canonicalize free-text region input. Reuses geo_aliases.canonical_geo()
    (already the single source of truth for country-name equivalence
    across scorer.py and the geo-hint endpoint) rather than maintaining a
    second, inevitably-drifting alias dict here.

    Returns {"city": str, "country": str, "canonical_geo": str}. City is
    only populated when the input clearly names a city (comma-separated
    "City, Country"); otherwise treated as a country/region-only input.
    """
    raw = (raw_geo or "").strip()
    if not raw:
        return {"city": "", "country": "", "canonical_geo": ""}

    if "," in raw:
        city_part, country_part = [p.strip() for p in raw.split(",", 1)]
    else:
        city_part, country_part = "", raw

    canonical = canonical_geo(country_part) or country_part.lower()
    canonical_display = canonical.title() if canonical else country_part

    return {
        "city": city_part,
        "country": canonical_display,
        "canonical_geo": f"{city_part}, {canonical_display}".strip(", "),
    }
