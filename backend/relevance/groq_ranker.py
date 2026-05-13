"""
Groq LLM Ranker v4 — uses all available DB columns including the extended
fields added for EventsEye/external sources (event_cities, event_venues,
related_industries, website).

Column priority (best-available):
  location  → event_cities  > "city, country"
  venue     → event_venues  > venue_name
  industry  → related_industries > industry_tags > category
  link      → website > registration_url > source_url
  description → description (if rich) > short_summary
"""
import json
import asyncio
from typing import List, Dict, Optional
from groq import Groq
from pydantic import BaseModel, ValidationError, field_validator
from models.event import EventORM, RankedEvent
from models.icp_profile import ICPProfile, CompanyContext
from relevance.scorer import build_fallback_rationale
from config import get_settings
from loguru import logger

settings = get_settings()


# ── Output schema ──────────────────────────────────────────────────

class GroqEventResult(BaseModel):
    id: str
    fit_verdict: str
    verdict_notes: str
    key_numbers: str = ""

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
    id: str
    verdict_ok: bool
    corrected_verdict: Optional[str] = None
    hallucination_flag: bool = False
    issue: Optional[str] = None


class ValidationResponse(BaseModel):
    validations: List[ValidationResult]


# ── Groq singleton ─────────────────────────────────────────────────

_groq_client: Optional[Groq] = None

def get_groq_client() -> Optional[Groq]:
    global _groq_client
    if not settings.groq_api_key:
        return None
    if _groq_client is None:
        _groq_client = Groq(api_key=settings.groq_api_key)
    return _groq_client


# ── Column helpers ─────────────────────────────────────────────────

def _best(*values: str) -> str:
    """Return the first non-empty, non-generic value."""
    generic = {
        "see website", "see 10times listing", "see eventseye listing",
        "see website for details", "",
    }
    for v in values:
        if v and v.strip() and v.strip().lower() not in generic:
            return v.strip()
    return ""


def _event_location(event: EventORM) -> str:
    """Best available location string."""
    # event_cities is the richest (e.g. "Jakarta (Indonesia)")
    ec = (event.event_cities or "").strip()
    if ec:
        return ec
    parts = [event.city or "", event.country or ""]
    return ", ".join(p for p in parts if p).strip(", ") or "Location TBC"


def _event_venue(event: EventORM) -> str:
    """Best available venue string."""
    return _best(event.event_venues or "", event.venue_name or "")


def _event_industry(event: EventORM) -> str:
    """Best available industry tags."""
    return _best(
        event.related_industries or "",
        event.industry_tags or "",
        event.category or "",
    )


def _event_link(event: EventORM) -> str:
    """Best available registration / info link."""
    return _best(
        event.website or "",
        event.registration_url or "",
        event.source_url or "",
    )


def _event_description(event: EventORM) -> str:
    """Return description only if it's genuinely informative (not a placeholder)."""
    from enrichment.serp_enricher import _is_generic_description
    desc = (event.description or "").strip()
    if _is_generic_description(desc):
        return (event.short_summary or "").strip()
    return desc[:400]


def _build_key_numbers(event: EventORM) -> str:
    parts = []
    att = event.est_attendees or 0
    if att > 0:
        parts.append(f"{att:,} attendees")
    if getattr(event, "vip_count", 0):
        parts.append(f"{event.vip_count} VIPs")
    if getattr(event, "speaker_count", 0):
        parts.append(f"{event.speaker_count} speakers")
    if getattr(event, "exhibitor_count", 0):
        parts.append(f"{event.exhibitor_count} exhibitors")
    return "; ".join(parts) if parts else ""


# ── System prompt ──────────────────────────────────────────────────

def _build_system_prompt(profile: ICPProfile, company_ctx: Optional[CompanyContext]) -> str:
    company_block = ""
    if company_ctx:
        parts = []
        if company_ctx.company_name: parts.append(f"Company: {company_ctx.company_name}")
        if company_ctx.location:     parts.append(f"HQ: {company_ctx.location}")
        if company_ctx.what_we_do:   parts.append(f"Sells/does: {company_ctx.what_we_do[:500]}")
        if company_ctx.what_we_need: parts.append(f"Needs from events: {company_ctx.what_we_need[:400]}")
        if company_ctx.deck_text:    parts.append(f"From pitch deck:\n{company_ctx.deck_text[:1800]}")
        if parts:
            company_block = "\n\nCOMPANY CONTEXT:\n" + "\n".join(parts)

    icp_block = (
        f"  Target industries: {', '.join(profile.target_industries)}\n"
        f"  Target buyer roles: {', '.join(profile.target_personas)}\n"
        f"  Focus geographies: {', '.join(profile.target_geographies)}\n"
        f"  Preferred formats: {', '.join(profile.preferred_event_types)}\n"
        f"  What the company does: {profile.company_description[:300]}"
    )

    return f"""You are an expert B2B sales strategist writing event recommendations.

CLIENT ICP:
{icp_block}
{company_block}

VERDICT RULES:
  GO      = Strong buyer-audience + industry alignment. Clear pipeline potential.
  CONSIDER= Partial overlap. Worth evaluating before committing budget.
  SKIP    = Poor alignment. Not worth the investment for this sales motion.

WRITING RULES for verdict_notes (CRITICAL):
  ✅ Write like a sales analyst talking to a colleague — plain business English.
  ✅ Mention specific industries, job titles, locations from the event data.
  ✅ Explain WHY it matters (or doesn't) in terms of sales opportunity.
  ❌ NEVER cite code / field names ("event.industry_tags", "ICP", "metadata").
  ❌ NEVER be vague ("great networking"). Be specific to this event.

key_numbers: use ONLY real numbers from event data. Leave empty if none available.
Output ONLY valid JSON. No text outside the JSON."""


VALIDATION_SYSTEM = """Quality-control reviewer for B2B event recommendations.

Check each verdict:
1. Does GO/CONSIDER/SKIP make logical sense given the event?
2. Does verdict_notes contain field names / developer jargon? Flag hallucination_flag=true.
3. Are key_numbers fabricated? Flag hallucination_flag=true.

Return JSON only:
{"validations":[{"id":"...","verdict_ok":true,"corrected_verdict":null,"hallucination_flag":false,"issue":null}]}"""


# ── Serialisers ────────────────────────────────────────────────────

def _event_to_dict(event: EventORM, pre_score: float, pre_tier: str, detail: dict) -> dict:
    return {
        "id":              event.id,
        "name":            event.name,
        "description":     _event_description(event),
        "start_date":      event.start_date,
        "end_date":        event.end_date,
        "location":        _event_location(event),
        "venue":           _event_venue(event),
        "is_virtual":      event.is_virtual,
        "is_hybrid":       event.is_hybrid,
        "est_attendees":   event.est_attendees,
        "vip_count":       getattr(event, "vip_count", 0),
        "speaker_count":   getattr(event, "speaker_count", 0),
        "exhibitor_count": getattr(event, "exhibitor_count", 0),
        "category":        event.category,
        "industry_focus":  _event_industry(event),
        "typical_attendees": event.audience_personas,
        "pricing":         event.price_description,
        "pre_relevance_score":    pre_score,
        "pre_tier_suggestion":    pre_tier,
        "rule_matched_industries":detail.get("industry_matched", []),
        "rule_matched_personas":  detail.get("persona_matched", []),
        "rule_geo_match":         detail.get("geo_matched", ""),
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
Override to SKIP only if zero buyer overlap confirmed.
Write verdict_notes in plain sales-analyst language.

Return JSON:
{{
  "ranked_events": [
    {{
      "id": "<event id>",
      "fit_verdict": "GO|CONSIDER|SKIP",
      "verdict_notes": "<2-3 plain-English sentences>",
      "key_numbers": "<real numbers only, or empty string>"
    }}
  ]
}}"""


# ── LLM call ───────────────────────────────────────────────────────

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


# ── Main entry ─────────────────────────────────────────────────────

async def rank_with_groq(
    events: List[EventORM],
    profile: ICPProfile,
    pre_scores: Dict[str, float],
    pre_tiers: Dict[str, str],
    pre_details: Dict[str, dict],
    company_ctx: Optional[CompanyContext] = None,
    enrichments: Optional[Dict[str, dict]] = None,  # from serp_enricher
) -> List[RankedEvent]:
    """
    Rank events using Groq LLM + cross-validation agent.

    enrichments: {event_id: {est_attendees, price_description, ...}}
    Applied to events before building the response.
    """
    client = get_groq_client()
    groq_results: Dict[str, GroqEventResult] = {}
    hallucinated: set = set()

    if client and events:
        events_dict   = [_event_to_dict(e, pre_scores.get(e.id, 0.0),
                                        pre_tiers.get(e.id, "SKIP"),
                                        pre_details.get(e.id, {})) for e in events]
        profile_dict  = _profile_to_dict(profile)
        system_prompt = _build_system_prompt(profile, company_ctx)
        user_prompt   = _ranking_prompt(events_dict, profile_dict)

        # Agent 1 — primary ranker
        raw = await _call_groq(client, system_prompt, user_prompt,
                               timeout=settings.groq_timeout_seconds, label="ranker")
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
                            logger.warning(f"Flagged hallucination: {v.id} — {v.issue}")
                        if not v.verdict_ok and v.corrected_verdict and v.id in groq_results:
                            old = groq_results[v.id].fit_verdict
                            groq_results[v.id] = GroqEventResult(
                                id=v.id,
                                fit_verdict=v.corrected_verdict,
                                verdict_notes=groq_results[v.id].verdict_notes,
                                key_numbers=groq_results[v.id].key_numbers,
                            )
                            corrections += 1
                            logger.info(f"Corrected {v.id}: {old}→{v.corrected_verdict}")
                    logger.info(f"Validation: {corrections} corrections, {len(hallucinated)} flagged.")
                except Exception as e:
                    logger.warning(f"Validator error: {e}")

    enrichments = enrichments or {}

    # ── Build output ───────────────────────────────────────────────
    ranked: List[RankedEvent] = []
    for event in events:
        score  = pre_scores.get(event.id, 0.0)
        tier   = pre_tiers.get(event.id, "SKIP")
        detail = pre_details.get(event.id, {})
        enrich = enrichments.get(event.id, {})

        # Apply SerpAPI enrichment to missing fields
        att          = enrich.get("est_attendees", event.est_attendees) or 0
        price_desc   = enrich.get("price_description", event.price_description) or "See website"
        price_usd    = enrich.get("ticket_price_usd", event.ticket_price_usd) or 0.0
        desc         = enrich.get("description_enriched", "") or _event_description(event)

        # Build key numbers from best available data
        key_nums = ""
        if event.id in groq_results and groq_results[event.id].key_numbers:
            key_nums = groq_results[event.id].key_numbers
        else:
            parts = []
            if att:  parts.append(f"{att:,} attendees")
            if getattr(event, "vip_count", 0):       parts.append(f"{event.vip_count} VIPs")
            if getattr(event, "speaker_count", 0):   parts.append(f"{event.speaker_count} speakers")
            if getattr(event, "exhibitor_count", 0): parts.append(f"{event.exhibitor_count} exhibitors")
            key_nums = "; ".join(parts)

        if event.id in groq_results and event.id not in hallucinated:
            gr        = groq_results[event.id]
            verdict   = gr.fit_verdict
            rationale = gr.verdict_notes
            if gr.key_numbers:
                key_nums = gr.key_numbers
        else:
            verdict   = tier
            rationale = build_fallback_rationale(event, profile, detail, score, tier)

        # Date range string
        date_str = event.start_date or ""
        if event.end_date and event.end_date != event.start_date and event.end_date:
            date_str += f" – {event.end_date}"

        # Pricing string
        if price_usd and price_usd > 0:
            pricing_display = price_desc or f"From ${price_usd:,.0f}"
        elif price_desc and price_desc.lower() not in ("see website", ""):
            pricing_display = price_desc
        elif event.ticket_price_usd == 0:
            pricing_display = "Free / Registration required"
        else:
            pricing_display = "See website"

        ranked.append(RankedEvent(
            id=event.id,
            event_name=event.name,
            date=date_str,
            place=_event_location(event),
            event_link=_event_link(event),
            what_its_about=desc[:250] if desc else "",
            key_numbers=key_nums,
            industry=_event_industry(event),
            buyer_persona=event.audience_personas or "",
            pricing=pricing_display,
            pricing_link=_event_link(event),
            fit_verdict=verdict,
            verdict_notes=rationale,
            sponsors=event.sponsors or "",
            speakers_link=event.speakers_url or "",
            agenda_link=event.agenda_url or "",
            relevance_score=score,
            source_platform=event.source_platform,
            est_attendees=att,
            enriched_attendees=bool(enrich.get("enriched_attendees")),
            enriched_price=bool(enrich.get("enriched_price")),
            enriched_description=bool(enrich.get("enriched_description")),
        ))

    return ranked
