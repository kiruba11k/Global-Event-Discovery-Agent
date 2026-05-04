"""
Groq LLM Ranker — v2
────────────────────
• Dynamic system prompt using company context + deck text
• Two-stage validation: primary ranker → cross-validation agent
• Anti-hallucination: strict schema enforcement, field-citation rules
• Fallback: rule-based rationale if Groq unavailable / timeout
Free tier: 14,400 req/day on llama-3.3-70b-versatile
"""
import json
import asyncio
from typing import List, Dict, Optional
from groq import Groq
from pydantic import BaseModel, ValidationError, field_validator
from models.event import EventORM, RankedEvent
from models.icp_profile import ICPProfile, CompanyContext
from config import get_settings
from loguru import logger

settings = get_settings()


# ── Pydantic models ────────────────────────────────────────
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


# ── Groq client singleton ──────────────────────────────────
_groq_client: Optional[Groq] = None


def get_groq_client() -> Optional[Groq]:
    global _groq_client
    if not settings.groq_api_key:
        return None
    if _groq_client is None:
        _groq_client = Groq(api_key=settings.groq_api_key)
    return _groq_client


# ── Build dynamic system prompt ────────────────────────────
def _build_system_prompt(company_ctx: Optional[CompanyContext]) -> str:
    company_section = ""
    if company_ctx:
        parts = []
        if company_ctx.company_name:
            parts.append(f"Company: {company_ctx.company_name}")
        if company_ctx.location:
            parts.append(f"HQ: {company_ctx.location}")
        if company_ctx.founded_year:
            parts.append(f"Founded: {company_ctx.founded_year}")
        if company_ctx.what_we_do:
            parts.append(f"What they do: {company_ctx.what_we_do[:500]}")
        if company_ctx.what_we_need:
            parts.append(f"What they need from events: {company_ctx.what_we_need[:400]}")
        if company_ctx.deck_text:
            parts.append(f"Key context from their company deck:\n{company_ctx.deck_text[:1500]}")

        if parts:
            company_section = f"""
EXTENDED COMPANY CONTEXT (use this to deepen relevance analysis):
{chr(10).join(parts)}

Use this context to:
- Better understand the company's specific product offerings and target market
- Identify which event audiences are most likely to be active buyers
- Assess geographic fit more precisely (HQ location, expansion targets)
- Evaluate whether the event format matches their go-to-market approach
"""

    return f"""You are EventRanker, an elite B2B event relevance analyst for LeadStrategus.
Your job: assess whether each event is worth attending for pipeline generation.
{company_section}
ABSOLUTE RULES — VIOLATIONS ARE NOT PERMITTED:
1. Use ONLY data from the JSON provided. Never invent attendee counts, speaker names, prices, sponsors, or dates.
2. If any field is missing/unknown → output null. Never estimate.
3. Output ONLY valid JSON with key "ranked_events". Zero prose outside JSON.
4. Verdicts:
   GO      → event.industry_tags OR audience_personas directly match ≥2 ICP fields AND geography aligns
   CONSIDER→ partial match, 1 clear signal, some uncertainty, OR strong vertical match but weak geo
   SKIP    → no meaningful ICP overlap, wrong audience, or irrelevant industry
5. verdict_notes MUST cite exact event field names:
   GOOD: "event.audience_personas includes 'CIO' matching profile.target_personas; event.industry_tags has 'fintech' matching profile.target_industries"
   BAD:  "This is a great networking event" (no field cited → REJECT and use CONSIDER instead)
6. Default to CONSIDER when uncertain. Never inflate to GO without ≥2 verified field matches.
7. verdict_notes: 2-3 sentences MAX. Be specific about WHY, not generic praise.
8. key_numbers: use ONLY integers from event.est_attendees, event.vip_count, event.speaker_count.
9. Never reference events not in this prompt's list.
10. If company context was provided, incorporate it into the rationale — e.g. if they sell supply chain software, a logistics expo is a strong GO even with generic industry tags."""


# ── Cross-validation agent prompt ─────────────────────────
VALIDATION_SYSTEM = """You are ValidationAgent, a quality control AI for event relevance scores.
Your task: review event verdicts and flag hallucinations or errors.

Check each verdict:
1. Is the verdict (GO/CONSIDER/SKIP) consistent with the event data provided?
2. Does verdict_notes cite actual event field names from the data (not invented claims)?
3. Are key_numbers real integers from the event data (not invented)?
4. Is there any fabricated information (invented speakers, sponsors, prices)?

Output JSON only:
{
  "validations": [
    {
      "id": "<event id>",
      "verdict_ok": true/false,
      "corrected_verdict": "CONSIDER" (if wrong, else null),
      "hallucination_flag": true/false,
      "issue": "<brief description if problem found, else null>"
    }
  ]
}"""


def _validation_prompt(events_dict: list, primary_results: list) -> str:
    return f"""Validate these event verdicts against the source event data.

SOURCE EVENT DATA:
{json.dumps(events_dict, indent=2)}

PRIMARY VERDICTS TO VALIDATE:
{json.dumps(primary_results, indent=2)}

Return JSON with validation results for each event."""


# ── Event / Profile serialisers ────────────────────────────
def _event_to_dict(event: EventORM) -> dict:
    return {
        "id": event.id,
        "name": event.name,
        "description": (event.description or "")[:400],
        "start_date": event.start_date,
        "city": event.city,
        "country": event.country,
        "est_attendees": event.est_attendees,
        "vip_count": getattr(event, "vip_count", 0),
        "speaker_count": getattr(event, "speaker_count", 0),
        "category": event.category,
        "industry_tags": event.industry_tags,
        "audience_personas": event.audience_personas,
        "price_description": event.price_description,
        "is_virtual": event.is_virtual,
        "is_hybrid": event.is_hybrid,
    }


def _profile_to_dict(profile: ICPProfile) -> dict:
    return {
        "company_name": profile.company_name,
        "company_description": profile.company_description[:400],
        "target_industries": profile.target_industries,
        "target_personas": profile.target_personas,
        "target_geographies": profile.target_geographies,
        "preferred_event_types": profile.preferred_event_types,
        "budget_usd": profile.budget_usd,
        "min_attendees": profile.min_attendees,
    }


# ── LLM call helper ────────────────────────────────────────
async def _call_groq(client: Groq, system: str, user: str, timeout: int) -> Optional[str]:
    try:
        completion = await asyncio.wait_for(
            asyncio.to_thread(
                client.chat.completions.create,
                model=settings.groq_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=settings.groq_temperature,
                max_tokens=settings.groq_max_tokens,
                response_format={"type": "json_object"},
            ),
            timeout=timeout,
        )
        return completion.choices[0].message.content
    except asyncio.TimeoutError:
        logger.error(f"Groq call timed out after {timeout}s")
        return None
    except Exception as e:
        logger.error(f"Groq API error: {e}")
        return None


# ── Fallback rationale ─────────────────────────────────────
def _fallback_rationale(event: EventORM, profile: ICPProfile, tier: str, score: float) -> str:
    event_industries = (event.industry_tags or "").lower()
    event_personas = (event.audience_personas or "").lower()
    event_geo = f"{event.city or ''}, {event.country or ''}".lower()
    event_type = (event.category or "").lower()

    signal_specs = [
        ("event.industry_tags", "profile.target_industries", event_industries, profile.target_industries or [], 3),
        ("event.audience_personas", "profile.target_personas", event_personas, profile.target_personas or [], 3),
        ("event.city/country", "profile.target_geographies", event_geo, profile.target_geographies or [], 2),
        ("event.category", "profile.preferred_event_types", event_type, profile.preferred_event_types or [], 2),
    ]

    strengths, gaps = [], []
    for ev_label, pr_label, ev_val, pr_vals, limit in signal_specs:
        overlaps = [v for v in pr_vals if v and v.lower() in ev_val]
        if overlaps:
            strengths.append(f"{ev_label} matches {pr_label} ({', '.join(overlaps[:limit])})")
        elif pr_vals:
            gaps.append(f"{ev_label} has weak overlap with {pr_label}")

    score_label = "high" if score >= 0.75 else "moderate" if score >= 0.45 else "low"

    if tier == "GO":
        return (
            f"{'; '.join(strengths[:2])}. Verdict GO reflects {score_label} relevance ({score:.2f}) across multiple ICP signals."
            if strengths else f"High semantic overlap with ICP profile ({score:.2f})."
        )
    if tier == "CONSIDER":
        return (
            f"{'; '.join(strengths[:1]) if strengths else 'Some ICP overlap detected'}. "
            f"{gaps[0] if gaps else 'Validate attendee buying authority before committing.'} "
            f"Score: {score:.2f} ({score_label} relevance)."
        )
    return (
        f"SKIP: {gaps[0] if gaps else 'event.industry_tags and event.audience_personas do not match ICP'}. "
        f"Score {score:.2f} ({score_label} relevance) — insufficient signal for pipeline generation."
    )


# ── Main ranking function ──────────────────────────────────
async def rank_with_groq(
    events: List[EventORM],
    profile: ICPProfile,
    pre_scores: Dict[str, float],
    pre_tiers: Dict[str, str],
    company_ctx: Optional[CompanyContext] = None,
) -> List[RankedEvent]:
    """
    Multi-agent ranking pipeline:
    1. Primary Groq ranker with dynamic prompt (+ company context)
    2. Cross-validation agent flags hallucinations
    3. Apply corrections from validator
    4. Fallback to rule-based if Groq unavailable
    """
    client = get_groq_client()
    groq_results: Dict[str, GroqEventResult] = {}
    hallucination_flags: set = set()

    if client and events:
        events_dict = [_event_to_dict(e) for e in events]
        profile_dict = _profile_to_dict(profile)

        system_prompt = _build_system_prompt(company_ctx)

        ranking_prompt = f"""
Company ICP Profile:
{json.dumps(profile_dict, indent=2)}

Events to evaluate (pre-scored by semantic + rule engine, evaluate each for GO/CONSIDER/SKIP):
{json.dumps(events_dict, indent=2)}

Return JSON:
{{
  "ranked_events": [
    {{
      "id": "<event id from input>",
      "fit_verdict": "GO|CONSIDER|SKIP",
      "verdict_notes": "<2-3 sentences citing event field names that justify the verdict>",
      "key_numbers": "<attendees/VIPs/speakers from event data only>"
    }}
  ]
}}
"""

        # ── Agent 1: Primary ranker ────────────────────────
        raw = await _call_groq(
            client, system_prompt, ranking_prompt,
            timeout=settings.groq_timeout_seconds
        )

        if raw:
            try:
                parsed = GroqRankingResponse.model_validate_json(raw)
                for item in parsed.ranked_events:
                    groq_results[item.id] = item
                logger.info(f"Primary ranker: {len(groq_results)} events ranked.")
            except ValidationError as ve:
                logger.error(f"Primary ranker schema validation failed: {ve}")

        # ── Agent 2: Cross-validation ──────────────────────
        if groq_results and len(groq_results) >= 3:
            primary_list = [
                {"id": r.id, "fit_verdict": r.fit_verdict,
                 "verdict_notes": r.verdict_notes, "key_numbers": r.key_numbers}
                for r in groq_results.values()
            ]

            val_raw = await _call_groq(
                client,
                VALIDATION_SYSTEM,
                _validation_prompt(events_dict, primary_list),
                timeout=max(10, settings.groq_timeout_seconds // 2),
            )

            if val_raw:
                try:
                    val_parsed = ValidationResponse.model_validate_json(val_raw)
                    corrections = 0
                    for val in val_parsed.validations:
                        if val.hallucination_flag:
                            hallucination_flags.add(val.id)
                            logger.warning(f"Hallucination detected for {val.id}: {val.issue}")
                        if not val.verdict_ok and val.corrected_verdict and val.id in groq_results:
                            old = groq_results[val.id].fit_verdict
                            groq_results[val.id] = GroqEventResult(
                                id=val.id,
                                fit_verdict=val.corrected_verdict,
                                verdict_notes=f"[Validated: {val.issue}] " + groq_results[val.id].verdict_notes,
                                key_numbers=groq_results[val.id].key_numbers,
                            )
                            corrections += 1
                            logger.info(f"Verdict corrected {val.id}: {old} → {val.corrected_verdict}")
                    logger.info(f"Validation complete: {corrections} corrections, {len(hallucination_flags)} hallucinations flagged.")
                except ValidationError as ve:
                    logger.warning(f"Validation agent schema error: {ve} — skipping corrections")
                except Exception as e:
                    logger.warning(f"Validation agent error: {e}")
        else:
            logger.info("Skipping cross-validation (too few results or Groq unavailable).")

    # ── Build final RankedEvent list ───────────────────────
    ranked: List[RankedEvent] = []
    for event in events:
        score = pre_scores.get(event.id, 0.0)
        tier = pre_tiers.get(event.id, "SKIP")

        if event.id in groq_results and event.id not in hallucination_flags:
            gr = groq_results[event.id]
            verdict = gr.fit_verdict
            rationale = gr.verdict_notes
            key_nums = gr.key_numbers
        elif event.id in groq_results and event.id in hallucination_flags:
            # Hallucinated output — use rule-based fallback for safety
            verdict = tier
            rationale = "[Quality check: reverting to rule-based analysis] " + _fallback_rationale(event, profile, tier, score)
            key_nums = ""
        else:
            verdict = tier
            rationale = _fallback_rationale(event, profile, tier, score)
            key_nums = ""

        if not key_nums:
            parts = []
            if event.est_attendees:
                parts.append(f"{event.est_attendees:,}+ attendees")
            if getattr(event, "vip_count", 0):
                parts.append(f"{event.vip_count}+ VIPs")
            if getattr(event, "speaker_count", 0):
                parts.append(f"{event.speaker_count}+ speakers")
            key_nums = "; ".join(parts) if parts else "See event website"

        ranked.append(RankedEvent(
            id=event.id,
            event_name=event.name,
            date=(
                f"{event.start_date}"
                + (f" – {event.end_date}" if event.end_date and event.end_date != event.start_date else "")
            ),
            place=", ".join(filter(None, [event.venue_name, event.city, event.country])),
            event_link=event.registration_url or event.source_url or "",
            what_its_about=(event.short_summary or event.description or "")[:200],
            key_numbers=key_nums,
            industry=event.industry_tags or event.category or "",
            buyer_persona=event.audience_personas or "",
            pricing=event.price_description or ("Free" if event.ticket_price_usd == 0 else f"From ${event.ticket_price_usd:.0f}"),
            pricing_link=event.registration_url or event.source_url or "",
            fit_verdict=verdict,
            verdict_notes=rationale,
            sponsors=event.sponsors or "",
            speakers_link=event.speakers_url or "",
            agenda_link=event.agenda_url or "",
            relevance_score=score,
            source_platform=event.source_platform,
            est_attendees=event.est_attendees,
        ))

    return ranked
