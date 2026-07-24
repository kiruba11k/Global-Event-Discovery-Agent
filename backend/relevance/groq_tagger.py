"""
relevance/groq_tagger.py  —  Groq LLM-powered event tagging & keyword extraction

Two functions replace the hardcoded keyword matching:

  extract_search_keywords(company_desc, industries, personas, event_types)
    → list[str]  — event search terms derived from ICP form inputs
    Called ONCE per search.

  infer_event_tags_batch(events)
    → dict[event_id, str]  — industry tags for a batch of events
    Called ONCE after fetching events, not per-event.

ANTI-HALLUCINATION DESIGN:
  ✅ Temperature=0 for deterministic output
  ✅ Fixed taxonomy — LLM must choose FROM a predefined list, cannot invent new industries
  ✅ Evidence requirement — LLM must cite which words in the text justify each tag
  ✅ Pydantic validation of every response — invalid schema → fallback
  ✅ Length/content guards — reject responses that exceed schema bounds
  ✅ Forbidden phrases — prompt explicitly lists what NOT to do
  ✅ Synchronous fallback — hardcoded logic if Groq is unavailable/fails
"""
from __future__ import annotations

import asyncio
import json
import re
from functools import lru_cache
from typing import Optional

from loguru import logger
from pydantic import BaseModel, ValidationError, field_validator

from relevance.llm_client import llm

# ── Fixed taxonomy — LLM must pick from this list ONLY ─────────────
# Adding, removing, or renaming categories here automatically updates
# both the prompt and the validator.
INDUSTRY_TAXONOMY: list[str] = [
    "Technology",
    "AI / Machine Learning",
    "Cloud Computing",
    "Cybersecurity",
    "Manufacturing",
    "Logistics / Supply Chain",
    "Healthcare / Medtech",
    "Fintech",
    "Retail / Ecommerce",
    "Energy / Cleantech",
    "Data & Analytics",
    "HR Tech",
    "Marketing / Adtech",
    "Startup / VC",
    "Real Estate / PropTech",
    "Education / EdTech",
    "Legal Tech",
    "Automotive",
    "Agriculture / AgriTech",
    "Sustainability / ESG",
    "Telecommunications",
    "Media / Publishing",
    "Food & Beverage",
    "Fashion / Apparel",
    "Construction / Infrastructure",
    "Government / Public Sector",
    "Defence / Aerospace",
    "Mining / Resources",
    "Sports Technology",
    "Travel / Hospitality",
    "Business Events",  # generic fallback
]

# Lowercase set for fast validation
_TAXONOMY_LOWER: frozenset[str] = frozenset(t.lower() for t in INDUSTRY_TAXONOMY)

# Taxonomy joined for prompt injection
_TAXONOMY_STR: str = "\n".join(f"  - {t}" for t in INDUSTRY_TAXONOMY)

# Same fixed-taxonomy anti-hallucination pattern as INDUSTRY_TAXONOMY above,
# reusing the canonical persona list icp_parser.py already normalises
# user-typed designations against — so an inferred persona always matches
# something the ICP form's own parser can recognise.
from relevance.icp_parser import CANONICAL_PERSONAS  # noqa: E402

_PERSONA_TAXONOMY_LOWER: frozenset[str] = frozenset(p.lower() for p in CANONICAL_PERSONAS)
_PERSONA_TAXONOMY_STR: str = "\n".join(f"  - {p}" for p in CANONICAL_PERSONAS)


# ── Pydantic schemas ────────────────────────────────────────────────

class ICPAttributes(BaseModel):
    """
    Structured attributes extracted from the ICP buyer description.
    Used for seniority-aware scoring and per-API query specialisation.
    No hallucinations: all fields must be inferrable from the input text.
    """
    industry:     str = "Business Events"   # primary industry (from taxonomy)
    persona:      str = "Business Leader"   # job title / role (e.g. "CFO", "VP Engineering")
    seniority:    str = "unknown"           # c-suite | vp | director | manager | practitioner | unknown
    company_size: str = "any"               # enterprise | mid-market | smb | startup | any
    function:     str = "other"             # finance | technology | operations | sales | hr | marketing | other

    model_config = {"extra": "ignore"}

    @field_validator("seniority")
    @classmethod
    def validate_seniority(cls, v):
        allowed = {"c-suite","vp","director","manager","practitioner","unknown"}
        return v.lower() if v.lower() in allowed else "unknown"

    @field_validator("company_size")
    @classmethod
    def validate_company_size(cls, v):
        allowed = {"enterprise","mid-market","smb","startup","any"}
        return v.lower() if v.lower() in allowed else "any"


class SearchKeywordsResponse(BaseModel):
    """
    Enriched keyword extraction response.

    Three keyword sets for different query purposes:
      industry_keywords  → broad event discovery (SerpAPI + EventsEye DB)
      persona_keywords   → role-specific events missed by industry search
      api_keywords       → short, API-native terms for TM / PredictHQ

    icp_attributes captures structured profile signals for scoring.
    reasoning must quote specific input words justifying each keyword.
    """
    industry_keywords: list[str] = []            # 3–5 broad industry event terms
    persona_keywords:  list[str] = []            # 2–4 persona/seniority-specific terms
    api_keywords:      list[str] = []            # 2–4 short terms native to TM/PHQ APIs
    icp_attributes:    ICPAttributes = ICPAttributes()
    reasoning:         str = ""                  # optional — never reject a payload for this

    model_config = {"extra": "ignore"}

    @field_validator("industry_keywords", "persona_keywords", "api_keywords")
    @classmethod
    def validate_keywords(cls, v: list[str]) -> list[str]:
        validated = []
        for kw in v:
            kw = kw.strip()
            if len(kw) < 4 or len(kw) > 80:
                continue
            if any(bad in kw.lower() for bad in ["http", "www.", "ltd", "inc.", "corp.", ".com"]):
                continue
            validated.append(kw)
        return validated[:6]

    # Backward compat: callers that only want a flat keyword list
    @property
    def keywords(self) -> list[str]:
        """Deduplicated union of all keyword sets."""
        seen: set[str] = set()
        result = []
        for kw in self.industry_keywords + self.persona_keywords + self.api_keywords:
            if kw.lower() not in seen:
                seen.add(kw.lower())
                result.append(kw)
        return result[:10]


class EventTagItem(BaseModel):
    """Industry tags for a single event."""
    event_id:   str
    tags:       list[str] = []  # must all be from taxonomy
    evidence:   str = ""        # which words in the event title/desc justify this

    model_config = {"extra": "ignore"}

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        validated = []
        for tag in v:
            tag = tag.strip()
            if tag.lower() not in _TAXONOMY_LOWER:
                logger.debug(f"Rejected hallucinated tag: {tag!r}")
                continue  # silently drop invented tags
            # Find the canonical-cased version
            for canonical in INDUSTRY_TAXONOMY:
                if canonical.lower() == tag.lower():
                    validated.append(canonical)
                    break
        return list(dict.fromkeys(validated))[:5]  # deduplicate, limit 5


class EventTagsResponse(BaseModel):
    """Batch response for event tag inference."""
    events: list[EventTagItem] = []

    model_config = {"extra": "ignore"}


class EventPersonaItem(BaseModel):
    """Inferred attending designations for a single event — same
    anti-hallucination shape as EventTagItem, validated against
    CANONICAL_PERSONAS instead of INDUSTRY_TAXONOMY."""
    event_id:   str
    personas:   list[str] = []
    evidence:   str = ""

    model_config = {"extra": "ignore"}

    @field_validator("personas")
    @classmethod
    def validate_personas(cls, v: list[str]) -> list[str]:
        validated = []
        for p in v:
            p = p.strip()
            if p.lower() not in _PERSONA_TAXONOMY_LOWER:
                logger.debug(f"Rejected hallucinated persona: {p!r}")
                continue
            for canonical in CANONICAL_PERSONAS:
                if canonical.lower() == p.lower():
                    validated.append(canonical)
                    break
        return list(dict.fromkeys(validated))[:5]


class EventPersonasResponse(BaseModel):
    """Batch response for event persona/designation inference."""
    events: list[EventPersonaItem] = []

    model_config = {"extra": "ignore"}


# ══════════════════════════════════════════════════════════════════════
# FUNCTION 1: extract_search_keywords
# Replaces _extract_desc_keywords() in icp_query_builder.py
# ══════════════════════════════════════════════════════════════════════

_KEYWORD_SYSTEM = """You are a B2B event research analyst. Your job is to generate event search terms and extract structured buyer profile attributes.

STRICT RULES — violating ANY rule makes your response invalid:
  1. ONLY derive output from information EXPLICITLY present in the user input.
  2. NEVER invent industries, products, technologies, or attributes not mentioned.
  3. Each keyword must be a real event type (e.g. "AI conference", "logistics expo").
  4. Do NOT include company names, personal names, URLs, or product names in keywords.
  5. The "reasoning" field must quote the EXACT phrases from the input that justify each decision.
  6. seniority must be one of: c-suite | vp | director | manager | practitioner | unknown
  7. company_size must be one of: enterprise | mid-market | smb | startup | any
  8. function must be one of: finance | technology | operations | sales | hr | marketing | other

Return ONLY this JSON (no text before or after, no markdown):
{
  "industry_keywords": ["broad industry event term 1", "broad term 2", "broad term 3"],
  "persona_keywords": ["CTO technology summit", "VP Engineering conference"],
  "api_keywords": ["Conference", "Technology Expo"],
  "icp_attributes": {
    "industry": "Technology",
    "persona": "CTO",
    "seniority": "c-suite",
    "company_size": "enterprise",
    "function": "technology"
  },
  "reasoning": "industry_keywords: derived from '...'. persona_keywords: derived from '...'"
}

KEYWORD RULES:
  industry_keywords: 3–5 terms, broad enough to find many events — include the industry + event type
  persona_keywords: 2–4 terms, combine the job role with event type — find role-specific events missed by industry search
  api_keywords: 2–4 short native terms for Ticketmaster/PredictHQ (these APIs prefer single-word or 2-word queries)"""


async def extract_search_keywords(
    company_desc:  str,
    industries:    list[str],
    personas:      list[str],
    event_types:   list[str],
) -> "SearchKeywordsResponse":
    """
    Use Groq LLM to extract targeted event search keywords from ICP form inputs.

    Works for ANY company description — no hardcoded keyword lists needed.
    Falls back to safe defaults if Groq is unavailable.

    Examples:
      "AR/VR training for factory floor managers" →
        ["manufacturing technology conference", "industrial training expo",
         "AR VR enterprise summit", "factory automation conference"]

      "Carbon credit trading for ESG-focused CFOs" →
        ["sustainability conference", "ESG summit", "carbon trading expo",
         "cleantech conference", "CFO finance summit"]
    """
    # Build the user prompt from ALL ICP form inputs
    parts = []
    if company_desc.strip():
        parts.append(f"Company description: {company_desc.strip()[:600]}")
    if industries:
        parts.append(f"Target industries: {', '.join(industries)}")
    if personas:
        parts.append(f"Target buyer roles: {', '.join(personas[:5])}")
    if event_types:
        parts.append(f"Preferred event formats: {', '.join(event_types)}")

    if not parts:
        return _fallback_keywords(industries)

    user_prompt = (
        "Generate B2B event search terms for this company profile:\n\n"
        + "\n".join(parts)
        + "\n\nReturn search terms that would find relevant industry events "
          "where this company's target buyers attend."
    )

    parsed = await llm.chat_json(
        _KEYWORD_SYSTEM,
        user_prompt,
        label="keyword_extractor",
        schema=SearchKeywordsResponse,
        max_completion_tokens=800,
        temperature=0,
        timeout=15,
        cache_ttl=3600,   # identical ICP inputs must not re-spend tokens
    )
    if parsed is None or not parsed.industry_keywords:
        logger.warning("extract_search_keywords: no usable LLM response — using fallback")
        return _make_fallback_response(industries, personas, company_desc)

    logger.info(
        f"Groq keyword extraction: industry={parsed.industry_keywords} "
        f"persona={parsed.persona_keywords} api={parsed.api_keywords} | "
        f"seniority={parsed.icp_attributes.seniority} "
        f"company_size={parsed.icp_attributes.company_size}"
    )
    return parsed


def _fallback_keywords(industries: list[str], desc: str = "") -> list[str]:
    """
    Safe hardcoded fallback — returns reasonable defaults even without Groq.
    Used when Groq is unavailable or returns invalid output.
    """
    _IND_KW = {
        "Technology":           "technology conference",
        "AI / Machine Learning": "AI artificial intelligence conference",
        "Cloud Computing":      "cloud computing summit",
        "Cybersecurity":        "cybersecurity conference",
        "Manufacturing":        "manufacturing expo",
        "Logistics / Supply Chain": "supply chain logistics conference",
        "Healthcare / Medtech": "healthcare technology summit",
        "Fintech":              "fintech financial technology conference",
        "Retail / Ecommerce":   "retail ecommerce summit",
        "Energy / Cleantech":   "energy cleantech conference",
        "Data & Analytics":     "data analytics summit",
        "HR Tech":              "HR technology talent conference",
        "Marketing / Adtech":   "marketing technology conference",
    }
    kws = [_IND_KW.get(ind, f"{ind.lower()} conference") for ind in industries[:4]]
    # Also check description for obvious matches
    if desc:
        d = desc.lower()
        extras = [
            ("supply chain",    "supply chain conference"),
            ("legal",           "legal technology conference"),
            ("sustainability",  "sustainability ESG conference"),
            ("drone",           "IoT drone technology summit"),
            ("carbon",          "sustainability carbon conference"),
            ("ar vr",           "enterprise technology summit"),
            ("real estate",     "proptech real estate conference"),
        ]
        for kw, term in extras:
            if kw in d:
                kws.insert(0, term)
    return list(dict.fromkeys(kws))[:6] or ["technology conference", "business summit"]


def _make_fallback_response(
    industries: list[str],
    personas:   list[str],
    desc:       str = "",
) -> "SearchKeywordsResponse":
    """
    Build a complete SearchKeywordsResponse without Groq.
    Deterministic and safe — no hallucinations possible.
    """
    ind_kws  = _fallback_keywords(industries, desc)
    # Persona keywords: combine first persona with industry
    per_kws  = []
    for p in (personas or [])[:2]:
        p_clean = p.strip().split("/")[0].strip()  # "CIO / CTO" → "CIO"
        if ind_kws:
            per_kws.append(f"{p_clean} {ind_kws[0]}")
        per_kws.append(f"{p_clean} conference")
    per_kws = list(dict.fromkeys(per_kws))[:3]

    api_kws  = [k.split()[0].title() for k in ind_kws[:2]]  # "fintech conference" → "Fintech"

    # Infer seniority from persona text
    seniority = "unknown"
    persona_str = " ".join(personas or []).lower()
    if any(t in persona_str for t in ["ceo","cfo","cio","cto","coo","cxo","chief","president"]):
        seniority = "c-suite"
    elif any(t in persona_str for t in ["vp","vice president","vice-president"]):
        seniority = "vp"
    elif "director" in persona_str:
        seniority = "director"
    elif "manager" in persona_str:
        seniority = "manager"

    # Infer function
    function = "other"
    if any(t in persona_str for t in ["cio","cto","engineer","developer","technical","it ","tech"]):
        function = "technology"
    elif any(t in persona_str for t in ["cfo","finance","financial","treasury"]):
        function = "finance"
    elif any(t in persona_str for t in ["coo","operations","supply","logistics","procurement"]):
        function = "operations"
    elif any(t in persona_str for t in ["cmo","marketing","growth","demand"]):
        function = "marketing"
    elif any(t in persona_str for t in ["chro","hr","people","talent","recruiting"]):
        function = "hr"

    attrs = ICPAttributes(
        industry     = industries[0] if industries else "Business Events",
        persona      = personas[0].split("/")[0].strip() if personas else "Business Leader",
        seniority    = seniority,
        company_size = "any",
        function     = function,
    )
    return SearchKeywordsResponse(
        industry_keywords = ind_kws,
        persona_keywords  = per_kws or [f"{attrs.persona} conference"],
        api_keywords      = api_kws or ["Conference"],
        icp_attributes    = attrs,
        reasoning         = "fallback: derived from industries and personas fields",
    )


# ══════════════════════════════════════════════════════════════════════
# FUNCTION 2: infer_event_tags_batch
# Replaces _infer_tags() in serpapi_events.py
# ══════════════════════════════════════════════════════════════════════

_TAGS_SYSTEM = f"""You are an event industry classifier. Classify events into industry categories.

STRICT RULES — violating ANY rule makes your response invalid:
  1. You MUST ONLY use categories from this exact list:
{_TAXONOMY_STR}

  2. NEVER invent or use any category not in the list above.
  3. ONLY assign a category if there is explicit textual evidence in the event title or description.
  4. If the event text is ambiguous, assign "Business Events" rather than guessing.
  5. Maximum 3 categories per event.
  6. The "evidence" field must quote the EXACT words from the event text that justify the category.
  7. Do NOT assign categories based on what seems likely — only from what is written.

Return ONLY this JSON (no text before or after):
{{
  "events": [
    {{
      "event_id": "...",
      "tags": ["Category1", "Category2"],
      "evidence": "Category1 is justified by the phrase '...' in the title/description"
    }}
  ]
}}"""


async def infer_event_tags_batch(
    events: list[dict],  # list of {"id": str, "title": str, "description": str, "query": str}
    batch_size: int = 20,
) -> dict[str, str]:
    """
    Use Groq LLM to infer industry tags for a batch of events.

    Input:  list of {"id", "title", "description", "query"}
    Output: dict {event_id → comma-separated taxonomy tags}

    Anti-hallucination:
      - LLM must pick from INDUSTRY_TAXONOMY only
      - Must quote evidence from the event text
      - Pydantic validates every tag against the taxonomy
      - Invented categories are silently dropped

    Falls back to simple text matching if Groq unavailable.
    """
    if not events:
        return {}

    results: dict[str, str] = {}

    # Process in batches of batch_size
    for i in range(0, len(events), batch_size):
        chunk = events[i: i + batch_size]

        # Build user prompt with just enough context
        events_text = json.dumps([
            {
                "event_id":    ev["id"],
                "title":       ev["title"][:200],
                "description": ev.get("description", "")[:300],
            }
            for ev in chunk
        ], indent=2)

        user_prompt = (
            f"Classify the following {len(chunk)} events into industry categories.\n"
            "Use ONLY the allowed taxonomy. Quote evidence from the event text.\n\n"
            f"EVENTS:\n{events_text}"
        )

        parsed = await llm.chat_json(
            _TAGS_SYSTEM,
            user_prompt,
            label=f"event_tagger_batch_{i}",
            schema=EventTagsResponse,
            max_completion_tokens=800,
            temperature=0,
            timeout=15,
            cache_ttl=3600,
        )

        if parsed is None:
            # Fallback for this chunk (Groq unavailable / failed / unparseable)
            for ev in chunk:
                results[ev["id"]] = _fallback_infer_tags(
                    ev.get("title", "") + " " + ev.get("description", ""),
                    ev.get("query", ""),
                )
            continue

        accepted = 0; dropped = 0
        for item in parsed.events:
            if not item.tags:
                # No valid taxonomy tags → use fallback for this event
                ev_data = next((e for e in chunk if e["id"] == item.event_id), None)
                if ev_data:
                    results[item.event_id] = _fallback_infer_tags(
                        ev_data.get("title", "") + " " + ev_data.get("description", ""),
                        ev_data.get("query", ""),
                    )
                dropped += 1
            else:
                results[item.event_id] = ", ".join(item.tags)
                accepted += 1
        logger.info(
            f"Groq event tagging batch {i//batch_size + 1}: "
            f"{accepted} tagged, {dropped} fell back, "
            f"{len(chunk) - accepted - dropped} missing"
        )

    # Fill in any events that got no result
    for ev in events:
        if ev["id"] not in results:
            results[ev["id"]] = _fallback_infer_tags(
                ev.get("title", "") + " " + ev.get("description", ""),
                ev.get("query", ""),
            )

    return results


# ══════════════════════════════════════════════════════════════════════
# FUNCTION 3: infer_event_personas_batch
# Fills audience_personas for events where it's empty — the actual data
# gap behind weak rule-based + semantic persona matching, see
# scorer.py's PERSONA_UNKNOWN_PENALTY. Only INFERS from what the event
# text already implies (e.g. "CIO Summit" → CIO); never invents a
# designation the text gives no evidence for.
# ══════════════════════════════════════════════════════════════════════

_PERSONAS_SYSTEM = f"""You are a B2B event analyst. Infer which buyer designations (job roles) are likely to attend each event, based ONLY on its title and description.

STRICT RULES — violating ANY rule makes your response invalid:
  1. You MUST ONLY use designations from this exact list:
{_PERSONA_TAXONOMY_STR}

  2. NEVER invent or use any designation not in the list above.
  3. Only assign a designation if the event title/description gives real evidence
     it's relevant to that role (explicit role mention, or a clear functional
     theme — e.g. "Cybersecurity Summit" implies CISO/CIO, "Supply Chain Expo"
     implies VP Supply Chain/COO). Do not guess from weak/generic wording.
  4. If there's no reasonable evidence for any specific role, return an empty list —
     do NOT default to a generic executive role just to have an answer.
  5. Maximum 4 designations per event.
  6. The "evidence" field must quote or closely paraphrase the exact words that justify each designation.

Return ONLY this JSON (no text before or after):
{{
  "events": [
    {{
      "event_id": "...",
      "personas": ["CISO", "CIO"],
      "evidence": "explicit cybersecurity leadership theme in the title"
    }}
  ]
}}"""


async def infer_event_personas_batch(
    events: list[dict],  # list of {"id": str, "title": str, "description": str, "industry_tags": str}
    batch_size: int = 20,
) -> dict[str, str]:
    """
    Use Groq/OpenAI to infer likely attending designations for events
    whose audience_personas is currently empty. Same anti-hallucination
    shape as infer_event_tags_batch — fixed taxonomy, evidence required,
    Pydantic-validated, silent fallback on failure.

    Output: dict {event_id → comma-separated CANONICAL_PERSONAS string}.
    Callers should only write this into audience_personas when the
    result is non-empty — an empty inference means "no confident
    evidence," not "definitely no one relevant attends."
    """
    if not events:
        return {}

    results: dict[str, str] = {}

    for i in range(0, len(events), batch_size):
        chunk = events[i: i + batch_size]

        events_text = json.dumps([
            {
                "event_id":     ev["id"],
                "title":        ev["title"][:200],
                "description":  ev.get("description", "")[:300],
                "industry_tags": ev.get("industry_tags", "")[:150],
            }
            for ev in chunk
        ], indent=2)

        user_prompt = (
            f"Infer attending designations for the following {len(chunk)} events.\n"
            "Use ONLY the allowed designation list. Quote evidence from the event text.\n\n"
            f"EVENTS:\n{events_text}"
        )

        parsed = await llm.chat_json(
            _PERSONAS_SYSTEM,
            user_prompt,
            label=f"event_persona_tagger_batch_{i}",
            schema=EventPersonasResponse,
            max_completion_tokens=800,
            temperature=0,
            timeout=15,
            cache_ttl=3600,
        )

        if parsed is None:
            for ev in chunk:
                results[ev["id"]] = _fallback_infer_personas(
                    ev.get("title", "") + " " + ev.get("description", "")
                )
            continue

        accepted = 0; empty = 0
        for item in parsed.events:
            if item.personas:
                results[item.event_id] = ", ".join(item.personas)
                accepted += 1
            else:
                empty += 1
        logger.info(
            f"Groq persona tagging batch {i//batch_size + 1}: "
            f"{accepted} tagged, {empty} no-confident-evidence"
        )

    for ev in events:
        if ev["id"] not in results:
            results[ev["id"]] = _fallback_infer_personas(
                ev.get("title", "") + " " + ev.get("description", "")
            )

    return results


def _fallback_infer_personas(text: str) -> str:
    """
    Simple keyword-based persona inference — used when the LLM is
    unavailable. Deliberately conservative: only fires on strong,
    unambiguous role/theme signals, returns "" (no guess) otherwise.
    """
    t = text.lower()
    matched: list[str] = []
    checks = [
        (["cio", "chief information officer", "it leadership"], "CIO"),
        (["cto", "chief technology officer", "engineering leadership"], "CTO"),
        (["ciso", "cybersecurity leadership", "chief information security"], "CISO"),
        (["cfo", "chief financial officer", "finance leadership"], "CFO"),
        (["coo", "chief operating officer", "operations leadership"], "COO"),
        (["ceo", "chief executive officer"], "CEO"),
        (["cmo", "chief marketing officer", "marketing leadership"], "CMO"),
        (["chro", "chief human resources", "hr leadership", "people leadership"], "CHRO"),
        (["cdo", "chief data officer", "data leadership"], "CDO"),
        (["supply chain", "logistics leadership", "procurement"], "VP Supply Chain"),
        (["vp engineering", "engineering vp"], "VP Engineering"),
        (["vp sales", "sales leadership"], "VP Sales"),
        (["founder", "startup leadership"], "Founder"),
    ]
    for kws, persona in checks:
        if any(kw in t for kw in kws) and persona not in matched:
            matched.append(persona)
    return ", ".join(matched[:4])


def _fallback_infer_tags(text: str, query: str = "") -> str:
    """
    Simple text-based tag inference — used when Groq is unavailable.
    Checks for taxonomy keywords in the combined text.
    Returns a comma-separated string of matched taxonomy items.
    """
    combined = (text + " " + query).lower()
    matched: list[str] = []

    checks = [
        (["ai", "artificial intelligence", "machine learning", "deep learning", "neural"],
         "AI / Machine Learning"),
        (["cloud", "saas", "paas", "kubernetes", "aws", "azure", "gcp", "devops"],
         "Cloud Computing"),
        (["cyber", "infosec", "zero trust", "ransomware", "data breach", "soc "],
         "Cybersecurity"),
        (["fintech", "banking", "payments", "blockchain", "crypto", "insurtech", "regtech"],
         "Fintech"),
        (["health", "medical", "medtech", "pharma", "biotech", "clinical", "hospital"],
         "Healthcare / Medtech"),
        (["manufactur", "industrial", "factory", "cnc", "robotics", "automation", "industry 4"],
         "Manufacturing"),
        (["logistic", "supply chain", "freight", "warehouse", "procurement", "last mile"],
         "Logistics / Supply Chain"),
        (["retail", "ecommerce", "e-commerce", "omnichannel", "d2c", "fmcg"],
         "Retail / Ecommerce"),
        (["energy", "renewable", "solar", "wind", "oil", "gas", "power", "utility"],
         "Energy / Cleantech"),
        (["sustainab", "esg", "carbon", "climate", "green", "net zero", "circular"],
         "Sustainability / ESG"),
        (["data analytics", "big data", "business intelligence", "data engineer"],
         "Data & Analytics"),
        (["hr tech", "talent", "workforce", "recruitment", "people ops", "payroll"],
         "HR Tech"),
        (["marketing", "adtech", "martech", "demand gen", "digital marketing"],
         "Marketing / Adtech"),
        (["startup", "venture capital", "vc ", "founder", "seed round", "pitch"],
         "Startup / VC"),
        (["real estate", "proptech", "property", "construction", "architecture"],
         "Real Estate / PropTech"),
        (["edtech", "education", "e-learning", "university", "academic", "training"],
         "Education / EdTech"),
        (["legal", "legaltech", "law firm", "compliance", "regulatory", "governance"],
         "Legal Tech"),
        (["automotive", "vehicle", "electric vehicle", "ev ", "mobility", "car"],
         "Automotive"),
        (["agritech", "agriculture", "farming", "crop", "aquaculture", "food tech"],
         "Agriculture / AgriTech"),
        (["telecom", "5g", "connectivity", "network", "broadband", "isp"],
         "Telecommunications"),
        (["media", "publishing", "broadcast", "content", "streaming", "advertising"],
         "Media / Publishing"),
        (["food", "beverage", "catering", "hospitality", "restaurant", "fmcg"],
         "Food & Beverage"),
        (["fashion", "textile", "apparel", "clothing", "luxury", "retail fashion"],
         "Fashion / Apparel"),
        (["construction", "infrastructure", "civil", "building", "smart city"],
         "Construction / Infrastructure"),
        (["government", "public sector", "smart gov", "civic tech", "e-gov"],
         "Government / Public Sector"),
        (["defence", "aerospace", "defense", "military", "space", "aviation"],
         "Defence / Aerospace"),
        (["mining", "mineral", "ore", "metals", "quarry", "resources"],
         "Mining / Resources"),
        (["travel", "tourism", "hospitality", "airline", "hotel", "destination"],
         "Travel / Hospitality"),
        (["tech", "technology", "digital", "software", "developer", "it "],
         "Technology"),
    ]

    for keywords, tag in checks:
        if any(kw in combined for kw in keywords) and tag not in matched:
            matched.append(tag)

    return ", ".join(matched[:4]) if matched else "Business Events"


# ══════════════════════════════════════════════════════════════════════
# SYNC WRAPPER for use in non-async contexts (e.g. icp_query_builder)
# ══════════════════════════════════════════════════════════════════════

def extract_search_keywords_sync(
    company_desc: str,
    industries:   list[str],
    personas:     list[str],
    event_types:  list[str],
) -> list[str]:
    """
    Synchronous wrapper around extract_search_keywords.
    Used in icp_query_builder.py which may run in sync context.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're inside an async context — can't run another event loop
            # Return fallback immediately
            logger.debug("extract_search_keywords_sync: event loop running, using fallback")
            return _make_fallback_response(industries, personas, company_desc)
        return loop.run_until_complete(
            extract_search_keywords(company_desc, industries, personas, event_types)
        )
    except Exception as exc:
        logger.warning(f"extract_search_keywords_sync: {exc} — using fallback")
        return _make_fallback_response(industries, personas, company_desc)
