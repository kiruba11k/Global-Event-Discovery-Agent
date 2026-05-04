"""
Groq LLM Ranker v3 — plain-language business rationale.
No field-name citations in output. Reads like a sales analyst wrote it.
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


# ── System prompt ──────────────────────────────────────────────────

def _build_system_prompt(profile: ICPProfile, company_ctx: Optional[CompanyContext]) -> str:
    company_block = ""
    if company_ctx:
        parts = []
        if company_ctx.company_name:
            parts.append(f"Company: {company_ctx.company_name}")
        if company_ctx.location:
            parts.append(f"HQ: {company_ctx.location}")
        if company_ctx.founded_year:
            parts.append(f"Founded: {company_ctx.founded_year}")
        if company_ctx.what_we_do:
            parts.append(f"What they sell/do: {company_ctx.what_we_do[:500]}")
        if company_ctx.what_we_need:
            parts.append(f"What they need from events: {company_ctx.what_we_need[:400]}")
        if company_ctx.deck_text:
            parts.append(f"From their pitch deck:\n{company_ctx.deck_text[:1800]}")
        if parts:
            company_block = "\n\nCOMPANY CONTEXT:\n" + "\n".join(parts)

    icp_block = (
        f"  Sells to industries: {', '.join(profile.target_industries)}\n"
        f"  Targets these buyer roles: {', '.join(profile.target_personas)}\n"
        f"  Focus geographies: {', '.join(profile.target_geographies)}\n"
        f"  Preferred event formats: {', '.join(profile.preferred_event_types)}\n"
        f"  What the company does: {profile.company_description[:300]}"
    )

    return f"""You are an expert B2B sales strategist writing event recommendations for a sales team.

YOUR CLIENT'S ICP (Ideal Customer Profile):
{icp_block}
{company_block}

YOUR JOB: For each event, write a verdict (GO / CONSIDER / SKIP) and a plain-English explanation
that a salesperson or business executive can immediately understand.

VERDICT RULES:
  GO      = This event clearly attracts the right buyers in the right industry.
             Strong pipeline potential. Recommend attending.
  CONSIDER = Some overlap with target buyers or industry, but not a perfect fit.
             Worth evaluating further before committing budget.
  SKIP    = The event audience, industry, or location doesn't match the ICP.
             Not worth the investment for this sales motion.

WRITING RULES FOR verdict_notes (CRITICAL):
  ✅ Write like a smart sales analyst talking to a colleague.
  ✅ Mention specific industries, job titles, and locations from the event data.
  ✅ Explain WHY it's relevant (or not) in terms of sales opportunity.
  ✅ Be concrete: name the audience, the industry, why it matters for pipeline.
  ❌ NEVER mention code, field names, or technical terms like "event.industry_tags",
     "profile.target_personas", "ICP", "data fields", "metadata", etc.
  ❌ NEVER say "the event's industry tags match the profile". That's developer speak.
  ❌ NEVER be generic ("great networking opportunity"). Be specific to this event.

EXAMPLES OF GOOD verdict_notes:
  GO:      "This is Singapore's largest fintech festival drawing 65,000 attendees including
            CFOs, payments heads, and banking leaders — exactly the buyers you're targeting.
            The conference format gives strong opportunity for structured meetings."
  CONSIDER:"This retail tech expo attracts CMOs and ecommerce heads which partially overlaps
            with your target buyers, but the audience skews more consumer brand than
            enterprise software — worth evaluating if retail is a near-term priority."
  SKIP:    "This is primarily an academic computer science conference targeting researchers
            and students, not the enterprise decision-makers you're selling to. The audience
            won't generate pipeline for your sales motion."

EXAMPLES OF BAD verdict_notes (DO NOT DO THIS):
  ❌ "The event.industry_tags match profile.target_industries."
  ❌ "event.audience_personas aligns with the ICP target_personas field."
  ❌ "This is a good networking event." (too vague)

key_numbers: only include real numbers from the event data (attendee count, VIPs, speakers).
Output ONLY valid JSON. No text outside the JSON object.
"""


# ── Cross-validation agent ─────────────────────────────────────────

VALIDATION_SYSTEM = """You are a quality-control reviewer for B2B event recommendations.

Check each verdict for:
1. Does the verdict (GO/CONSIDER/SKIP) make logical sense given the event data?
2. Does the verdict_notes contain any technical field names like "event.industry_tags",
   "profile.target_personas", "ICP field", etc.? If so, flag hallucination_flag=true.
3. Is verdict_notes written in plain business English? If it's developer-speak, flag it.
4. Are key_numbers fabricated (not in event data)? If so, flag hallucination_flag=true.

Be lenient on GO vs CONSIDER. Only correct SKIP if the event clearly has some buyer overlap.

Return JSON only:
{
  "validations": [
    {
      "id": "<event id>",
      "verdict_ok": true,
      "corrected_verdict": null,
      "hallucination_flag": false,
      "issue": null
    }
  ]
}"""


# ── Serialisers ────────────────────────────────────────────────────

def _event_to_dict(event: EventORM, pre_score: float, pre_tier: str, detail: dict) -> dict:
    """Clean event data for the LLM. Hints included to guide reasoning."""
    return {
        "id": event.id,
        "name": event.name,
        "description": (event.description or "")[:400],
        "start_date": event.start_date,
        "city": event.city,
        "country": event.country,
        "is_virtual": event.is_virtual,
        "is_hybrid": event.is_hybrid,
        "est_attendees": event.est_attendees,
        "vip_count": getattr(event, "vip_count", 0),
        "speaker_count": getattr(event, "speaker_count", 0),
        "category": event.category,
        "industry_focus": event.industry_tags,
        "typical_attendees": event.audience_personas,
        "pricing": event.price_description,
        # Rule engine hints (help LLM calibrate)
        "pre_relevance_score": pre_score,
        "pre_tier_suggestion": pre_tier,
        "rule_matched_industries": detail.get("industry_matched", []),
        "rule_matched_personas": detail.get("persona_matched", []),
        "rule_geo_match": detail.get("geo_matched", ""),
    }


def _profile_to_dict(profile: ICPProfile) -> dict:
    return {
        "company_name": profile.company_name,
        "what_we_do": profile.company_description[:400],
        "target_industries": profile.target_industries,
        "target_buyer_roles": profile.target_personas,
        "target_locations": profile.target_geographies,
        "preferred_event_types": profile.preferred_event_types,
        "max_budget_usd": profile.budget_usd,
        "min_attendees": profile.min_attendees,
    }


def _ranking_prompt(events_dict: list, profile_dict: dict) -> str:
    return f"""CLIENT ICP:
{json.dumps(profile_dict, indent=2)}

EVENTS TO EVALUATE:
{json.dumps(events_dict, indent=2)}

The "pre_tier_suggestion" and "rule_matched_*" fields show what the rule engine already found.
Use these as strong hints — override to SKIP only if you're certain there is zero buyer overlap.

Write verdict_notes in plain sales-analyst language. No technical field names. Be specific.

Return JSON:
{{
  "ranked_events": [
    {{
      "id": "<event id>",
      "fit_verdict": "GO|CONSIDER|SKIP",
      "verdict_notes": "<2-3 plain-English sentences a salesperson would understand>",
      "key_numbers": "<real numbers from event data only>"
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


def _build_key_numbers(event: EventORM) -> str:
    parts = []
    if event.est_attendees:
        parts.append(f"{event.est_attendees:,} attendees")
    if getattr(event, "vip_count", 0):
        parts.append(f"{event.vip_count} VIPs")
    if getattr(event, "speaker_count", 0):
        parts.append(f"{event.speaker_count} speakers")
    return "; ".join(parts) if parts else "See event website"


# ── Main entry ─────────────────────────────────────────────────────

async def rank_with_groq(
    events: List[EventORM],
    profile: ICPProfile,
    pre_scores: Dict[str, float],
    pre_tiers: Dict[str, str],
    pre_details: Dict[str, dict],
    company_ctx: Optional[CompanyContext] = None,
) -> List[RankedEvent]:
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
                            logger.warning(f"Flagged: {v.id} — {v.issue}")
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

    # ── Build output ───────────────────────────────────────────────
    ranked: List[RankedEvent] = []
    for event in events:
        score  = pre_scores.get(event.id, 0.0)
        tier   = pre_tiers.get(event.id, "SKIP")
        detail = pre_details.get(event.id, {})

        if event.id in groq_results and event.id not in hallucinated:
            gr = groq_results[event.id]
            verdict   = gr.fit_verdict
            rationale = gr.verdict_notes
            key_nums  = gr.key_numbers or _build_key_numbers(event)
        else:
            verdict   = tier
            rationale = build_fallback_rationale(event, profile, detail, score, tier)
            key_nums  = _build_key_numbers(event)

        ranked.append(RankedEvent(
            id=event.id,
            event_name=event.name,
            date=(
                event.start_date
                + (f" – {event.end_date}"
                   if event.end_date and event.end_date != event.start_date else "")
            ),
            place=", ".join(filter(None, [event.venue_name, event.city, event.country])),
            event_link=event.registration_url or event.source_url or "",
            what_its_about=(event.short_summary or event.description or "")[:200],
            key_numbers=key_nums,
            industry=event.industry_tags or event.category or "",
            buyer_persona=event.audience_personas or "",
            pricing=(
                event.price_description
                or ("Free" if event.ticket_price_usd == 0 else f"From ${event.ticket_price_usd:.0f}")
            ),
            pricing_link=event.registration_url or event.source_url or "",
            fit_verdict=verdict,
            verdict_notes=rationale,
            sponsors=event.sponsors or "",
            speakers_link=event.speakers_url or "",
            agenda_link=event.agenda_url or "",
            relevance_score=score,
            source_platform=event.source_platform,
            est_attendees=event.est_attendees or 0,
        ))

    return ranked
