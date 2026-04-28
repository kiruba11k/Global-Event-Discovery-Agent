"""
Hybrid Relevance Scorer
========================
Combines:
  1. Semantic cosine similarity (embedding-based)
  2. Rule-based signal boosts
  3. Hard filters (geography, date, budget)

Returns a final_score ∈ [0, 1] per event.
"""
from typing import List, Dict, Tuple
from models.event import EventORM
from models.icp_profile import ICPProfile
from config import get_settings

settings = get_settings()


def _overlap_score(a_tags: str, b_tags: List[str]) -> float:
    """Fraction of b_tags found in a_tags string."""
    if not a_tags or not b_tags:
        return 0.0
    a_lower = a_tags.lower()
    hits = sum(1 for t in b_tags if t.lower() in a_lower)
    return hits / len(b_tags)


def _attendee_boost(attendees: int) -> float:
    if attendees >= 10000:
        return 0.12
    if attendees >= 3000:
        return 0.09
    if attendees >= 1000:
        return 0.06
    if attendees >= 300:
        return 0.03
    return 0.0


def _budget_penalty(event_price: float, budget: float | None) -> float:
    """Negative signal if event cost exceeds user budget."""
    if budget is None or event_price == 0:
        return 0.0
    if event_price > budget * 1.5:
        return -0.15
    if event_price > budget:
        return -0.08
    return 0.0


def _event_type_boost(event_category: str, preferred_types: List[str]) -> float:
    if not preferred_types or not event_category:
        return 0.0
    cat_lower = event_category.lower()
    if any(pt.lower() in cat_lower or cat_lower in pt.lower() for pt in preferred_types):
        return 0.06
    return 0.0


def compute_rule_score(event: EventORM, profile: ICPProfile) -> float:
    """
    Rule-based signal score ∈ [-0.15, 0.40].
    Independent of embeddings — uses explicit field matching.
    """
    score = 0.0

    # Industry overlap
    score += _overlap_score(event.industry_tags, profile.target_industries) * 0.20

    # Persona overlap
    score += _overlap_score(event.audience_personas, profile.target_personas) * 0.20

    # Attendee size boost
    score += _attendee_boost(event.est_attendees)

    # Event type match
    score += _event_type_boost(event.category, profile.preferred_event_types)

    # Budget
    score += _budget_penalty(event.ticket_price_usd, profile.budget_usd)

    return max(-0.15, min(0.40, score))


def compute_final_score(cosine_score: float, rule_score: float) -> float:
    """Blend cosine + rule scores."""
    raw = (settings.cosine_weight * cosine_score) + (settings.rule_weight * rule_score)
    return round(min(1.0, max(0.0, raw)), 4)


def assign_tier(score: float) -> str:
    if score >= settings.go_threshold:
        return "GO"
    if score >= settings.consider_threshold:
        return "CONSIDER"
    return "SKIP"


def score_candidates(
    events: List[EventORM],
    profile: ICPProfile,
    cosine_scores: Dict[str, float],
) -> List[Tuple[EventORM, float, str]]:
    """
    Score and rank all candidate events.
    Returns list of (event, final_score, tier) sorted desc.
    """
    results = []
    for event in events:
        cscore = cosine_scores.get(event.id, 0.0)
        rscore = compute_rule_score(event, profile)
        fscore = compute_final_score(cscore, rscore)
        tier = assign_tier(fscore)
        results.append((event, fscore, tier))

    results.sort(key=lambda x: x[1], reverse=True)
    return results
