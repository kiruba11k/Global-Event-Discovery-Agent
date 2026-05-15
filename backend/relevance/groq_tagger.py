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


# ── Pydantic schemas ────────────────────────────────────────────────

class SearchKeywordsResponse(BaseModel):
    """Schema for extract_search_keywords response."""
    keywords: list[str]
    reasoning: str  # required: LLM must justify each keyword

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("keywords list must not be empty")
        if len(v) > 10:
            raise ValueError(f"Too many keywords: {len(v)} > 10")
        validated = []
        for kw in v:
            kw = kw.strip()
            if len(kw) < 5:
                continue  # too short to be useful
            if len(kw) > 80:
                raise ValueError(f"Keyword too long: {kw!r}")
            # Reject keywords that look like hallucinated company names or URLs
            if any(bad in kw.lower() for bad in ["http", "www.", "ltd", "inc.", "corp."]):
                continue
            validated.append(kw)
        if not validated:
            raise ValueError("No valid keywords after filtering")
        return validated[:8]


class EventTagItem(BaseModel):
    """Industry tags for a single event."""
    event_id:   str
    tags:       list[str]  # must all be from taxonomy
    evidence:   str        # which words in the event title/desc justify this

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        if len(v) > 5:
            raise ValueError(f"Too many tags: {len(v)} > 5")
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
    events: list[EventTagItem]


# ── Groq client ─────────────────────────────────────────────────────

def _get_groq_client():
    """Get Groq client using settings. Returns None if no API key."""
    try:
        from config import get_settings
        from groq import Groq
        s = get_settings()
        if not s.groq_api_key:
            return None
        return Groq(api_key=s.groq_api_key)
    except Exception:
        return None


async def _call_groq(
    client,
    system_prompt: str,
    user_prompt:   str,
    label:         str = "groq_tagger",
) -> Optional[str]:
    """Call Groq with temperature=0, JSON mode, 10s timeout."""
    try:
        resp = await asyncio.wait_for(
            asyncio.to_thread(
                client.chat.completions.create,
                model           = "llama-3.3-70b-versatile",
                messages        = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature     = 0,       # deterministic — no creative hallucination
                max_tokens      = 800,
                response_format = {"type": "json_object"},
            ),
            timeout=10.0,
        )
        return resp.choices[0].message.content
    except asyncio.TimeoutError:
        logger.warning(f"{label}: timed out (10s)")
    except Exception as exc:
        logger.warning(f"{label}: {exc}")
    return None


# ══════════════════════════════════════════════════════════════════════
# FUNCTION 1: extract_search_keywords
# Replaces _extract_desc_keywords() in icp_query_builder.py
# ══════════════════════════════════════════════════════════════════════

_KEYWORD_SYSTEM = """You are a B2B event research analyst. Your job is to generate event search terms.

STRICT RULES — violating ANY rule makes your response invalid:
  1. ONLY derive search terms from information explicitly present in the user's text.
  2. NEVER invent industries, products, or technologies not mentioned.
  3. Each search term must be a real event type that exists (e.g. "AI conference", "logistics expo").
  4. Maximum 8 search terms.
  5. Each search term must be 5–80 characters.
  6. Do NOT include company names, personal names, URLs, or product names.
  7. The "reasoning" field must quote the specific words from the user input that justify each keyword.

Return ONLY this JSON (no text before or after):
{
  "keywords": ["keyword 1", "keyword 2", ...],
  "reasoning": "keyword 1 is justified by the phrase '...' in the input. keyword 2 is justified by..."
}"""


async def extract_search_keywords(
    company_desc:  str,
    industries:    list[str],
    personas:      list[str],
    event_types:   list[str],
) -> list[str]:
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
    client = _get_groq_client()

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

    if not client:
        logger.debug("extract_search_keywords: Groq not available → using fallback")
        return _fallback_keywords(industries, company_desc)

    raw = await _call_groq(client, _KEYWORD_SYSTEM, user_prompt, label="keyword_extractor")
    if not raw:
        return _fallback_keywords(industries, company_desc)

    try:
        parsed = SearchKeywordsResponse.model_validate_json(raw)
        logger.info(
            f"Groq keyword extraction: {len(parsed.keywords)} keywords | "
            f"reasoning excerpt: {parsed.reasoning[:80]}..."
        )
        return parsed.keywords
    except (ValidationError, ValueError, Exception) as exc:
        logger.warning(f"extract_search_keywords validation failed: {exc} — using fallback")
        return _fallback_keywords(industries, company_desc)


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

    client = _get_groq_client()
    results: dict[str, str] = {}

    # Process in batches of batch_size
    for i in range(0, len(events), batch_size):
        chunk = events[i: i + batch_size]

        if not client:
            # Fallback: fast text-based inference
            for ev in chunk:
                results[ev["id"]] = _fallback_infer_tags(
                    ev.get("title", "") + " " + ev.get("description", ""),
                    ev.get("query", ""),
                )
            continue

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

        raw = await _call_groq(client, _TAGS_SYSTEM, user_prompt, label=f"event_tagger_batch_{i}")

        if not raw:
            # Fallback for this chunk
            for ev in chunk:
                results[ev["id"]] = _fallback_infer_tags(
                    ev.get("title", "") + " " + ev.get("description", ""),
                    ev.get("query", ""),
                )
            continue

        try:
            parsed = EventTagsResponse.model_validate_json(raw)
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
        except (ValidationError, ValueError, Exception) as exc:
            logger.warning(f"infer_event_tags_batch validation error: {exc} — fallback for chunk")
            for ev in chunk:
                results[ev["id"]] = _fallback_infer_tags(
                    ev.get("title", "") + " " + ev.get("description", ""),
                    ev.get("query", ""),
                )

    # Fill in any events that got no result
    for ev in events:
        if ev["id"] not in results:
            results[ev["id"]] = _fallback_infer_tags(
                ev.get("title", "") + " " + ev.get("description", ""),
                ev.get("query", ""),
            )

    return results


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
            return _fallback_keywords(industries, company_desc)
        return loop.run_until_complete(
            extract_search_keywords(company_desc, industries, personas, event_types)
        )
    except Exception as exc:
        logger.warning(f"extract_search_keywords_sync: {exc} — using fallback")
        return _fallback_keywords(industries, company_desc)
