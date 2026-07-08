"""
relevance/icp_parser.py - LLM-based universal ICP parsing.

Turns free text like "Head of Perioperative Services at ambulatory
surgery centers" into structured targeting data. The hardcoded keyword
maps (frontend parseBuyerText, scorer taxonomy) can only cover the
designations someone thought to list; the LLM covers the long tail of
titles, niches and phrasings in any wording.

Design:
  - Canonical taxonomy anchors the output so downstream scoring stays
    consistent: the LLM must map to known industry labels first.
  - Open vocabulary is preserved: niche descriptors that don't fit a
    canonical label are returned in extra_keywords and flow into the
    scorer's free-text matching, so nothing the user typed is lost.
  - Free-tier safe: goes through llm_client (budgeting, model fallback,
    TTL cache). Identical inputs within an hour cost zero tokens.
  - Never blocks the product: on any LLM failure the caller falls back
    to the rule-based parser. This endpoint degrades, never errors.
"""
from __future__ import annotations

from typing import List, Optional

from loguru import logger
from pydantic import BaseModel, field_validator

from relevance.llm_client import llm

# ── Canonical taxonomy ─────────────────────────────────────────────
# Must stay in sync with the labels the scorer taxonomy understands.
# The LLM maps free text INTO these; anything that doesn't fit goes to
# extra_keywords instead of being forced into a wrong bucket.

CANONICAL_INDUSTRIES: List[str] = [
    "Fintech", "Cloud Computing", "AI / Machine Learning", "Cybersecurity",
    "Manufacturing", "Logistics / Supply Chain", "Healthcare / Medtech",
    "Retail / Ecommerce", "Energy / Cleantech", "HR Tech", "Marketing / Adtech",
    "Real Estate / PropTech", "Telecommunications", "Technology",
    "Food & Beverage", "Automotive", "Fashion / Apparel",
    "Agriculture / AgriTech", "Education / EdTech", "Mining / Resources",
    "Government / Public Sector", "Defence / Aerospace", "Startup / VC",
    "Legal Tech", "Travel / Hospitality", "Data & Analytics",
    "Media / Publishing", "Sustainability / ESG",
]

CANONICAL_PERSONAS: List[str] = [
    "CIO", "CTO", "CDO", "CISO", "CFO", "COO", "CEO", "CMO", "CHRO",
    "VP Product", "CRO", "VP Engineering", "VP Supply Chain",
    "Head of Procurement", "VP Sales", "IT Manager", "Finance Manager",
    "Operations Manager", "Founder", "Head of Growth",
    "Supply Chain Manager", "Data Scientist / Analytics", "Project Manager",
]

_CANON_IND_LOWER = {c.lower(): c for c in CANONICAL_INDUSTRIES}
_CANON_PER_LOWER = {c.lower(): c for c in CANONICAL_PERSONAS}


class ICPParseResult(BaseModel):
    industries:     List[str] = []
    personas:       List[str] = []
    extra_keywords: List[str] = []   # niche descriptors outside the taxonomy
    seniority:      str = ""         # c-suite | vp | director | manager | ""
    confidence:     float = 0.0

    model_config = {"extra": "ignore"}

    @field_validator("industries", "personas", "extra_keywords", mode="before")
    @classmethod
    def _listify(cls, v):
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v or []

    @field_validator("confidence", mode="before")
    @classmethod
    def _conf(cls, v):
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.0


_SYSTEM = f"""You are an ICP (ideal customer profile) parser for a B2B trade-event
recommendation engine. The user describes who they sell to, in any language or
phrasing. Extract structured targeting data.

CANONICAL INDUSTRIES (map to these EXACT labels; order by how central each is
to the described buyer - the PRIMARY industry must be FIRST):
{", ".join(CANONICAL_INDUSTRIES)}

CANONICAL BUYER ROLES (map to these EXACT labels where possible):
{", ".join(CANONICAL_PERSONAS)}

RULES:
- industries: 1-3 canonical labels, primary first. Only industries of the
  BUYER's organisation, never the seller's product category. Example: "CISO at
  healthcare organisations" -> ["Healthcare / Medtech"] (the buyer works in
  healthcare; do NOT add Cybersecurity just because the role is security).
- personas: canonical role labels. If the stated role has no canonical
  equivalent (e.g. "Head of Perioperative Services"), return the role verbatim
  in Title Case instead - never drop it and never force a wrong label.
- extra_keywords: 0-5 lowercase niche descriptors from the text that a keyword
  search over event listings would benefit from (e.g. "ambulatory surgery",
  "clinical operations"). Only terms actually implied by the input.
- seniority: one of "c-suite", "vp", "director", "manager", or "" if unclear.
- confidence: 0.0-1.0, how unambiguous the input was.
- Input may be misspelled or partial - infer sensibly, never invent industries
  that are not implied.

Return ONLY JSON:
{{"industries": [], "personas": [], "extra_keywords": [], "seniority": "", "confidence": 0.0}}"""


def _normalise(parsed: ICPParseResult) -> ICPParseResult:
    """Snap near-miss labels onto the canonical taxonomy; keep novel roles."""
    industries: list[str] = []
    extra = list(parsed.extra_keywords)
    for ind in parsed.industries:
        canon = _CANON_IND_LOWER.get(ind.strip().lower())
        if canon and canon not in industries:
            industries.append(canon)
        elif ind.strip() and ind.strip().lower() not in [e.lower() for e in extra]:
            # non-canonical industry -> keep as searchable keyword, not a bucket
            extra.append(ind.strip().lower())

    personas: list[str] = []
    for per in parsed.personas:
        canon = _CANON_PER_LOWER.get(per.strip().lower())
        label = canon or per.strip()
        if label and label not in personas:
            personas.append(label)

    return ICPParseResult(
        industries=industries[:3],
        personas=personas[:4],
        extra_keywords=[e for e in extra if e][:5],
        seniority=parsed.seniority,
        confidence=parsed.confidence,
    )


async def parse_icp_text(text: str) -> Optional[ICPParseResult]:
    """
    LLM parse of a free-text buyer description. Returns None when the
    LLM is unavailable/failed - callers fall back to rule-based parsing.
    Results are cached for an hour (typing the same ICP twice is free).
    """
    text = (text or "").strip()
    if len(text) < 4:
        return None

    parsed = await llm.chat_json(
        _SYSTEM,
        f'BUYER DESCRIPTION: "{text[:400]}"',
        label="icp-parser",
        schema=ICPParseResult,
        max_completion_tokens=300,
        temperature=0.0,
        timeout=12,
        cache_ttl=3600,
    )
    if parsed is None:
        return None

    result = _normalise(parsed)
    if not result.industries and not result.personas:
        return None
    logger.info(
        f"ICP parsed via LLM: {text[:60]!r} -> ind={result.industries} "
        f"per={result.personas} extra={result.extra_keywords}"
    )
    return result
