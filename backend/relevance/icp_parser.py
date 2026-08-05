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


class ICPSegmentResult(BaseModel):
    """One persona/industry pair, e.g. {"personas": ["CEO"], "industries": ["Fintech"]}."""
    personas:   List[str] = []
    industries: List[str] = []

    model_config = {"extra": "ignore"}

    @field_validator("personas", "industries", mode="before")
    @classmethod
    def _listify(cls, v):
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v or []


class ICPParseResult(BaseModel):
    industries:     List[str] = []
    personas:       List[str] = []
    extra_keywords: List[str] = []   # niche descriptors outside the taxonomy
    seniority:      str = ""         # c-suite | vp | director | manager | ""
    confidence:     float = 0.0
    # Only populated when the input names 2+ DISTINCT role+vertical pairs
    # ("CEO at BFSI, CIO at Medtech companies"). industries/personas above
    # always stay the flat union of every segment for back-compat; this is
    # the extra pairing info the scorer uses to keep groups from
    # cross-matching. Empty for single-group or role-only/industry-only input.
    segments:       List[ICPSegmentResult] = []

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
- industries: 0-3 canonical labels, primary first. Only industries of the
  BUYER's organisation, never the seller's product category. Example: "CISO at
  healthcare organisations" -> ["Healthcare / Medtech"] (the buyer works in
  healthcare; do NOT add Cybersecurity just because the role is security).
  Return an EMPTY list when the input explicitly says the buyer spans every
  industry / is industry-agnostic (e.g. "CIOs across all industries", "any
  industry", "industry-agnostic", "sold horizontally") - do NOT guess a
  single vertical just to have something to return. An empty industries list
  correctly means "no industry restriction" downstream, not "unparsed."
- Use your general world knowledge to resolve industry jargon, abbreviations,
  regional terms and acronyms into the canonical list - do not require exact
  wording. These are NOT hardcoded anywhere else in the system, so this is the
  only place they get resolved. Examples:
    "BFSI" -> ["Fintech"]                       (Banking, Financial Services & Insurance)
    "FMCG" or "CPG" -> ["Retail / Ecommerce"]    (fast-moving consumer goods)
    "D2C" or "DTC" -> ["Retail / Ecommerce"]     (direct-to-consumer brands)
    "MSME" or "SME" manufacturers -> ["Manufacturing"]
    "ISV" (independent software vendor) -> ["Technology"]
    "GovTech" -> ["Government / Public Sector"]
    "OTT platforms" -> ["Media / Publishing"]
    "Web3" -> ["Fintech"] with extra_keywords ["web3", "crypto"] unless the
    text is clearly about infra/tooling, then ["Technology"]
  These are illustrative, not exhaustive - apply the same reasoning to any
  other acronym, regional term, or industry shorthand you recognise.
- personas: canonical role labels - return ALL roles mentioned, not just the
  first one (e.g. "CIOs and CISOs" -> ["CIO", "CISO"], not just ["CIO"]). If a
  stated role has no canonical equivalent (e.g. "Head of Perioperative
  Services"), return the role verbatim in Title Case instead - never drop it
  and never force a wrong label. Resolve role jargon/abbreviations the same
  way as industries, e.g. "CXO" -> the specific C-suite roles implied by
  context, or ["CEO", "CFO", "CTO", "COO"] if genuinely unspecified; "IT
  Head" -> ["CIO"]; "L&D leaders" -> ["Head of Growth"] only if no closer
  match exists, otherwise keep as verbatim "L&D Leader".
- extra_keywords: 0-5 lowercase niche descriptors from the text that a keyword
  search over event listings would benefit from (e.g. "ambulatory surgery",
  "clinical operations"). Only terms actually implied by the input.
- seniority: one of "c-suite", "vp", "director", "manager", or "" if unclear.
- confidence: 0.0-1.0, how unambiguous the input was.
- Input may be misspelled or partial - infer sensibly, never invent industries
  that are not implied.
- segments: populate ONLY when the input names two or more DISTINCT
  role+vertical pairs that should NOT be cross-matched with each other -
  e.g. "CEO at BFSI companies, CIO at Medtech firms" means find a CEO buyer
  at a BFSI company OR a CIO buyer at a Medtech company, NEVER a CEO at a
  Medtech company. Each segment is {{"personas": [...], "industries": [...]}}
  using the same canonical labels as above.

  HOW TO DECIDE WHERE ONE PAIR ENDS AND THE NEXT BEGINS - read the input as
  a human would, using punctuation, repeated prepositions, and clause
  structure as your evidence, not just presence of "and":
    - A comma, semicolon, or "and also" between two "ROLE at/in VERTICAL"
      clauses is a strong signal of two separate pairs: "CEOs at BFSI firms,
      CIOs at Medtech companies" -> 2 segments.
    - A role preposition ("at", "in", "for", "within") repeated once per
      clause confirms each clause is its own pair: "CTOs in cloud computing
      and Plant Managers in manufacturing" -> 2 segments (the second "in"
      re-anchors a new pair, it does not extend the first).
    - Roles joined by "and"/"&" immediately before ONE shared preposition +
      vertical are ONE pair, not several: "CIOs and CISOs at healthcare
      orgs" -> segments EMPTY, personas=["CIO","CISO"], industries=
      ["Healthcare / Medtech"] (only one preposition, one vertical - no
      pairing ambiguity to resolve).
    - Verticals joined by "and" immediately after ONE shared role+preposition
      are also ONE pair: "CIOs at fintech and healthcare companies" ->
      segments EMPTY, personas=["CIO"], industries=["Fintech","Healthcare /
      Medtech"] (one role, two verticals it's equally happy with - not two
      role/vertical pairings).
    - GENUINE ambiguity ("CEOs and CIOs at fintech and healthcare firms" -
      unclear whether every role should pair with every vertical, or
      role[i] pairs with vertical[i]): DO NOT force a guess into segments.
      Leave segments EMPTY and return the flat union instead - an
      incorrectly split pairing is worse than no pairing, since it would
      wrongly exclude combinations the buyer actually wants. Only emit
      segments when the clause structure makes the pairing unambiguous.
    - Leave segments EMPTY when the buyer is industry-agnostic (no verticals
      to pair against) even if multiple roles are listed.
  When segments IS populated, industries/personas at the top level must
  still be the flat union of every persona/industry across all segments.
  Example: "CEO at BFSI, CIO at Medtech" ->
  {{"industries": ["Fintech", "Healthcare / Medtech"], "personas": ["CEO", "CIO"],
    "segments": [{{"personas": ["CEO"], "industries": ["Fintech"]}},
                 {{"personas": ["CIO"], "industries": ["Healthcare / Medtech"]}}]}}

Return ONLY JSON:
{{"industries": [], "personas": [], "extra_keywords": [], "seniority": "", "confidence": 0.0, "segments": []}}"""


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

    def _canon_persona(p: str) -> str:
        canon = _CANON_PER_LOWER.get(p.strip().lower())
        return canon or p.strip()

    segments: list[ICPSegmentResult] = []
    for seg in parsed.segments:
        seg_industries = list(dict.fromkeys(
            _CANON_IND_LOWER.get(i.strip().lower(), i.strip()) for i in seg.industries if i.strip()
        ))
        seg_personas = list(dict.fromkeys(_canon_persona(p) for p in seg.personas if p.strip()))
        # A pairing needs both sides to mean anything - a segment with only
        # a persona or only an industry can't be scored any differently
        # from the flat behaviour, so it isn't worth the added restriction.
        if seg_industries and seg_personas:
            segments.append(ICPSegmentResult(personas=seg_personas, industries=seg_industries))

    return ICPParseResult(
        industries=industries[:3],
        personas=personas[:4],
        extra_keywords=[e for e in extra if e][:5],
        seniority=parsed.seniority,
        confidence=parsed.confidence,
        segments=segments[:5],
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
        max_completion_tokens=450,
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
        f"per={result.personas} extra={result.extra_keywords} "
        f"segments={[(s.personas, s.industries) for s in result.segments]}"
    )
    return result
