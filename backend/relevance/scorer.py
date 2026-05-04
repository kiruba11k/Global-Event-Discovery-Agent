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
    Plain-language business rationale — no code field names, no developer speak.
    Reads like a sales analyst wrote it.
    """
    event_name    = event.name or "This event"
    event_loc     = f"{event.city}, {event.country}".strip(", ") or "an unspecified location"
    ind_matched   = detail.get("industry_matched", [])
    per_matched   = detail.get("persona_matched", [])
    geo_matched   = detail.get("geo_matched", "")
    type_matched  = detail.get("type_matched", False)
    att_tier      = detail.get("attendee_tier", "")
    score_pct     = int(score * 100)

    # Build industry sentence
    if ind_matched:
        ind_sentence = (
            f"{event_name} focuses on {_join_natural(ind_matched[:3])}, "
            f"which directly aligns with your target market."
        )
    else:
        target_inds = _join_natural((profile.target_industries or [])[:3])
        ind_sentence = (
            f"{event_name} covers topics outside your core focus of {target_inds}."
        )

    # Build audience/persona sentence
    event_personas = _clean_tags(event.audience_personas or "")
    target_personas = _join_natural((profile.target_personas or [])[:3])
    if per_matched:
        per_sentence = (
            f"The event draws {_join_natural(per_matched[:3])} — "
            f"exactly the decision-makers you want in front of."
        )
    elif event_personas:
        per_sentence = (
            f"The typical attendees are {event_personas[:80]}, "
            f"which doesn't strongly match the {target_personas} you're targeting."
        )
    else:
        per_sentence = (
            f"Attendee profile is unclear — hard to confirm alignment "
            f"with your target buyers ({target_personas})."
        )

    # Build geo sentence
    if geo_matched and geo_matched != "Global":
        geo_sentence = f"It's held in {event_loc}, which is within your target regions."
    elif geo_matched == "Global":
        geo_sentence = f"Held in {event_loc} — your global focus means geography isn't a barrier."
    elif event.is_virtual or event.is_hybrid:
        geo_sentence = f"This is a virtual/hybrid event, so your team can participate remotely regardless of location."
    else:
        target_geos = _join_natural((profile.target_geographies or [])[:3])
        geo_sentence = (
            f"It's based in {event_loc}, which falls outside your primary target regions ({target_geos})."
        )

    # Format + size note
    format_note = ""
    if type_matched and att_tier:
        format_note = f"Format ({event.category}) matches your preference, with {att_tier}."
    elif att_tier:
        format_note = f"Scale: {att_tier}."
    elif type_matched:
        format_note = f"The {event.category} format matches your preferred event type."

    if tier == TIER_GO:
        verdict_line = (
            f"Strong fit — this event is worth attending for pipeline generation ({score_pct}% match)."
        )
        parts = [ind_sentence, per_sentence]
        if format_note: parts.append(format_note)
        parts.append(verdict_line)

    elif tier == TIER_CONSIDER:
        verdict_line = (
            f"Partial fit ({score_pct}% match) — worth evaluating before committing budget."
        )
        parts = [ind_sentence, per_sentence]
        if geo_sentence and not geo_matched: parts.append(geo_sentence)
        parts.append(verdict_line)

    else:  # SKIP
        verdict_line = (
            f"Weak fit ({score_pct}% match) — the audience and industry focus don't align "
            f"well enough to justify the investment for your current sales motion."
        )
        parts = []
        if not ind_matched:   parts.append(ind_sentence)
        if not per_matched:   parts.append(per_sentence)
        if not geo_matched:   parts.append(geo_sentence)
        if not parts:         parts.append(ind_sentence)
        parts.append(verdict_line)

    return " ".join(parts)


def _join_natural(items: list) -> str:
    """['A', 'B', 'C'] → 'A, B and C'"""
    items = [str(i) for i in items if i]
    if not items:       return "your target areas"
    if len(items) == 1: return items[0]
    if len(items) == 2: return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])} and {items[-1]}"


def _clean_tags(tag_str: str) -> str:
    """'CTO,CIO,VP Engineering' → 'CTOs, CIOs, VP Engineering'"""
    tags = [t.strip() for t in tag_str.split(",") if t.strip()]
    return ", ".join(tags[:4])



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
