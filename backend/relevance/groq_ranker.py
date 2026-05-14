"""
relevance/groq_ranker.py  —  LLM ranker with correct DB field mapping.

DB column reality (from Neon sample rows):
  POPULATED   : name, description, industry_tags, venue_name, city, country,
                source_url (eventseye page), start_date, end_date
  NULL / EMPTY: related_industries, event_cities, event_venues, website
  ALWAYS ZERO : est_attendees, ticket_price_usd
  ALWAYS EMPTY: audience_personas, price_description

Field priority used throughout this file:
  industry  → related_industries  → industry_tags  → category
  location  → event_cities        → city + country
  venue     → event_venues        → venue_name
  link      → website             → SerpAPI enriched → source_url (eventseye page)
                                  → Google search fallback

After SerpAPI enrichment, event dicts sent to the LLM include:
  est_attendees      (filled by SerpAPI or still 0 if not found)
  price_description  (filled by SerpAPI or "See website")
  audience_personas  (inferred from industry)
  event_link         (official site from SerpAPI organic results)
  serpapi_text       (AI-mode text blocks for LLM context)
"""
from __future__ import annotations

import json
import asyncio
import re
from typing import Dict, List, Optional
from urllib.parse import quote_plus

from groq import Groq
from loguru import logger
from pydantic import BaseModel, ValidationError, field_validator

from config import get_settings
from models.event import EventORM, RankedEvent
from models.icp_profile import CompanyContext, ICPProfile
from relevance.scorer import build_fallback_rationale

settings = get_settings()

# ── Pydantic schemas ───────────────────────────────────────────────

class GroqEventResult(BaseModel):
    id:             str
    fit_verdict:    str
    verdict_notes:  str
    key_numbers:    str = ""
    what_its_about: str = ""
    buyer_persona:  str = ""
    pricing:        str = ""
    event_link:     str = ""
    est_attendees:  int = 0

    @field_validator("fit_verdict")
    @classmethod
    def _check(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in {"GO", "CONSIDER", "SKIP"}:
            raise ValueError(f"bad verdict: {v}")
        return v


class GroqRankingResponse(BaseModel):
    ranked_events: List[GroqEventResult]


class ValidationResult(BaseModel):
    id:                 str
    verdict_ok:         bool
    corrected_verdict:  Optional[str] = None
    hallucination_flag: bool = False
    issue:              Optional[str] = None


class ValidationResponse(BaseModel):
    validations: List[ValidationResult]


# ── Groq client singleton ──────────────────────────────────────────

_groq_client: Optional[Groq] = None

def _groq() -> Optional[Groq]:
    global _groq_client
    if not settings.groq_api_key:
        return None
    if _groq_client is None:
        _groq_client = Groq(api_key=settings.groq_api_key)
    return _groq_client


# ── Field accessors with correct fallback order ────────────────────

def _industry(event: EventORM) -> str:
    """Always returns the populated industry_tags string."""
    return (
        (getattr(event, "related_industries", "") or "").strip() or
        (event.industry_tags or "").strip() or
        (event.category or "").strip()
    )


def _venue(event: EventORM) -> str:
    return (
        (getattr(event, "event_venues", "") or "").strip() or
        (event.venue_name or "").strip()
    )


def _city(event: EventORM) -> str:
    ec = (getattr(event, "event_cities", "") or "").strip()
    if ec:
        return ec
    city    = (event.city or "").strip()
    country = (event.country or "").strip()
    # Normalise "UK - United Kingdom" → "United Kingdom"
    if " - " in country:
        country = country.split(" - ")[-1].strip()
    return f"{city}, {country}".strip(", ")


def _place(event: EventORM) -> str:
    parts = [p for p in [_venue(event), _city(event)] if p]
    return ", ".join(parts)


def _is_generic(text: str) -> bool:
    t = (text or "").lower().strip()
    if t in ("", "see website", "see event website", "—", "-"):
        return True
    bad = (
        "major global trade fair",
        "source: eventseye", "sourced from eventseye",
        "trade show / expo sourced from",
        "professional conference sourced from",
        "see 10times listing",
    )
    return any(b in t for b in bad)


def _is_venue_url(url: str) -> bool:
    from enrichment.serp_enricher import _is_venue_url as _check
    return _check(url)


def _google_fallback(event: EventORM) -> str:
    year = (event.start_date or "")[:4] or ""
    city = (event.city or "").strip()
    q    = " ".join(filter(None, [event.name, year, city, "official website"]))
    return f"https://www.google.com/search?q={quote_plus(q)}"


def _best_link(event: EventORM, enrichments: dict) -> str:
    """
    Priority:
      1. SerpAPI enriched event_link / website
      2. source_url if it's an EventsEye event page
      3. registration_url if it's NOT a venue site
      4. Google search fallback
    """
    from enrichment.serp_enricher import _is_eventseye_event_page

    serp_link = enrichments.get("event_link") or enrichments.get("website") or ""
    if serp_link and not _is_venue_url(serp_link):
        return serp_link

    src = event.source_url or ""
    if _is_eventseye_event_page(src):
        return src

    reg = (getattr(event, "website", "") or "").strip() or (event.registration_url or "").strip()
    if reg and not _is_venue_url(reg):
        return reg

    return _google_fallback(event)


def _personas(event: EventORM, enrichments: dict, llm_value: str = "") -> str:
    db = (event.audience_personas or "").strip()
    if db and not _is_generic(db):
        return db
    if llm_value and not _is_generic(llm_value):
        return llm_value
    ep = enrichments.get("audience_personas", "")
    if ep:
        return ep
    # Last resort: infer from industry_tags
    from enrichment.serp_enricher import _infer_personas
    ind = _industry(event)
    if ind:
        inferred = _infer_personas("", ind)
        if inferred:
            return inferred
    return ""


def _pricing(event: EventORM, enrichments: dict, llm_value: str = "") -> str:
    pd = (event.price_description or "").strip()
    if pd and not _is_generic(pd):
        return pd
    if event.ticket_price_usd and event.ticket_price_usd > 0:
        return f"From ${event.ticket_price_usd:,.0f}"
    if llm_value and not _is_generic(llm_value):
        return llm_value
    ep = enrichments.get("price_description", "")
    if ep and not _is_generic(ep):
        return ep
    return "See website"


def _description(event: EventORM, enrichments: dict, llm_value: str = "") -> str:
    for v in [event.short_summary, event.description, llm_value,
              enrichments.get("description", "")]:
        if v and not _is_generic(v):
            return v[:300]
    return (event.description or event.short_summary or "")[:300]


def _key_numbers(event: EventORM, enrichments: dict, llm_nums: str = "", llm_att: int = 0) -> str:
    # LLM key_numbers if not generic
    if llm_nums and not _is_generic(llm_nums):
        return llm_nums
    # Build from known numeric fields
    parts: list[str] = []
    att = event.est_attendees or llm_att or enrichments.get("est_attendees", 0)
    if att:
        parts.append(f"{att:,} attendees")
    vip = getattr(event, "vip_count", 0) or 0
    if vip:
        parts.append(f"{vip} VIPs")
    spk = getattr(event, "speaker_count", 0) or 0
    if spk:
        parts.append(f"{spk} speakers")
    if parts:
        return "; ".join(parts)
    # Fall back to first sentence of description
    desc = event.description or ""
    if desc and not _is_generic(desc):
        for s in re.split(r"[.!?]", desc):
            s = s.strip()
            if len(s) > 30:
                return s[:120]
    return "See event website"


# ── System prompt ──────────────────────────────────────────────────

def _system_prompt(profile: ICPProfile, ctx: Optional[CompanyContext]) -> str:
    company_block = ""
    if ctx:
        parts = []
        if ctx.company_name:  parts.append(f"Company: {ctx.company_name}")
        if ctx.location:      parts.append(f"HQ: {ctx.location}")
        if ctx.what_we_do:    parts.append(f"What they sell: {ctx.what_we_do[:500]}")
        if ctx.what_we_need:  parts.append(f"Event goals: {ctx.what_we_need[:400]}")
        if ctx.deck_text:     parts.append(f"Deck excerpt:\n{ctx.deck_text[:1800]}")
        if parts:
            company_block = "\n\nCOMPANY CONTEXT:\n" + "\n".join(parts)

    return f"""You are an expert B2B sales strategist recommending trade events.

CLIENT ICP:
  Target industries: {', '.join(profile.target_industries)}
  Target buyer roles: {', '.join(profile.target_personas)}
  Focus geographies: {', '.join(profile.target_geographies)}
  Preferred formats: {', '.join(profile.preferred_event_types)}
  Company description: {profile.company_description[:300]}
{company_block}

VERDICT DEFINITIONS:
  GO      = Strong industry + buyer role match. Clear pipeline opportunity.
  CONSIDER = Partial overlap. Buyer profiles partially match or geography is borderline.
  SKIP    = Weak or no alignment.

CRITICAL WRITING RULES:
  ✅ Use ONLY fields visible in the event data (industry_focus, description, typical_attendees, location).
  ✅ Describe what the event ACTUALLY covers based on its industry_focus and description.
  ✅ Explain WHY it's relevant (or not) in terms of sales opportunity.
  ✅ If serpapi_text has attendee or pricing data, extract it accurately.
  ✅ Use event_link from the event data for the link field.

  ❌ NEVER say an event covers "AI/ML", "Technology", "Cloud" unless those words appear
     in the event's own industry_focus, description, or serpapi_text.
  ❌ NEVER project the client's target industries onto the event.
  ❌ NEVER use code field names like event.industry_tags, profile.target_personas.
  ❌ Do not fabricate attendee numbers or prices — use "See event website" if unknown.

Output ONLY valid JSON. No text outside JSON."""


VALIDATION_SYS = """You are a QA reviewer for B2B event intelligence.

For each verdict, check:
1. Does the verdict match the event data (not the client's industry wishlist)?
2. Does verdict_notes describe what the event ACTUALLY covers?
3. Are there any developer field names in the text? → hallucination_flag=true
4. Does it claim industries not in the event's own data? → hallucination_flag=true

Return ONLY this JSON:
{"validations":[{"id":"...","verdict_ok":true,"corrected_verdict":null,"hallucination_flag":false,"issue":null}]}"""


# ── Event serialiser for LLM ───────────────────────────────────────

def _event_dict(
    event:      EventORM,
    score:      float,
    tier:       str,
    detail:     dict,
    enrichments: dict,
) -> dict:
    """Build the dict sent to the LLM — uses only populated DB fields + enrichments."""
    return {
        "id":                   event.id,
        "name":                 event.name,
        "description":          _description(event, enrichments)[:400],
        "start_date":           event.start_date,
        "end_date":             event.end_date or event.start_date,
        "location":             _place(event),
        "venue":                _venue(event),
        "is_virtual":           event.is_virtual,
        "is_hybrid":            event.is_hybrid,
        "est_attendees":        event.est_attendees or enrichments.get("est_attendees", 0),
        "industry_focus":       _industry(event),
        "typical_attendees":    _personas(event, enrichments),
        "pricing":              _pricing(event, enrichments),
        "event_link":           _best_link(event, enrichments),
        "serpapi_text":         enrichments.get("serpapi_text", "")[:2000],
        "serpapi_results":      enrichments.get("serpapi_results", []),
        "pre_score":            score,
        "pre_tier":             tier,
        "rule_matched_industries": detail.get("industry_matched", []),
        "rule_matched_personas":   detail.get("persona_matched", []),
        "geo_match":               detail.get("geo_matched", ""),
    }


def _profile_dict(profile: ICPProfile) -> dict:
    return {
        "company_name":       profile.company_name,
        "what_we_do":         profile.company_description[:400],
        "target_industries":  profile.target_industries,
        "target_buyer_roles": profile.target_personas,
        "target_locations":   profile.target_geographies,
        "preferred_formats":  profile.preferred_event_types,
    }


def _ranking_prompt(events_dicts: list, profile_dict: dict) -> str:
    return f"""CLIENT ICP:
{json.dumps(profile_dict, indent=2)}

EVENTS:
{json.dumps(events_dicts, indent=2)}

For each event:
- what_its_about: describe based on industry_focus + description fields ONLY
- buyer_persona: use typical_attendees field, or infer from industry_focus
- pricing: use pricing field from event data, or extract from serpapi_text
- event_link: use event_link field from event data
- est_attendees: extract number from serpapi_text if available, else 0
- key_numbers: attendee count + any numeric facts from serpapi_text; empty string if unknown
- verdict_notes: explain the relevance in plain sales-analyst language

Return JSON:
{{
  "ranked_events": [
    {{
      "id": "<id>",
      "fit_verdict": "GO|CONSIDER|SKIP",
      "verdict_notes": "<2-3 sentences about what the event is and its sales relevance>",
      "key_numbers": "<numbers from serpapi_text or empty string>",
      "what_its_about": "<what this event covers based on its own data>",
      "buyer_persona": "<who attends based on industry>",
      "pricing": "<from serpapi_text or 'See website'>",
      "event_link": "<from event_link field>",
      "est_attendees": 0
    }}
  ]
}}"""


# ── LLM call ───────────────────────────────────────────────────────

async def _call_groq(
    client: Groq,
    system: str,
    user:   str,
    timeout: int,
    label:  str = "groq",
) -> Optional[str]:
    try:
        resp = await asyncio.wait_for(
            asyncio.to_thread(
                client.chat.completions.create,
                model           = settings.groq_model,
                messages        = [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
                temperature     = settings.groq_temperature,
                max_tokens      = settings.groq_max_tokens,
                response_format = {"type": "json_object"},
            ),
            timeout=timeout,
        )
        return resp.choices[0].message.content
    except asyncio.TimeoutError:
        logger.error(f"[{label}] timed out after {timeout}s")
    except Exception as exc:
        logger.error(f"[{label}] error: {exc}")
    return None


# ── Hallucination guard ────────────────────────────────────────────

def _is_hallucinated(
    result:  GroqEventResult,
    event:   EventORM,
    profile: ICPProfile,
    detail:  dict,
) -> bool:
    notes = (result.verdict_notes or "").lower().strip()
    if len(notes) < 20:
        return True
    if any(p in notes for p in ("event.industry", "profile.target", "icp field",
                                 "event.name", "profile.company")):
        return True

    event_text  = (
        f"{event.name} {_industry(event)} {event.description or ''} "
        f"{event.audience_personas or ''} {event.category or ''}"
    ).lower()
    matched_ind = {s.lower() for s in detail.get("industry_matched", [])}

    for ind in profile.target_industries or []:
        tokens = [
            t for t in re.split(r"[^a-z0-9]+", ind.lower())
            if len(t) > 2
        ]
        if not tokens:
            continue
        mentioned = any(t in notes for t in tokens)
        evidenced = (
            any(t in event_text for t in tokens) or
            ind.lower() in matched_ind
        )
        negated = any(
            f"not {t}" in notes or f"outside {t}" in notes
            for t in tokens
        )
        if mentioned and not evidenced and not negated:
            logger.debug(
                f"Hallucination: '{ind}' in notes for '{event.name[:50]}' "
                f"but not in event data"
            )
            return True
    return False


# ── Main entry ─────────────────────────────────────────────────────

async def rank_with_groq(
    events:      List[EventORM],
    profile:     ICPProfile,
    pre_scores:  Dict[str, float],
    pre_tiers:   Dict[str, str],
    pre_details: Dict[str, dict],
    company_ctx: Optional[CompanyContext] = None,
    enrichments: Dict[str, dict]  = None,
    deal_size_category: str = "medium",
) -> List[RankedEvent]:

    enrichments  = enrichments or {}
    client       = _groq()
    groq_results: Dict[str, GroqEventResult] = {}
    hallucinated: set[str] = set()

    if client and events:
        events_dicts = [
            _event_dict(
                e,
                pre_scores.get(e.id, 0.0),
                pre_tiers.get(e.id, "SKIP"),
                pre_details.get(e.id, {}),
                enrichments.get(e.id, {}),
            )
            for e in events
        ]

        # Agent 1 — ranker
        raw = await _call_groq(
            client,
            _system_prompt(profile, company_ctx),
            _ranking_prompt(events_dicts, _profile_dict(profile)),
            timeout=settings.groq_timeout_seconds,
            label="ranker",
        )
        if raw:
            try:
                parsed = GroqRankingResponse.model_validate_json(raw)
                groq_results = {r.id: r for r in parsed.ranked_events}
                logger.info(f"Ranker: {len(groq_results)} events ranked")
            except ValidationError as ve:
                logger.error(f"Ranker schema error: {ve}")

        # Agent 2 — validator
        if len(groq_results) >= 3:
            primary_list = [
                {"id": r.id, "fit_verdict": r.fit_verdict,
                 "verdict_notes": r.verdict_notes, "key_numbers": r.key_numbers}
                for r in groq_results.values()
            ]
            val_raw = await _call_groq(
                client,
                VALIDATION_SYS,
                (f"SOURCE DATA:\n{json.dumps(events_dicts, indent=2)}\n\n"
                 f"VERDICTS:\n{json.dumps(primary_list, indent=2)}"),
                timeout=max(10, settings.groq_timeout_seconds // 2),
                label="validator",
            )
            if val_raw:
                try:
                    val = ValidationResponse.model_validate_json(val_raw)
                    corrections = 0
                    for v in val.validations:
                        if v.hallucination_flag:
                            hallucinated.add(v.id)
                            logger.warning(f"Validator flagged: {v.id} — {v.issue}")
                        if not v.verdict_ok and v.corrected_verdict and v.id in groq_results:
                            old = groq_results[v.id].fit_verdict
                            groq_results[v.id] = groq_results[v.id].model_copy(
                                update={"fit_verdict": v.corrected_verdict}
                            )
                            corrections += 1
                            logger.info(f"Corrected {v.id}: {old}→{v.corrected_verdict}")
                    logger.info(
                        f"Validation: {corrections} corrected, {len(hallucinated)} flagged"
                    )
                except Exception as exc:
                    logger.warning(f"Validator parse error: {exc}")

    # ── Build final RankedEvent list ───────────────────────────────
    ranked: List[RankedEvent] = []
    for event in events:
        score  = pre_scores.get(event.id, 0.0)
        tier   = pre_tiers.get(event.id, "SKIP")
        detail = pre_details.get(event.id, {})
        ev_en  = enrichments.get(event.id, {})

        llm_about   = ""
        llm_persona = ""
        llm_pricing = ""
        llm_link    = ""
        llm_att     = 0
        llm_nums    = ""

        if event.id in groq_results and event.id not in hallucinated:
            gr = groq_results[event.id]
            if _is_hallucinated(gr, event, profile, detail):
                logger.warning(f"Replacing hallucinated rationale: '{event.name[:50]}'")
                verdict   = tier
                rationale = build_fallback_rationale(event, profile, detail, score, tier)
            else:
                verdict   = gr.fit_verdict
                rationale = gr.verdict_notes
                llm_about   = gr.what_its_about or ""
                llm_persona = gr.buyer_persona  or ""
                llm_pricing = gr.pricing        or ""
                llm_link    = gr.event_link     or ""
                llm_att     = gr.est_attendees  or 0
                llm_nums    = gr.key_numbers    or ""
        else:
            verdict   = tier
            rationale = build_fallback_rationale(event, profile, detail, score, tier)

        # Resolve final values with full fallback chain
        final_link = (
            (llm_link if llm_link and not _is_generic(llm_link) and
             not _is_venue_url(llm_link) else "")
            or _best_link(event, ev_en)
        )
        final_att  = (
            event.est_attendees or
            llm_att or
            ev_en.get("est_attendees", 0) or
            0
        )

        ranked.append(RankedEvent(
            id              = event.id,
            event_name      = event.name,
            date            = (
                event.start_date +
                (f" – {event.end_date}"
                 if event.end_date and event.end_date != event.start_date else "")
            ),
            place           = _place(event),
            event_link      = final_link,
            what_its_about  = _description(event, ev_en, llm_about)[:200],
            key_numbers     = _key_numbers(event, ev_en, llm_nums, llm_att),
            industry        = _industry(event),
            buyer_persona   = _personas(event, ev_en, llm_persona),
            pricing         = _pricing(event, ev_en, llm_pricing),
            pricing_link    = final_link,
            fit_verdict     = verdict,
            verdict_notes   = rationale,
            sponsors        = event.sponsors or "",
            speakers_link   = event.speakers_url or "",
            agenda_link     = event.agenda_url or "",
            relevance_score = score,
            source_platform = event.source_platform,
            est_attendees   = final_att,
            organizer       = getattr(event, "organizer", "") or "",
            website         = final_link,
            serpapi_enriched= bool(ev_en),
        ))

    return ranked
