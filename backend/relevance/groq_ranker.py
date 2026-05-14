"""
relevance/groq_ranker.py — fixed field mapping.

Critical fixes vs original:
  • Uses related_industries (not industry_tags) for industry display
  • Uses event_cities / event_venues for location
  • Uses website (not registration_url) for the event link
  • Applies SerpAPI enrichments to fill missing attendee/price/description
  • _event_to_dict passes richer data to the LLM
"""
import json
import asyncio
from typing import List, Dict, Optional
from loguru import logger
import re
from groq import Groq
from pydantic import BaseModel, ValidationError, field_validator

from models.event import EventORM, RankedEvent
from models.icp_profile import ICPProfile, CompanyContext
from relevance.scorer import build_fallback_rationale
from config import get_settings

settings = get_settings()


# ── Output schema ──────────────────────────────────────────

class GroqEventResult(BaseModel):
    id:           str
    fit_verdict:  str
    verdict_notes: str
    key_numbers:  str = ""
    what_its_about: str = ""
    buyer_persona: str = ""
    pricing: str = ""
    event_link: str = ""
    est_attendees: int = 0

    @field_validator("fit_verdict")
    @classmethod
    def validate_verdict(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in {"GO", "CONSIDER", "SKIP"}:
            raise ValueError(f"Invalid verdict: {v}")
        return v


class GroqRankingResponse(BaseModel):
    ranked_events: List[GroqEventResult]


class ValidationResult(BaseModel):
    id:                str
    verdict_ok:        bool
    corrected_verdict: Optional[str] = None
    hallucination_flag: bool = False
    issue:             Optional[str] = None


class ValidationResponse(BaseModel):
    validations: List[ValidationResult]


# ── Groq client ────────────────────────────────────────────

_groq_client: Optional[Groq] = None

def get_groq_client() -> Optional[Groq]:
    global _groq_client
    if not settings.groq_api_key:
        return None
    if _groq_client is None:
        _groq_client = Groq(api_key=settings.groq_api_key)
    return _groq_client


# ── Field helpers ──────────────────────────────────────────

def _get_industry(event: EventORM) -> str:
    """Return best available industry string."""
    return (
        getattr(event, "related_industries", "") or
        event.industry_tags or
        event.category or ""
    )


def _get_place(event: EventORM) -> str:
    """Return best available location string."""
    parts = filter(None, [
        getattr(event, "event_venues", "") or event.venue_name or "",
        getattr(event, "event_cities",  "") or event.city or "",
        event.country or "",
    ])
    return ", ".join(parts)


def _normalize_link(link: str) -> str:
    return (link or "").strip().rstrip("/").lower()


def _get_link(event: EventORM, enrichments: dict = None, duplicate_links: set[str] | None = None) -> str:
    """Return best available event-specific link, avoiding shared CSV/source URLs."""
    enrichments = enrichments or {}
    duplicate_links = duplicate_links or set()
    enriched_link = enrichments.get("event_link", "") or enrichments.get("website", "")
    db_link = getattr(event, "website", "") or event.registration_url or ""
    source_link = event.source_url or ""

    db_is_shared = _normalize_link(db_link) in duplicate_links
    source_is_shared = _normalize_link(source_link) in duplicate_links

    # Uploaded CSVs often arrive with one shared listing/export URL. Never show
    # that same URL as the event page for multiple rows; prefer SerpAPI's
    # event-specific result and otherwise leave the link empty.
    if (event.source_platform or "").upper() == "CSV_UPLOAD":
        if enriched_link:
            return enriched_link
        if db_is_shared or source_is_shared or "example.com/event/" in (db_link or source_link):
            return ""

    if db_is_shared and enriched_link:
        return enriched_link
    if db_is_shared and not enriched_link:
        db_link = ""
    if source_is_shared and not enriched_link:
        source_link = ""
    if "example.com/event/" in db_link or "example.com/event/" in source_link:
        return enriched_link or ""
    return db_link or enriched_link or source_link


def _get_personas(event: EventORM, enrichments: dict = None, llm_value: str = "") -> str:
    enrichments = enrichments or {}
    db_value = event.audience_personas or ""
    if not _is_generic_text(db_value):
        return db_value
    if not _is_generic_text(llm_value):
        return llm_value
    return enrichments.get("audience_personas", "") or ""


def _is_generic_text(text: str) -> bool:
    value = (text or "").strip().lower()
    if value in {"", "see website", "see event website", "—", "-"}:
        return True
    generic_phrases = (
        "major global trade fair",
        "source: eventseye",
        "sourced from eventseye",
        "see 10times listing",
    )
    return any(phrase in value for phrase in generic_phrases)


def _event_evidence_text(event: EventORM) -> str:
    return " ".join(filter(None, [
        event.name or "",
        event.description or "",
        event.short_summary or "",
        _get_industry(event),
        event.audience_personas or "",
        event.category or "",
    ])).lower()


def _looks_hallucinated(result: GroqEventResult, event: EventORM, profile: ICPProfile, detail: dict) -> bool:
    """Catch rationales that incorrectly project the client's ICP onto the event."""
    notes = (result.verdict_notes or "").lower()
    if not notes:
        return True
    blocked_phrases = ("event.industry_tags", "profile.target", "icp field")
    if any(phrase in notes for phrase in blocked_phrases):
        return True

    event_text = _event_evidence_text(event)
    matched = {str(x).lower() for x in detail.get("industry_matched", [])}
    for industry in profile.target_industries or []:
        tokens = [t for t in re.split(r"[^a-z0-9]+", industry.lower()) if len(t) > 2]
        if not tokens:
            continue
        mentioned = any(t in notes for t in tokens) or industry.lower() in notes
        evidenced = any(t in event_text for t in tokens) or industry.lower() in matched
        negated = any(f"not {t}" in notes or f"outside {t}" in notes for t in tokens)
        if mentioned and not evidenced and not negated:
            return True
    return False


def _get_description(event: EventORM, enrichments: dict = None, llm_value: str = "") -> str:
    enrichments = enrichments or {}
    for value in (event.short_summary, event.description, llm_value, enrichments.get("description", "")):
        if value and not _is_generic_text(value):
            return value[:300]
    return (event.short_summary or event.description or llm_value or enrichments.get("description", ""))[:300]


def _build_key_numbers(event: EventORM, enrichments: dict = None, llm_attendees: int = 0) -> str:
    parts = []
    att = event.est_attendees or 0
    # Apply enrichment if original is missing
    if not att and llm_attendees:
        att = llm_attendees
    if not att and enrichments:
        att = enrichments.get("est_attendees", 0)
    if att:
        parts.append(f"{att:,} attendees")

    vip = getattr(event, "vip_count", 0) or 0
    if vip:
        parts.append(f"{vip} VIPs")

    spk = getattr(event, "speaker_count", 0) or 0
    if spk:
        parts.append(f"{spk} speakers")

    return "; ".join(parts) if parts else "See event website"


def _get_pricing(event: EventORM, enrichments: dict = None, llm_value: str = "") -> str:
    if event.price_description and not _is_generic_text(event.price_description):
        return event.price_description
    if event.ticket_price_usd and event.ticket_price_usd > 0:
        return f"From ${event.ticket_price_usd:,.0f}"
    if not _is_generic_text(llm_value):
        return llm_value
    if enrichments:
        pd = enrichments.get("price_description", "")
        if pd and not _is_generic_text(pd):
            return pd
    return "See website"


# ── System prompt ──────────────────────────────────────────

def _build_system_prompt(profile: ICPProfile, company_ctx: Optional[CompanyContext]) -> str:
    company_block = ""
    if company_ctx:
        parts = []
        if company_ctx.company_name:
            parts.append(f"Company: {company_ctx.company_name}")
        if company_ctx.location:
            parts.append(f"HQ: {company_ctx.location}")
        if company_ctx.what_we_do:
            parts.append(f"What they sell/do: {company_ctx.what_we_do[:500]}")
        if company_ctx.what_we_need:
            parts.append(f"What they need from events: {company_ctx.what_we_need[:400]}")
        if company_ctx.deck_text:
            parts.append(f"From their pitch deck:\n{company_ctx.deck_text[:1800]}")
        if parts:
            company_block = "\n\nCOMPANY CONTEXT:\n" + "\n".join(parts)

    icp_block = (
        f"  Target industries: {', '.join(profile.target_industries)}\n"
        f"  Target buyer roles: {', '.join(profile.target_personas)}\n"
        f"  Focus geographies: {', '.join(profile.target_geographies)}\n"
        f"  Preferred event formats: {', '.join(profile.preferred_event_types)}\n"
        f"  Company description: {profile.company_description[:300]}"
    )

    return f"""You are an expert B2B sales strategist writing event recommendations for a sales team.

CLIENT'S ICP:
{icp_block}
{company_block}

For each event write a verdict (GO / CONSIDER / SKIP) and a 2-3 sentence plain-English explanation.

RULES:
  GO      = Clear buyer + industry match. Strong pipeline potential.
  CONSIDER = Partial overlap. Worth evaluating.
  SKIP    = Poor audience/industry/geography fit.

WRITING RULES:
  ✅ Write like a smart sales analyst. Mention specific industries, job titles, locations.
  ✅ Explain WHY it's relevant (or not) in terms of sales opportunity.
  ✅ Use ONLY event facts shown in EVENTS TO EVALUATE, including DATABASE_URL fields and SerpAPI evidence. If an event is about kitchen/bath, construction, healthcare, etc., describe that event category exactly.
  ✅ When DATABASE_URL fields are missing or generic, extract what_its_about, buyer_persona, pricing, attendees, and event_link from the matching SerpAPI evidence only.
  ❌ Do NOT force the client's target industry onto the event. Never say an event covers AI/ML, technology, fintech, etc. unless those words are present in the event facts.
  ❌ NEVER use code terms like "event.industry_tags", "profile.target_personas", "ICP field"
  ❌ NEVER be generic ("great networking opportunity")

Output ONLY valid JSON. No text outside the JSON.
"""


VALIDATION_SYSTEM = """You are a QA reviewer for B2B event recommendations.

Check each verdict for:
1. Does GO/CONSIDER/SKIP make sense given the event data?
2. Does verdict_notes contain developer field names like "event.industry_tags"? → hallucination_flag=true
3. Are key_numbers fabricated? → hallucination_flag=true

Return JSON only:
{"validations": [{"id": "...", "verdict_ok": true, "corrected_verdict": null, "hallucination_flag": false, "issue": null}]}"""


# ── Serialisers ────────────────────────────────────────────

def _event_to_dict(
    event: EventORM,
    pre_score: float,
    pre_tier: str,
    detail: dict,
    enrichments: dict,
) -> dict:
    """Send rich data to LLM. Uses new DB columns with old-field fallbacks."""
    industry = _get_industry(event)
    place    = _get_place(event)

    att = event.est_attendees or enrichments.get("est_attendees", 0)
    desc = (
        event.description or
        enrichments.get("description", "") or
        event.short_summary or ""
    )[:400]

    return {
        "id":                 event.id,
        "name":               event.name,
        "description":        desc,
        "start_date":         event.start_date,
        "end_date":           event.end_date or event.start_date,
        "location":           place,
        "is_virtual":         event.is_virtual,
        "is_hybrid":          event.is_hybrid,
        "est_attendees":      att,
        "category":           event.category,
        "industry_focus":     industry,
        "typical_attendees":  _get_personas(event, enrichments),
        "organizer":          getattr(event, "organizer", "") or "",
        "pricing":            _get_pricing(event, enrichments),
        "current_event_link":  _get_link(event, enrichments),
        "serpapi_search_text": enrichments.get("serpapi_text", "")[:1800],
        "serpapi_results":     enrichments.get("serpapi_results", []),
        "pre_relevance_score":  pre_score,
        "pre_tier_suggestion":  pre_tier,
        "rule_matched_industries": detail.get("industry_matched", []),
        "rule_matched_personas":   detail.get("persona_matched", []),
        "rule_geo_match":          detail.get("geo_matched", ""),
    }


def _profile_to_dict(profile: ICPProfile) -> dict:
    return {
        "company_name":       profile.company_name,
        "what_we_do":         profile.company_description[:400],
        "target_industries":  profile.target_industries,
        "target_buyer_roles": profile.target_personas,
        "target_locations":   profile.target_geographies,
        "preferred_formats":  profile.preferred_event_types,
        "max_budget_usd":     profile.budget_usd,
        "min_attendees":      profile.min_attendees,
    }


def _ranking_prompt(events_dict: list, profile_dict: dict) -> str:
    return f"""CLIENT ICP:
{json.dumps(profile_dict, indent=2)}

EVENTS TO EVALUATE:
{json.dumps(events_dict, indent=2)}

Use pre_tier_suggestion and rule_matched_* as strong hints.
Write verdict_notes in plain sales-analyst language. No field names.

Return JSON:
{{
  "ranked_events": [
    {{
      "id": "<event id>",
      "fit_verdict": "GO|CONSIDER|SKIP",
      "verdict_notes": "<2-3 plain-English sentences>",
      "key_numbers": "<real numbers only; use See event website if unknown>",
      "what_its_about": "<event description from DB/SerpAPI, blank if unknown>",
      "buyer_persona": "<attendee/buyer profile from DB/SerpAPI, blank if unknown>",
      "pricing": "<ticket/entry price from DB/SerpAPI, or See website if unknown>",
      "event_link": "<official event-specific URL from DB/SerpAPI, blank if unknown>",
      "est_attendees": 0
    }}
  ]
}}"""


# ── LLM call ───────────────────────────────────────────────

async def _call_groq(client, system, user, timeout, label="groq") -> Optional[str]:
    try:
        completion = await asyncio.wait_for(
            asyncio.to_thread(
                client.chat.completions.create,
                model=settings.groq_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user},
                ],
                temperature=settings.groq_temperature,
                max_tokens=settings.groq_max_tokens,
                response_format={"type": "json_object"},
            ),
            timeout=timeout,
        )
        return completion.choices[0].message.content
    except asyncio.TimeoutError:
        logger.error(f"[{label}] timed out after {timeout}s")
    except Exception as e:
        logger.error(f"[{label}] error: {e}")
    return None


# ── Main entry ─────────────────────────────────────────────

async def rank_with_groq(
    events:      List[EventORM],
    profile:     ICPProfile,
    pre_scores:  Dict[str, float],
    pre_tiers:   Dict[str, str],
    pre_details: Dict[str, dict],
    company_ctx: Optional[CompanyContext] = None,
    enrichments: Dict[str, dict] = None,   # ← SerpAPI enrichments keyed by event.id
    deal_size_category: str = "medium",
) -> List[RankedEvent]:

    enrichments = enrichments or {}
    client = get_groq_client()
    groq_results: Dict[str, GroqEventResult] = {}
    hallucinated: set = set()
    link_counts: dict[str, int] = {}
    for event in events:
        event_links = {
            _normalize_link(link)
            for link in (getattr(event, "website", ""), event.registration_url or "", event.source_url or "")
            if _normalize_link(link)
        }
        for normalized in event_links:
            link_counts[normalized] = link_counts.get(normalized, 0) + 1
    duplicate_links = {link for link, count in link_counts.items() if count > 1}

    if client and events:
        events_dict   = [
            _event_to_dict(
                e,
                pre_scores.get(e.id, 0.0),
                pre_tiers.get(e.id, "SKIP"),
                pre_details.get(e.id, {}),
                enrichments.get(e.id, {}),
            )
            for e in events
        ]
        profile_dict  = _profile_to_dict(profile)
        system_prompt = _build_system_prompt(profile, company_ctx)
        user_prompt   = _ranking_prompt(events_dict, profile_dict)

        # Agent 1 — primary ranker
        raw = await _call_groq(
            client, system_prompt, user_prompt,
            timeout=settings.groq_timeout_seconds, label="ranker"
        )
        if raw:
            try:
                parsed = GroqRankingResponse.model_validate_json(raw)
                for item in parsed.ranked_events:
                    groq_results[item.id] = item
                logger.info(f"Ranker: {len(groq_results)} events ranked.")
            except ValidationError as ve:
                logger.error(f"Ranker schema error: {ve}")

        # Agent 2 — cross-validator
        if len(groq_results) >= 3:
            primary_list = [
                {"id": r.id, "fit_verdict": r.fit_verdict,
                 "verdict_notes": r.verdict_notes, "key_numbers": r.key_numbers}
                for r in groq_results.values()
            ]
            val_raw = await _call_groq(
                client, VALIDATION_SYSTEM,
                f"SOURCE DATA:\n{json.dumps(events_dict, indent=2)}\n\n"
                f"VERDICTS:\n{json.dumps(primary_list, indent=2)}",
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
                            logger.warning(f"Flagged: {v.id} — {v.issue}")
                        if not v.verdict_ok and v.corrected_verdict and v.id in groq_results:
                            old = groq_results[v.id].fit_verdict
                            groq_results[v.id] = groq_results[v.id].model_copy(
                                update={"fit_verdict": v.corrected_verdict}
                            )
                            corrections += 1
                            logger.info(f"Corrected {v.id}: {old}→{v.corrected_verdict}")
                    logger.info(f"Validation: {corrections} corrected, {len(hallucinated)} flagged.")
                except Exception as e:
                    logger.warning(f"Validator parse error: {e}")

    # ── Build RankedEvent list ─────────────────────────────
    ranked: List[RankedEvent] = []
    for event in events:
        score  = pre_scores.get(event.id, 0.0)
        tier   = pre_tiers.get(event.id, "SKIP")
        detail = pre_details.get(event.id, {})
        ev_enrich = enrichments.get(event.id, {})

        llm_about = ""
        llm_persona = ""
        llm_pricing = ""
        llm_link = ""
        llm_attendees = 0

        if event.id in groq_results and event.id not in hallucinated:
            gr        = groq_results[event.id]
            if _looks_hallucinated(gr, event, profile, detail):
                logger.warning(f"Replacing hallucinated rationale for {event.id}: {gr.verdict_notes[:120]}")
                verdict   = tier
                rationale = build_fallback_rationale(event, profile, detail, score, tier)
            else:
                verdict   = gr.fit_verdict
                rationale = gr.verdict_notes
                llm_about = gr.what_its_about or ""
                llm_persona = gr.buyer_persona or ""
                llm_pricing = gr.pricing or ""
                llm_link = gr.event_link or ""
                llm_attendees = gr.est_attendees or 0
        else:
            verdict   = tier
            rationale = build_fallback_rationale(event, profile, detail, score, tier)

        key_nums = (
            groq_results[event.id].key_numbers
            if (
                event.id in groq_results
                and event.id not in hallucinated
                and not _is_generic_text(groq_results[event.id].key_numbers)
            )
            else _build_key_numbers(event, ev_enrich, llm_attendees)
        )

        about = _get_description(event, ev_enrich, llm_about)[:200]
        llm_link_is_shared = _normalize_link(llm_link) in duplicate_links
        event_link = (
            llm_link
            if not _is_generic_text(llm_link) and not llm_link_is_shared
            else _get_link(event, ev_enrich, duplicate_links)
        )
        pricing = _get_pricing(event, ev_enrich, llm_pricing)
        personas = _get_personas(event, ev_enrich, llm_persona)
        est_attendees = event.est_attendees or llm_attendees or ev_enrich.get("est_attendees", 0) or 0

        ranked.append(RankedEvent(
            id=event.id,
            event_name=event.name,
            date=(
                event.start_date +
                (f" – {event.end_date}"
                 if event.end_date and event.end_date != event.start_date else "")
            ),
            place=_get_place(event),
            event_link=event_link,
            what_its_about=about,
            key_numbers=key_nums,
            industry=_get_industry(event),
            buyer_persona=personas,
            pricing=pricing,
            pricing_link=event_link,
            fit_verdict=verdict,
            verdict_notes=rationale,
            sponsors=event.sponsors or "",
            speakers_link=event.speakers_url or "",
            agenda_link=event.agenda_url or "",
            relevance_score=score,
            source_platform=event.source_platform,
            est_attendees=est_attendees,
            organizer=getattr(event, "organizer", "") or "",
            website=event_link,
            serpapi_enriched=bool(ev_enrich),
        ))

    return ranked
