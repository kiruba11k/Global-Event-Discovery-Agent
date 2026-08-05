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

import difflib
from typing import Optional

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from relevance.geo_aliases import canonical_geo
from relevance.icp_parser import parse_icp_text

# Fuzzy-match threshold for correcting a near-miss industry label against
# the DB vocabulary (e.g. "Health Tech" -> "Healthcare / Medtech").
_FUZZY_CUTOFF = 0.72


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


def _fuzzy_correct(industry: str, vocab: list[str]) -> Optional[str]:
    if not vocab:
        return industry  # no vocab to validate against — pass through
    lower_vocab = {v.lower(): v for v in vocab}
    if industry.lower() in lower_vocab:
        return lower_vocab[industry.lower()]
    match = difflib.get_close_matches(industry.lower(), lower_vocab.keys(),
                                       n=1, cutoff=_FUZZY_CUTOFF)
    return lower_vocab[match[0]] if match else None


async def extract_industry_persona_pairs(
    raw_text: str,
    db: Optional[AsyncSession] = None,
) -> list[dict]:
    """
    Returns [{"industry": str, "persona": str}, ...] — the flat pairing
    the SQL keyword-match/candidate_retriever layer scores against.

    industry is validated against the DB's actual related_industries
    vocabulary when a `db` session is given: an unmatched industry is
    fuzzy-corrected to the nearest real vocabulary term, or dropped (with
    a logged warning) if nothing is close enough. Without a db session
    (or on a DB error) the LLM's canonical label passes through unchecked —
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

    corrected = _fuzzy_correct(primary_industry, vocab) if primary_industry else ""
    if primary_industry and vocab and corrected is None:
        logger.warning(f"icp_extractor: dropping unmatched industry "
                        f"'{primary_industry}' (no close DB vocab match)")
        primary_industry = ""
    else:
        primary_industry = corrected or primary_industry

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
