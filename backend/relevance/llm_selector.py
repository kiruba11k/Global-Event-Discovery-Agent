"""
relevance/llm_selector.py — Layer 5 of the search pipeline: single LLM
call picks the top 6 of 12 candidates, each with a reason AND a
GO/CONSIDER verdict (the LLM's own judgment per event, not a positional
3+3 split). No SKIP here — anything selected into the top 6 already
cleared the bar; SKIP only applies to events that never made the cut,
which this function doesn't surface at all.
"""
from __future__ import annotations

import json
from typing import List, Optional

from loguru import logger
from pydantic import BaseModel, field_validator

from config import get_settings
from models.event import EventORM
from relevance.llm_client import llm

settings = get_settings()


class SelectedEvent(BaseModel):
    event_id: str
    reason: str = ""
    verdict: str = "CONSIDER"

    model_config = {"extra": "ignore"}

    @field_validator("reason", mode="before")
    @classmethod
    def _clean(cls, v):
        return (str(v or "")).strip()

    @field_validator("verdict", mode="before")
    @classmethod
    def _check_verdict(cls, v) -> str:
        # Forgiving, mirrors groq_ranker.GroqEventResult's own validator:
        # never reject the whole event for a fixable verdict. No SKIP —
        # this schema is only for events already selected into the top 6.
        v = str(v or "").strip().upper()
        if v not in {"GO", "CONSIDER"}:
            if "GO" in v and "CONSIDER" not in v:
                return "GO"
            return "CONSIDER"
        return v


class SelectionResponse(BaseModel):
    selected: List[SelectedEvent] = []

    model_config = {"extra": "ignore"}


class ReasonCheck(BaseModel):
    event_id: str
    grounded: bool = True
    issue: Optional[str] = None

    model_config = {"extra": "ignore"}


class ReasonValidationResponse(BaseModel):
    checks: List[ReasonCheck] = []

    model_config = {"extra": "ignore"}


_SYSTEM = """You are a B2B sales strategist picking the {n} best trade events for a client
from a shortlist of pre-scored candidates.

Each candidate includes a blended_score (0-1, from keyword + semantic matching) as a
prior — trust it as a strong signal but you may re-rank based on the event's own
description, industry focus and location matching the client's ICP.

Pick EXACTLY {n} events. For each:
- reason: 1-2 sentences grounded ONLY in that event's own data (name, description,
  industry_focus, location) — never invent facts, never reference the client's
  wishlist as if the event confirmed it.
- verdict: "GO" or "CONSIDER" — your own judgment per event, not a fixed split.
    GO       = strong, clear match: industry, location and (if known) buyer role
               all line up well with the client's ICP.
    CONSIDER = a real match worth showing, but with a genuine gap or uncertainty
               (e.g. industry fits but buyer role is unconfirmed, or it's a
               plausible-but-not-perfect geography match).
  Do not force a fixed ratio of GO vs CONSIDER — judge each event on its own
  merits; it is fine for all 6 to be GO, or all 6 to be CONSIDER, if that is
  genuinely what the data supports.

Output ONLY valid JSON:
{{"selected": [{{"event_id": "...", "reason": "...", "verdict": "GO|CONSIDER"}}]}}"""


def _event_dict(event: EventORM, blended_score: float) -> dict:
    return {
        "id": event.id,
        "name": event.name,
        "description": (event.description or event.short_summary or "")[:300],
        "industry_focus": (getattr(event, "related_industries", "") or event.industry_tags or event.category or ""),
        "location": f"{event.city or ''}, {event.country or ''}".strip(", "),
        "start_date": event.start_date,
        "blended_score": round(blended_score, 4),
    }


def build_selection_prompt(icp_profile: dict, candidates: list) -> str:
    """candidates: list[(EventORM, blended_score)]."""
    events_payload = [_event_dict(e, s) for e, s in candidates]
    profile_payload = {
        "target_industries": [p.get("industry", "") for p in icp_profile.get("pairs", []) if p.get("industry")],
        "target_personas":   [p.get("persona", "") for p in icp_profile.get("pairs", []) if p.get("persona")],
        "region":             icp_profile.get("region", {}).get("canonical_geo", ""),
    }
    return (
        f"CLIENT ICP:\n{json.dumps(profile_payload, indent=2)}\n\n"
        f"CANDIDATES ({len(events_payload)}):\n{json.dumps(events_payload, indent=2)}"
    )


async def select_top_6(
    icp_profile: dict,
    candidates: list,
    n: Optional[int] = None,
) -> list[dict]:
    """
    candidates: [(EventORM, blended_score), ...] — the Layer 4 output.
    Returns [{"event_id": str, "reason": str, "verdict": "GO"|"CONSIDER"}, ...],
    length <= n. Falls back to the top-n by blended_score (empty reason,
    verdict defaulted from blended_score) if the LLM call fails —
    selection must never come back empty just because the LLM was
    unavailable.
    """
    n = n or settings.selection_size
    if not candidates:
        return []

    candidate_ids = {e.id for e, _ in candidates}
    system = _SYSTEM.format(n=n)
    user = build_selection_prompt(icp_profile, candidates)

    parsed = await llm.chat_json(
        system,
        user,
        label="selector",
        schema=SelectionResponse,
        max_completion_tokens=max(500, n * 150),
        timeout=settings.openai_timeout_seconds,
        cache_ttl=600,
    )

    if parsed is None or not parsed.selected:
        logger.warning("llm_selector: selection failed — falling back to "
                        "top-N by blended_score")
        top = sorted(candidates, key=lambda pair: -pair[1])[:n]
        return [_fallback_entry(e, s) for e, s in top]

    selected: list[dict] = []
    seen_ids: set = set()
    for item in parsed.selected:
        if item.event_id not in candidate_ids:
            logger.warning(f"llm_selector: dropping unknown id '{item.event_id}' "
                            "not in candidate set")
            continue
        if item.event_id in seen_ids:
            logger.warning(f"llm_selector: dropping duplicate id '{item.event_id}' "
                            "returned more than once")
            continue
        seen_ids.add(item.event_id)
        selected.append({"event_id": item.event_id, "reason": item.reason,
                          "verdict": item.verdict})

    if len(selected) < n:
        chosen_ids = {s["event_id"] for s in selected}
        backfill = sorted(
            (pair for pair in candidates if pair[0].id not in chosen_ids),
            key=lambda pair: -pair[1],
        )
        for e, s in backfill[: n - len(selected)]:
            selected.append(_fallback_entry(e, s))

    return selected[:n]


def _fallback_entry(event: EventORM, blended_score: float) -> dict:
    """
    Used when the LLM didn't cover an event (call failed, or it filled
    fewer than n slots and this is backfilled by score). No LLM judgment
    exists for it, so verdict is derived from the same blended_score
    that ranked it here — above the midpoint of the pipeline's own
    weight split (keyword_weight + semantic_weight, i.e. a "both signals
    at least moderately agree" bar) is GO, otherwise CONSIDER.
    """
    go_bar = (settings.keyword_match_weight + settings.semantic_match_weight) * 0.5
    verdict = "GO" if blended_score >= go_bar else "CONSIDER"
    return {"event_id": event.id, "reason": "", "verdict": verdict}


async def validate_reasons(
    selected: list[dict],
    candidates: list,
) -> list[dict]:
    """
    Cheap fact-check pass: does each reason reference something actually
    in that event's own data? Flags (doesn't discard) hallucinated
    reasons — logs for now, since a wrong-but-plausible reason is a
    quality issue to track, not a hard failure that should shrink the
    result below n.
    """
    if not selected:
        return selected

    by_id = {e.id: e for e, _ in candidates}
    slim = [
        {
            "event_id": s["event_id"],
            "reason": s["reason"],
            "event_name": getattr(by_id.get(s["event_id"]), "name", ""),
            "industry_focus": getattr(by_id.get(s["event_id"]), "related_industries", "") or "",
        }
        for s in selected if s["event_id"] in by_id and s["reason"]
    ]
    if not slim:
        return selected

    val = await llm.chat_json(
        "You are a QA reviewer. For each reason, check it only references facts "
        "plausibly grounded in that event's own name/industry_focus — flag "
        "grounded=false if it invents specifics not implied by the data.\n"
        'Return ONLY: {"checks": [{"event_id": "...", "grounded": true, "issue": null}]}',
        json.dumps(slim, indent=2),
        label="reason-validator",
        schema=ReasonValidationResponse,
        max_completion_tokens=min(800, 80 * len(slim) + 100),
        timeout=15,
        cache_ttl=600,
    )
    if val is None:
        return selected

    flagged = {c.event_id: c.issue for c in val.checks if not c.grounded}
    for s in selected:
        if s["event_id"] in flagged:
            logger.warning(f"llm_selector: reason flagged for {s['event_id']}: "
                            f"{flagged[s['event_id']]}")
    return selected
