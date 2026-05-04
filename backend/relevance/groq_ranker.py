"""
Groq LLM Ranker v2 — dynamic prompt, cross-validation agent, grounded rationale.

Anti-hallucination layers:
  L1 — system prompt with field-citation requirement
  L2 — Pydantic schema validation of LLM output
  L3 — cross-validation agent flags fabricated data
  L4 — rule-based fallback when Groq unavailable or fails

Dynamic prompt: company context + deck text + pre-computed match signals
  so the LLM explains WHY, using the actual data it received.
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


# ── Groq client singleton ──────────────────────────────────────────

_groq_client: Optional[Groq] = None


def get_groq_client() -> Optional[Groq]:
    global _groq_client
    if not settings.groq_api_key:
        return None
    if _groq_client is None:
        _groq_client = Groq(api_key=settings.groq_api_key)
    return _groq_client


# ── Dynamic system prompt builder ─────────────────────────────────

def _build_system_prompt(
    profile: ICPProfile,
    company_ctx: Optional[CompanyContext],
) -> str:
    """
    Build a rich, data-driven system prompt.
    Injects company context + deck text so the LLM has maximum signal.
    """
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
            parts.append(f"What they do/sell:\n{company_ctx.what_we_do[:600]}")
        if company_ctx.what_we_need:
            parts.append(f"What they need from events:\n{company_ctx.what_we_need[:500]}")
        if company_ctx.deck_text:
            parts.append(
                f"Context extracted from their company deck (use this for deeper matching):\n"
                f"{company_ctx.deck_text[:2000]}"
            )
        if parts:
            company_block = "\n\nEXTENDED COMPANY CONTEXT:\n" + "\n".join(parts)

    # Stringify profile for reference in prompt
    icp_summary = (
        f"  target_industries: {profile.target_industries}\n"
        f"  target_personas: {profile.target_personas}\n"
        f"  target_geographies: {profile.target_geographies}\n"
        f"  preferred_event_types: {profile.preferred_event_types}\n"
        f"  company_description: {profile.company_description[:300]}"
    )

    return f"""You are EventRanker, an elite B2B sales event analyst for LeadStrategus.
Your job: determine whether each event is worth attending for sales pipeline generation.

ICP PROFILE SUMMARY:
{icp_summary}
{company_block}

VERDICT DEFINITIONS — use these precisely:
  GO      = event.industry_tags OR event.audience_personas clearly match ≥1 profile signal
             AND geography is acceptable (or event is virtual/global)
             → Recommend attending. Strong pipeline potential.
  CONSIDER = some ICP overlap but missing 1-2 key signals (e.g. right industry, wrong geo)
             OR signals are indirect (related field, adjacent persona)
             → Worth evaluating. Validate before committing budget.
  SKIP    = no meaningful overlap between event data and ICP
             (completely different industry, wrong audience, irrelevant geography)
             → Not worth pursuing for this ICP.

ABSOLUTE RULES:
1. Use ONLY data from the JSON provided. Never invent speaker names, sponsors, prices, or dates.
2. If a field is missing/null in event data → say "not specified", never guess.
3. Output ONLY valid JSON with key "ranked_events". Zero prose outside JSON.
4. verdict_notes MUST cite specific event field names and actual values:
     CORRECT: "event.industry_tags ('fintech,payments') directly matches profile.target_industries"
     WRONG:   "This is a great networking opportunity" (no field citation = REJECT, use CONSIDER)
5. Be generous with GO for events with even 1 clear industry OR persona match.
   Only SKIP if there is genuinely no overlap at all.
6. verdict_notes: 2-3 sentences. Specific field citations. No vague praise.
7. key_numbers: use ONLY integers from event.est_attendees, event.vip_count, event.speaker_count.
8. If company deck context was provided, incorporate those insights into your rationale.
   e.g. if the deck says they sell supply chain software → a logistics expo is a GO.
"""


# ── Cross-validation agent ─────────────────────────────────────────

VALIDATION_SYSTEM = """You are ValidationAgent, a quality-control AI for event relevance verdicts.

Review each verdict and check:
1. Does the verdict (GO/CONSIDER/SKIP) logically follow from the event data?
   - GO needs at least 1 clear industry OR persona match
   - SKIP should only be used when there is genuinely NO overlap
2. Does verdict_notes cite actual field values from the event data (not invented content)?
3. Are key_numbers actual integers from the event data (not fabricated)?
4. Flag any hallucinated data (invented speakers, sponsors, prices not in event data).

Be LENIENT with GO verdicts — only correct if the event clearly has zero ICP overlap.
Correct SKIP → CONSIDER if there's any reasonable industry or persona connection.

Output JSON only:
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


# ── Prompt builders ────────────────────────────────────────────────

def _event_to_dict(event: EventORM, pre_score: float, pre_tier: str, detail: dict) -> dict:
    """Minimal, DB-verified dict. Includes pre-score and match detail as hints."""
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
        "industry_tags": event.industry_tags,
        "audience_personas": event.audience_personas,
        "price_description": event.price_description,
        # Hints from rule engine (helps LLM calibrate)
        "_pre_score": pre_score,
        "_pre_tier": pre_tier,
        "_rule_industry_matches": detail.get("industry_matched", []),
        "_rule_persona_matches": detail.get("persona_matched", []),
        "_rule_geo": detail.get("geo_matched", ""),
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


def _build_ranking_prompt(events_dict: list, profile_dict: dict) -> str:
    return f"""ICP Profile:
{json.dumps(profile_dict, indent=2)}

Events to evaluate (pre-scored by rule engine — _pre_tier and _rule_* fields are hints):
{json.dumps(events_dict, indent=2)}

For each event, determine GO / CONSIDER / SKIP and explain WHY using exact field names and values.
When _rule_industry_matches or _rule_persona_matches are non-empty, that is evidence of overlap.
Only override a _pre_tier of GO/CONSIDER to SKIP if you are certain there is zero ICP relevance.

Return JSON:
{{
  "ranked_events": [
    {{
      "id": "<event id>",
      "fit_verdict": "GO|CONSIDER|SKIP",
      "verdict_notes": "<2-3 sentences citing event field names and values>",
      "key_numbers": "<attendees/VIPs/speakers from event data only>"
    }}
  ]
}}"""


def _build_validation_prompt(events_dict: list, primary_results: list) -> str:
    return f"""SOURCE EVENT DATA:
{json.dumps(events_dict, indent=2)}

PRIMARY VERDICTS TO VALIDATE:
{json.dumps(primary_results, indent=2)}

Check each verdict. Be lenient — only flag clear errors or fabricated data.
Return validation JSON."""


# ── LLM call helper ────────────────────────────────────────────────

async def _call_groq(
    client: Groq,
    system: str,
    user: str,
    timeout: int,
    label: str = "groq",
) -> Optional[str]:
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
        logger.error(f"[{label}] timed out after {timeout}s")
    except Exception as e:
        logger.error(f"[{label}] error: {e}")
    return None


# ── Key number builder ─────────────────────────────────────────────

def _build_key_numbers(event: EventORM) -> str:
    parts = []
    if event.est_attendees:
        parts.append(f"{event.est_attendees:,} attendees")
    if getattr(event, "vip_count", 0):
        parts.append(f"{event.vip_count} VIPs")
    if getattr(event, "speaker_count", 0):
        parts.append(f"{event.speaker_count} speakers")
    return "; ".join(parts) if parts else "See event website"


# ── Main ranking function ──────────────────────────────────────────

async def rank_with_groq(
    events: List[EventORM],
    profile: ICPProfile,
    pre_scores: Dict[str, float],
    pre_tiers: Dict[str, str],
    pre_details: Dict[str, dict],
    company_ctx: Optional[CompanyContext] = None,
) -> List[RankedEvent]:
    """
    Two-agent pipeline:
      Agent 1 — primary ranker with dynamic system prompt + company context
      Agent 2 — cross-validator flags hallucinations and corrects clear errors
    Falls back to rule-based rationale if Groq is unavailable.
    """
    client = get_groq_client()
    groq_results: Dict[str, GroqEventResult] = {}
    hallucinated: set = set()

    if client and events:
        events_dict = [
            _event_to_dict(e, pre_scores.get(e.id, 0.0), pre_tiers.get(e.id, "SKIP"),
                           pre_details.get(e.id, {}))
            for e in events
        ]
        profile_dict  = _profile_to_dict(profile)
        system_prompt = _build_system_prompt(profile, company_ctx)
        ranking_prompt = _build_ranking_prompt(events_dict, profile_dict)

        # ── Agent 1: Primary ranker ────────────────────────────────
        raw = await _call_groq(
            client, system_prompt, ranking_prompt,
            timeout=settings.groq_timeout_seconds,
            label="primary-ranker",
        )
        if raw:
            try:
                parsed = GroqRankingResponse.model_validate_json(raw)
                for item in parsed.ranked_events:
                    groq_results[item.id] = item
                logger.info(f"Primary ranker: {len(groq_results)} events ranked.")
            except ValidationError as ve:
                logger.error(f"Primary ranker schema error: {ve}")

        # ── Agent 2: Cross-validator ───────────────────────────────
        if len(groq_results) >= 3:
            primary_list = [
                {
                    "id": r.id,
                    "fit_verdict": r.fit_verdict,
                    "verdict_notes": r.verdict_notes,
                    "key_numbers": r.key_numbers,
                }
                for r in groq_results.values()
            ]
            val_raw = await _call_groq(
                client,
                VALIDATION_SYSTEM,
                _build_validation_prompt(events_dict, primary_list),
                timeout=max(10, settings.groq_timeout_seconds // 2),
                label="validator",
            )
            if val_raw:
                try:
                    val_parsed = ValidationResponse.model_validate_json(val_raw)
                    corrections = 0
                    for val in val_parsed.validations:
                        if val.hallucination_flag:
                            hallucinated.add(val.id)
                            logger.warning(f"Hallucination flagged: {val.id} — {val.issue}")
                        if (not val.verdict_ok
                                and val.corrected_verdict
                                and val.id in groq_results):
                            old = groq_results[val.id].fit_verdict
                            groq_results[val.id] = GroqEventResult(
                                id=val.id,
                                fit_verdict=val.corrected_verdict,
                                verdict_notes=(
                                    f"[Corrected: {val.issue}] "
                                    + groq_results[val.id].verdict_notes
                                ),
                                key_numbers=groq_results[val.id].key_numbers,
                            )
                            corrections += 1
                            logger.info(f"Corrected: {val.id} {old}→{val.corrected_verdict}")
                    logger.info(
                        f"Validation done: {corrections} corrections, "
                        f"{len(hallucinated)} hallucinations."
                    )
                except ValidationError as ve:
                    logger.warning(f"Validator schema error: {ve} — skipping")
                except Exception as e:
                    logger.warning(f"Validator error: {e}")
        else:
            logger.info("Skipping cross-validation (too few Groq results).")

    # ── Assemble final list ────────────────────────────────────────
    ranked: List[RankedEvent] = []

    for event in events:
        score  = pre_scores.get(event.id, 0.0)
        tier   = pre_tiers.get(event.id, "SKIP")
        detail = pre_details.get(event.id, {})

        # Use Groq result unless it hallucinated
        if event.id in groq_results and event.id not in hallucinated:
            gr = groq_results[event.id]
            verdict  = gr.fit_verdict
            rationale = gr.verdict_notes
            key_nums = gr.key_numbers or _build_key_numbers(event)
        else:
            # Fully dynamic rule-based fallback
            verdict  = tier
            rationale = build_fallback_rationale(event, profile, detail, score, tier)
            key_nums = _build_key_numbers(event)
            if event.id in hallucinated:
                rationale = "[Quality-check fallback] " + rationale

        ranked.append(RankedEvent(
            id=event.id,
            event_name=event.name,
            date=(
                event.start_date
                + (f" – {event.end_date}"
                   if event.end_date and event.end_date != event.start_date
                   else "")
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
