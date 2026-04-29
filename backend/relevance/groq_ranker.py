"""
Groq LLM Ranker — final ranking + rationale generation.
Anti-hallucination: strict system prompt, JSON schema validation,
temperature=0.1, dual-field citation enforcement.
Free tier: 14,400 req/day on llama-3.3-70b-versatile.
"""
import json
import asyncio
from typing import List, Dict, Optional
from groq import Groq
from pydantic import BaseModel, ValidationError, field_validator
from models.event import EventORM, RankedEvent
from models.icp_profile import ICPProfile
from config import get_settings
from loguru import logger

settings = get_settings()

# ─── STRICT SYSTEM PROMPT ─────────────────────────────────────────
SYSTEM_PROMPT = """You are EventRanker, a precise B2B event relevance analyst.

ABSOLUTE RULES — VIOLATION IS NOT PERMITTED:
1. Use ONLY data from the JSON provided. Never invent attendee counts, speaker names, prices, sponsors, or dates.
2. If any field is unknown or missing, output: null — never guess or estimate.
3. Output ONLY a valid JSON object with key "ranked_events" containing an array. Zero prose outside JSON.
4. Assign verdict from exactly: GO, CONSIDER, or SKIP — no other values.
   - GO:      event.industry_tags OR event.audience_personas directly match ≥2 profile fields
   - CONSIDER: partial match, 1 clear signal, remaining uncertain
   - SKIP:    no meaningful overlap with ICP
5. rationale MUST cite the exact event field name that justifies the verdict, e.g.:
   GOOD: "event.audience_personas includes 'CIO' matching profile.target_personas"
   BAD:  "This is a great event for networking" (no field cited → REJECT)
6. Default to CONSIDER when uncertain. Never inflate to GO without ≥2 field matches.
7. verdict_notes must be 1-2 sentences maximum.
8. Do not reference any event not present in this prompt's event list.
9. key_numbers must only use integers/strings from event.est_attendees, event.vip_count, event.speaker_count fields."""

RANKING_PROMPT_TEMPLATE = """
Company Profile:
{profile_json}

Events to rank (ranked by semantic similarity, evaluate each):
{events_json}

Return JSON:
{{
  "ranked_events": [
    {{
      "id": "<event id from input>",
      "fit_verdict": "GO|CONSIDER|SKIP",
      "verdict_notes": "<1-2 sentence rationale citing field names>",
      "key_numbers": "<attendees, VIPs, speakers from event data only>"
    }}
  ]
}}
"""


# ─── Pydantic validation model for Groq output ────────────────────
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


# ─── Groq client (singleton) ──────────────────────────────────────
_groq_client: Optional[Groq] = None


def get_groq_client() -> Optional[Groq]:
    global _groq_client
    if not settings.groq_api_key:
        return None
    if _groq_client is None:
        _groq_client = Groq(api_key=settings.groq_api_key)
    return _groq_client


def _event_to_dict(event: EventORM) -> dict:
    """Minimal, DB-verified event dict for the LLM prompt. No invented fields."""
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
    }


def _fallback_rationale(event: EventORM, profile: ICPProfile, tier: str) -> str:
    """Rule-based rationale when Groq is unavailable."""
    ind_overlap = [i for i in profile.target_industries if i.lower() in (event.industry_tags or "").lower()]
    persona_overlap = [p for p in profile.target_personas if p.lower() in (event.audience_personas or "").lower()]

    if tier == "GO":
        reasons = []
        if ind_overlap:
            reasons.append(f"event.industry_tags matches profile.target_industries: {', '.join(ind_overlap)}")
        if persona_overlap:
            reasons.append(f"event.audience_personas includes: {', '.join(persona_overlap)}")
        return ". ".join(reasons) if reasons else "Strong semantic overlap with company profile."
    if tier == "CONSIDER":
        return "Partial overlap with ICP. Verify attendee mix before committing."
    return "No significant overlap with target industries or personas."


async def rank_with_groq(
    events: List[EventORM],
    profile: ICPProfile,
    pre_scores: Dict[str, float],
    pre_tiers: Dict[str, str],
) -> List[RankedEvent]:
    """
    Use Groq to generate final verdicts + rationales.
    Falls back to rule-based rationale if Groq unavailable.
    """
    client = get_groq_client()
    groq_results: Dict[str, GroqEventResult] = {}

    if client and events:
        try:
            events_dict = [_event_to_dict(e) for e in events]
            profile_dict = _profile_to_dict(profile)

            prompt = RANKING_PROMPT_TEMPLATE.format(
                profile_json=json.dumps(profile_dict, indent=2),
                events_json=json.dumps(events_dict, indent=2),
            )

            completion = await asyncio.wait_for(
                asyncio.to_thread(
                    client.chat.completions.create,
                    model=settings.groq_model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=settings.groq_temperature,
                    max_tokens=settings.groq_max_tokens,
                    response_format={"type": "json_object"},
                ),
                timeout=settings.groq_timeout_seconds,
            )

            raw = completion.choices[0].message.content

            # ── L2: Pydantic schema validation ──────────────────
            parsed = GroqRankingResponse.model_validate_json(raw)
            for item in parsed.ranked_events:
                groq_results[item.id] = item

            logger.info(f"Groq ranked {len(groq_results)} events successfully.")

        except ValidationError as ve:
            logger.error(f"Groq output failed schema validation: {ve}")
        except asyncio.TimeoutError:
            logger.error(
                f"Groq call exceeded {settings.groq_timeout_seconds}s timeout. "
                "Falling back to rule-based rationale."
            )
        except Exception as e:
            logger.error(f"Groq API error: {e}. Falling back to rule-based rationale.")

    # ── Build final RankedEvent list ───────────────────────────
    ranked: List[RankedEvent] = []

    for event in events:
        score = pre_scores.get(event.id, 0.0)
        tier = pre_tiers.get(event.id, "SKIP")

        if event.id in groq_results:
            gr = groq_results[event.id]
            verdict = gr.fit_verdict
            rationale = gr.verdict_notes
            key_nums = gr.key_numbers
        else:
            verdict = tier
            rationale = _fallback_rationale(event, profile, tier)
            parts = []
            if event.est_attendees:
                parts.append(f"{event.est_attendees:,}+ attendees")
            if getattr(event, "vip_count", 0):
                parts.append(f"{event.vip_count}+ VIPs")
            if getattr(event, "speaker_count", 0):
                parts.append(f"{event.speaker_count}+ speakers")
            key_nums = "; ".join(parts) if parts else "See event website"

        # ── L3: Numeric guard — never let LLM override DB values ─
        # (key_nums is display-only; actual scores come from DB)

        ranked.append(RankedEvent(
            id=event.id,
            event_name=event.name,
            date=f"{event.start_date}" + (f" – {event.end_date}" if event.end_date and event.end_date != event.start_date else ""),
            place=f"{event.venue_name}, {event.city}, {event.country}".strip(", "),
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
        ))

    return ranked
