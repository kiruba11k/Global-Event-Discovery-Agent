"""
Hybrid Scorer v2 — rule-based event relevance scoring.

Key fixes vs v1:
- Tokenised ICP value matching: "AI / Machine Learning" → ["ai", "machine learning"]
  so it actually matches "machine learning" in event tags
- Bidirectional matching: checks event→ICP and ICP→event
- Calibrated thresholds: 0.45 GO, 0.22 CONSIDER (realistic for rule-only mode)
- Dynamic match logging for transparent rationale building
"""
import re
from typing import List, Dict, Tuple, Optional
from models.event import EventORM
from models.icp_profile import ICPProfile
from config import get_settings
from loguru import logger

settings = get_settings()

TIER_GO       = "GO"
TIER_CONSIDER = "CONSIDER"
TIER_SKIP     = "SKIP"

# Calibrated thresholds for rule-only mode (no semantic search)
RULE_ONLY_GO_THRESHOLD       = 0.45
RULE_ONLY_CONSIDER_THRESHOLD = 0.22


# ── Token helpers ──────────────────────────────────────────────────

def _tokenise(text: str) -> List[str]:
    """
    Split an ICP label like "AI / Machine Learning" or "Fintech"
    into meaningful match tokens: ["ai", "machine learning", "fintech"]
    """
    if not text:
        return []
    parts = re.split(r"[/,|]", text)
    tokens = []
    for part in parts:
        cleaned = part.strip().lower()
        if cleaned and len(cleaned) > 1:
            tokens.append(cleaned)
            # Also add individual words for fuzzy fallback
            words = [w for w in cleaned.split() if len(w) > 2]
            tokens.extend(words)
    seen, out = set(), []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _build_event_text(event: EventORM) -> str:
    return " ".join(filter(None, [
        event.name or "",
        event.industry_tags or "",
        event.audience_personas or "",
        event.category or "",
        event.description or "",
        event.short_summary or "",
        event.city or "",
        event.country or "",
    ])).lower()


def _token_match(profile_values: List[str], search_text: str) -> Tuple[int, List[str]]:
    """How many profile values have at least one token present in search_text."""
    matched = []
    for val in profile_values:
        tokens = _tokenise(val)
        if any(tok in search_text for tok in tokens):
            matched.append(val)
    return len(matched), matched


def _reverse_match(event_tag_str: str, profile_values: List[str]) -> List[str]:
    """
    Reverse check: event tags that appear in profile value tokens.
    Catches: event has "fintech", ICP has "Fintech" or "Financial Technology".
    """
    if not event_tag_str:
        return []
    profile_tokens = set()
    for v in profile_values:
        profile_tokens.update(_tokenise(v))
    matched = []
    for tag in re.split(r"[,;\s]+", event_tag_str.lower()):
        tag = tag.strip()
        if tag and len(tag) > 2 and tag in profile_tokens:
            matched.append(tag)
    return list(set(matched))


# ── Core rule scorer ───────────────────────────────────────────────

def _rule_score(event: EventORM, profile: ICPProfile) -> Tuple[float, dict]:
    """
    Score 0.0–1.0 with full match detail for dynamic rationale.
    """
    score = 0.0
    detail: dict = {
        "industry_matched": [],
        "industry_missed": False,
        "persona_matched": [],
        "persona_missed": False,
        "geo_matched": "",
        "geo_missed": False,
        "type_matched": False,
        "attendee_tier": "",
    }

    event_text    = _build_event_text(event)
    industry_tags = (event.industry_tags or "").lower()
    persona_tags  = (event.audience_personas or "").lower()

    # ── Industry — weight 0.32 ────────────────────────────────────
    _, ind_fwd = _token_match(profile.target_industries, event_text)
    ind_rev    = _reverse_match(industry_tags, profile.target_industries)
    all_ind    = list(dict.fromkeys(ind_fwd + ind_rev))

    if   len(all_ind) >= 3: score += 0.32
    elif len(all_ind) == 2: score += 0.26
    elif len(all_ind) == 1: score += 0.18
    else:                   detail["industry_missed"] = True

    detail["industry_matched"] = all_ind[:4]

    # ── Persona — weight 0.28 ─────────────────────────────────────
    _, per_fwd = _token_match(profile.target_personas, persona_tags)
    per_rev    = _reverse_match(persona_tags, profile.target_personas)
    all_per    = list(dict.fromkeys(per_fwd + per_rev))

    if   len(all_per) >= 2: score += 0.28
    elif len(all_per) == 1: score += 0.18
    else:                   detail["persona_missed"] = True

    detail["persona_matched"] = all_per[:4]

    # ── Geography — weight 0.22 ───────────────────────────────────
    geo_text  = f"{event.city or ''} {event.country or ''}".lower()
    is_global = any(g.lower() in ("global", "worldwide", "international", "any")
                    for g in (profile.target_geographies or []))

    if is_global:
        score += 0.22
        detail["geo_matched"] = "Global"
    else:
        _, geo_matched = _token_match(profile.target_geographies, geo_text)
        if geo_matched:
            score += 0.22
            detail["geo_matched"] = geo_matched[0]
        elif event.is_virtual or event.is_hybrid:
            score += 0.12
            detail["geo_matched"] = "Virtual/Hybrid"
        else:
            detail["geo_missed"] = True

    # ── Event type — weight 0.10 ──────────────────────────────────
    type_text = f"{event.category or ''} {event.name or ''}".lower()
    type_hits = []
    for t in (profile.preferred_event_types or []):
        if any(tok in type_text for tok in _tokenise(t)):
            type_hits.append(t)
    if type_hits:
        score += 0.10
        detail["type_matched"] = True

    # ── Attendee size — weight 0.08 ───────────────────────────────
    att = event.est_attendees or 0
    if   att >= 10000: score += 0.08; detail["attendee_tier"] = f"{att:,}+ attendees (flagship)"
    elif att >= 5000:  score += 0.07; detail["attendee_tier"] = f"{att:,}+ attendees (large)"
    elif att >= 1000:  score += 0.05; detail["attendee_tier"] = f"{att:,} attendees (mid-size)"
    elif att >= max(profile.min_attendees or 0, 200):
        score += 0.03; detail["attendee_tier"] = f"{att:,} attendees"
    elif att > 0:
        score += 0.01; detail["attendee_tier"] = f"{att} attendees (boutique)"

    return round(min(score, 1.0), 4), detail


def _tier(score: float, semantic_active: bool) -> str:
    if semantic_active:
        go_t = settings.go_threshold
        con_t = settings.consider_threshold
    else:
        go_t = RULE_ONLY_GO_THRESHOLD
        con_t = RULE_ONLY_CONSIDER_THRESHOLD
    if score >= go_t:       return TIER_GO
    if score >= con_t:      return TIER_CONSIDER
    return TIER_SKIP


def build_fallback_rationale(event: EventORM, profile: ICPProfile,
                              detail: dict, score: float, tier: str) -> str:
    """
    Build a fully dynamic rationale from actual match data.
    Called by groq_ranker when Groq is unavailable.
    """
    strengths, gaps = [], []

    if detail.get("industry_matched"):
        strengths.append(
            f"event.industry_tags matches profile.target_industries on: "
            f"{', '.join(detail['industry_matched'][:3])}"
        )
    elif detail.get("industry_missed"):
        gaps.append(
            f"event.industry_tags ('{(event.industry_tags or 'unknown')[:50]}') "
            f"has no overlap with profile.target_industries "
            f"({', '.join((profile.target_industries or [])[:3])})"
        )

    if detail.get("persona_matched"):
        strengths.append(
            f"event.audience_personas matches profile.target_personas on: "
            f"{', '.join(detail['persona_matched'][:3])}"
        )
    elif detail.get("persona_missed"):
        gaps.append(
            f"event.audience_personas ('{(event.audience_personas or 'unknown')[:50]}') "
            f"doesn't match profile.target_personas "
            f"({', '.join((profile.target_personas or [])[:3])})"
        )

    if detail.get("geo_matched"):
        strengths.append(
            f"event location ({event.city}, {event.country}) "
            f"satisfies profile.target_geographies ({detail['geo_matched']})"
        )
    elif detail.get("geo_missed"):
        gaps.append(
            f"event location ({event.city}, {event.country}) "
            f"is outside profile.target_geographies "
            f"({', '.join((profile.target_geographies or [])[:3])})"
        )

    if detail.get("type_matched"):
        strengths.append(
            f"event.category '{event.category}' matches profile.preferred_event_types"
        )

    if detail.get("attendee_tier"):
        strengths.append(detail["attendee_tier"])

    score_pct = int(score * 100)
    signal_summary = f"Relevance score: {score_pct}%"

    if tier == TIER_GO:
        verdict_line = (
            f"GO — strong ICP match across {len(strengths)} signal(s). "
            f"{signal_summary}. Recommended for pipeline generation."
        )
    elif tier == TIER_CONSIDER:
        gap_note = f" Gap: {gaps[0]}." if gaps else " Validate attendee buying authority."
        verdict_line = f"CONSIDER — partial ICP match. {signal_summary}.{gap_note}"
    else:
        gap_note = f" {'; '.join(gaps[:2])}." if gaps else " Insufficient ICP signal overlap."
        verdict_line = f"SKIP — weak ICP match. {signal_summary}.{gap_note}"

    parts = strengths + [verdict_line]
    return " | ".join(parts)


# ── Public API ─────────────────────────────────────────────────────

def score_candidates(
    events: List[EventORM],
    profile: ICPProfile,
    cosine_scores: Dict[str, float],
) -> List[Tuple[EventORM, float, str, dict]]:
    """
    Returns sorted list of (event, hybrid_score, tier, match_detail).
    match_detail passes actual overlap data to the Groq ranker for grounded rationale.
    """
    semantic_active = bool(cosine_scores)
    results = []

    for event in events:
        cosine = cosine_scores.get(event.id, 0.0)
        rule, detail = _rule_score(event, profile)

        hybrid = (
            (settings.cosine_weight * cosine) + (settings.rule_weight * rule)
            if semantic_active else rule
        )
        hybrid = round(hybrid, 4)
        tier   = _tier(hybrid, semantic_active)
        results.append((event, hybrid, tier, detail))

    results.sort(key=lambda x: x[1], reverse=True)

    counts = {TIER_GO: 0, TIER_CONSIDER: 0, TIER_SKIP: 0}
    for _, _, t, _ in results:
        counts[t] = counts.get(t, 0) + 1

    logger.info(
        f"Scored {len(results)} events — "
        f"GO: {counts[TIER_GO]}, CONSIDER: {counts[TIER_CONSIDER]}, SKIP: {counts[TIER_SKIP]}"
    )
    return results
