"""
relevance/scorer.py — fixed industry matching.

Key fixes:
  1. _reverse_match now splits event tags only by comma/semicolon/pipe (not
     whitespace), preventing "Domestic Appliance Technology" from matching
     the "Technology" IT industry.
  2. _reverse_match returns the original profile value strings (not lowercase
     event tag tokens), eliminating "Technology" + "technology" duplicates.
  3. Single-word profile industries (e.g. "Technology") only match if the
     event segment has ≤ 3 tokens — avoids compound-noun false positives.
"""
import re
from typing import List, Dict, Tuple
from models.event import EventORM
from models.icp_profile import ICPProfile
from config import get_settings
from loguru import logger

settings = get_settings()

TIER_GO       = "GO"
TIER_CONSIDER = "CONSIDER"
TIER_SKIP     = "SKIP"

RULE_ONLY_GO_THRESHOLD       = 0.45
RULE_ONLY_CONSIDER_THRESHOLD = 0.22


# ── Token helpers ──────────────────────────────────────────

def _tokenise(text: str) -> List[str]:
    if not text:
        return []
    parts = re.split(r"[/,|]", text)
    tokens = []
    for part in parts:
        cleaned = part.strip().lower()
        if cleaned and len(cleaned) > 1:
            tokens.append(cleaned)
            words = [w for w in cleaned.split() if len(w) > 2]
            tokens.extend(words)
    seen, out = set(), []
    for t in tokens:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _build_event_text(event: EventORM) -> str:
    industry_text = (
        getattr(event, "related_industries", "") or
        event.industry_tags or
        event.category or ""
    )
    location_text = " ".join(filter(None, [
        getattr(event, "event_cities",  "") or event.city or "",
        getattr(event, "event_venues",  "") or event.venue_name or "",
        event.country or "",
    ]))
    parts = [
        event.name          or "",
        industry_text,
        event.audience_personas or "",
        event.category      or "",
        event.description   or "",
        event.short_summary or "",
        location_text,
        getattr(event, "organizer", "") or "",
    ]
    return " ".join(p for p in parts if p).lower()


def _token_match(profile_values: List[str], search_text: str) -> Tuple[int, List[str]]:
    matched = []
    for val in profile_values:
        tokens = _tokenise(val)
        if any(tok in search_text for tok in tokens):
            matched.append(val)
    return len(matched), matched


def _reverse_match(event_tag_str: str, profile_values: List[str]) -> List[str]:
    """
    Return profile values whose keywords appear as the PRIMARY content of a
    discrete event-tag segment.

    Splits only by comma / semicolon / pipe (not whitespace) so that compound
    phrases like "Domestic Appliance Technology" are treated as ONE segment and
    do NOT falsely trigger a match for the single-word profile industry
    "Technology".

    Single-token profile industries only match a segment that has ≤ 3 tokens
    (to block "Appliance Technology" -> "Technology" but allow "Technology"
    or "IT Technology").

    Always returns the original profile value string (not a lowercased tag
    token), eliminating "Technology" + "technology" duplicates.
    """
    if not event_tag_str:
        return []

    # Split into comma/semicolon/pipe-separated segments only
    event_segments = [
        s.strip().lower()
        for s in re.split(r"[,;|]", event_tag_str)
        if s.strip()
    ]

    matched: List[str] = []
    for pv in profile_values:
        pv_lower = pv.lower().strip()
        pv_tokens = [t for t in re.split(r"[^a-z0-9]+", pv_lower) if len(t) > 2]
        if not pv_tokens:
            continue
        for segment in event_segments:
            seg_tokens = [t for t in re.split(r"[^a-z0-9]+", segment) if len(t) > 2]
            if not seg_tokens:
                continue
            # Every profile token must appear in this segment
            if not all(pt in seg_tokens for pt in pv_tokens):
                continue
            # Single-token profile industry (e.g. "Technology"): the matching
            # segment must itself be short (≤ 3 words) so we don't fire on
            # "Domestic Appliance Technology" (4 words including "and").
            if len(pv_tokens) == 1 and len(seg_tokens) > 3:
                continue
            matched.append(pv)   # ← original profile value, not lowercase tag
            break

    return list(dict.fromkeys(matched))   # preserve order, deduplicate


# ── Core rule scorer ───────────────────────────────────────

def _rule_score(event: EventORM, profile: ICPProfile) -> Tuple[float, dict]:
    score = 0.0
    detail: dict = {
        "industry_matched": [],
        "industry_missed":  False,
        "persona_matched":  [],
        "persona_missed":   False,
        "geo_matched":      "",
        "geo_missed":       False,
        "type_matched":     False,
        "attendee_tier":    "",
    }

    event_text = _build_event_text(event)

    industry_tags = (
        getattr(event, "related_industries", "") or
        event.industry_tags or ""
    ).lower()

    persona_tags = (event.audience_personas or "").lower()

    # ── Industry — 0.32 ───────────────────────────────────
    _, ind_fwd = _token_match(profile.target_industries, event_text)
    ind_rev    = _reverse_match(industry_tags, profile.target_industries)
    # Merge without duplicates (both lists now contain profile value strings)
    all_ind    = list(dict.fromkeys(ind_fwd + [v for v in ind_rev if v not in ind_fwd]))

    if   len(all_ind) >= 3: score += 0.32
    elif len(all_ind) == 2: score += 0.26
    elif len(all_ind) == 1: score += 0.18
    else:                   detail["industry_missed"] = True

    detail["industry_matched"] = all_ind[:4]

    # ── Persona — 0.28 ────────────────────────────────────
    _, per_fwd = _token_match(profile.target_personas, persona_tags)
    per_rev    = _reverse_match(persona_tags, profile.target_personas)
    all_per    = list(dict.fromkeys(per_fwd + [v for v in per_rev if v not in per_fwd]))

    if   len(all_per) >= 2: score += 0.28
    elif len(all_per) == 1: score += 0.18
    else:                   detail["persona_missed"] = True

    detail["persona_matched"] = all_per[:4]

    # ── Geography — 0.22 ──────────────────────────────────
    city_text    = getattr(event, "event_cities", "") or event.city or ""
    geo_text     = f"{city_text} {event.country or ''}".lower()
    is_global    = any(
        g.lower() in ("global", "worldwide", "international", "any")
        for g in (profile.target_geographies or [])
    )

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

    # ── Event type — 0.10 ────────────────────────────────
    type_text = f"{event.category or ''} {event.name or ''}".lower()
    type_hits = [
        t for t in (profile.preferred_event_types or [])
        if any(tok in type_text for tok in _tokenise(t))
    ]
    if type_hits:
        score += 0.10
        detail["type_matched"] = True

    # ── Attendees — 0.08 ─────────────────────────────────
    att = event.est_attendees or 0
    if   att >= 10000: score += 0.08; detail["attendee_tier"] = f"{att:,}+ (flagship)"
    elif att >= 5000:  score += 0.07; detail["attendee_tier"] = f"{att:,}+ (large)"
    elif att >= 1000:  score += 0.05; detail["attendee_tier"] = f"{att:,} (mid-size)"
    elif att >= max(profile.min_attendees or 0, 200):
                       score += 0.03; detail["attendee_tier"] = f"{att:,}"
    elif att > 0:      score += 0.01; detail["attendee_tier"] = f"{att} (boutique)"

    return round(min(score, 1.0), 4), detail


def _tier(score: float, semantic_active: bool) -> str:
    if semantic_active:
        go_t, con_t = settings.go_threshold, settings.consider_threshold
    else:
        go_t, con_t = RULE_ONLY_GO_THRESHOLD, RULE_ONLY_CONSIDER_THRESHOLD
    if score >= go_t:  return TIER_GO
    if score >= con_t: return TIER_CONSIDER
    return TIER_SKIP


def build_fallback_rationale(
    event: EventORM, profile: ICPProfile,
    detail: dict, score: float, tier: str,
) -> str:
    event_name   = event.name or "This event"
    city_raw     = getattr(event, "event_cities", "") or event.city or ""
    event_loc    = f"{city_raw}, {event.country}".strip(", ") or "an unspecified location"
    ind_matched  = detail.get("industry_matched", [])
    per_matched  = detail.get("persona_matched", [])
    geo_matched  = detail.get("geo_matched", "")
    att_tier     = detail.get("attendee_tier", "")
    score_pct    = int(score * 100)

    # Use the event's actual industries (what it IS about), not the profile industries
    event_industries = _clean_tags(
        getattr(event, "related_industries", "") or event.industry_tags or event.category or ""
    )

    # --- Industry sentence ---
    if ind_matched:
        ind_sentence = (
            f"{event_name} covers {_join_natural(ind_matched[:3])}, aligning with your target market."
        )
    elif event_industries:
        ind_sentence = (
            f"{event_name} is focused on {event_industries}, "
            f"which doesn't directly align with your target industries "
            f"({_join_natural((profile.target_industries or [])[:3])})."
        )
    else:
        ind_sentence = (
            f"{event_name} does not provide enough industry evidence to confirm alignment with "
            f"{_join_natural((profile.target_industries or [])[:3])}."
        )

    # --- Persona sentence ---
    event_personas   = _clean_tags(event.audience_personas or "")
    target_personas  = _join_natural((profile.target_personas or [])[:3])
    if per_matched:
        per_sentence = (
            f"The event draws {_join_natural(per_matched[:3])} — your target decision-makers."
        )
    elif event_personas:
        per_sentence = (
            f"The typical attendees are {event_personas[:80]}, "
            f"which doesn't strongly match your target {target_personas}."
        )
    else:
        per_sentence = (
            f"Attendee profile is unclear for your target buyers ({target_personas})."
        )

    # --- Geo sentence ---
    if geo_matched and geo_matched != "Global":
        geo_sentence = f"Held in {event_loc} — within your target regions."
    elif geo_matched == "Global":
        geo_sentence = f"Held in {event_loc}. Your global scope means geography isn't a barrier."
    elif event.is_virtual or event.is_hybrid:
        geo_sentence = "This is a virtual/hybrid event — your team can join remotely."
    else:
        target_geos  = _join_natural((profile.target_geographies or [])[:3])
        geo_sentence = (
            f"Based in {event_loc}, which is outside your primary regions ({target_geos})."
        )

    format_note = ""
    if detail.get("type_matched") and att_tier:
        format_note = f"Format ({event.category}) matches your preference; {att_tier}."
    elif att_tier:
        format_note = f"Scale: {att_tier}."

    if tier == TIER_GO:
        parts = [ind_sentence, per_sentence]
        if format_note: parts.append(format_note)
        parts.append(f"Strong pipeline fit — worth attending ({score_pct}% match).")
    elif tier == TIER_CONSIDER:
        parts = [ind_sentence, per_sentence]
        if not geo_matched: parts.append(geo_sentence)
        parts.append(f"Partial fit ({score_pct}%) — evaluate before committing budget.")
    else:
        parts = []
        if not ind_matched: parts.append(ind_sentence)
        if not per_matched: parts.append(per_sentence)
        if not geo_matched: parts.append(geo_sentence)
        if not parts:       parts.append(ind_sentence)
        parts.append(
            f"Weak fit ({score_pct}%) — audience and industry don't align well "
            f"enough for this sales motion."
        )

    return " ".join(parts)


def _join_natural(items: list) -> str:
    items = [str(i) for i in items if i]
    if not items:       return "your target areas"
    if len(items) == 1: return items[0]
    if len(items) == 2: return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])} and {items[-1]}"


def _clean_tags(tag_str: str) -> str:
    tags = [t.strip() for t in tag_str.split(",") if t.strip()]
    return ", ".join(tags[:4])


def score_candidates(
    events: List[EventORM],
    profile: ICPProfile,
    cosine_scores: Dict[str, float],
) -> List[Tuple[EventORM, float, str, dict]]:
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
        f"GO={counts[TIER_GO]} CONSIDER={counts[TIER_CONSIDER]} SKIP={counts[TIER_SKIP]}"
    )
    return results
