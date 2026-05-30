"""
relevance/fit_scorer.py  —  Robust 5-factor weighted fit score

KEY DESIGN PRINCIPLE: Missing data = skip that factor + rescale.
Never assign a neutral/fake score when data is absent.
The score always reflects only what we actually measured.

──────────────────────────────────────────────────────────────────
AVAILABLE-FACTOR NORMALISATION
──────────────────────────────────────────────────────────────────
Factor                Max weight  When available
─────────────────────────────────────────────────────────────────
ICP density            40         Always (industry + persona from DB)
Deal-size fit          25         Only when est_attendees > 0
Geographic match       15         Only when city/country populated in DB
Competitive intensity  10         Only when sponsors field populated
─────────────────────────────────────────────────────────────────

NORMALISATION:
  raw_total   = sum of scores for AVAILABLE factors only
  available_w = sum of max weights for AVAILABLE factors only
  fit_score   = round(raw_total / available_w * 100)

  If only ICP density is available (e.g. brand-new event, no attendee data):
    raw = icp_score (0–40)
    available_w = 40
    fit_score = raw/40*100 = 0–100 — still a full 0–100 score
    BUT confidence_level = "low" (only 1 of 4 factors measured)

CONFIDENCE LEVEL (separate from fit_score):
  "high"   →  available_weight ≥ 70%  of total possible (≥ 56 of 80 available)
  "medium" →  available_weight 40–69%  (≥ 32 of 80)
  "low"    →  available_weight < 40%   (< 32 of 80)

  This is displayed to the user as:
  "Score based on 2 of 4 measurable factors. More event data → higher confidence."

ICP COUNT FORMULA:
  = est_attendees × DM_RATIO × density_ratio
  
  DM_RATIO: configurable, default 0.35 (~35% of B2B show attendees are
            decision-makers, not vendors or booth staff). This comes from
            industry research on B2B trade show composition.
            Stored in Settings.dm_ratio for easy tuning.
  
  density_ratio: rule_score / RULE_SCORE_MAX (0.60 max from scorer.py)
                 This is the fraction of DMs that match YOUR specific ICP.
  
  Returns None when est_attendees = 0. Never fakes a number.
  
  Confidence range: ±ICP_UNCERTAINTY_PCT (default 30%)
  Rounded to nearest ICP_ROUND_TO (default 10) for honest uncertainty display.

COMPETITIVE INTENSITY:
  Source: event.sponsors (comma-separated exhibitor/sponsor names from DB)
  Method: match against industry keyword expansions from ICP profile.
  Score: graduated 0–10 based on competitor count found.
  If sponsors field is empty → factor SKIPPED entirely (not scored as 0 or 5).
  
  High competition = positive signal (your buyers definitely attend there).

HISTORICAL CONVERSION:
  MVP: always skipped — we have no real outcome data yet.
  v2: will use actual client meeting outcomes from CRM per event.
  The factor slot is reserved in the schema, score = None in MVP.

DEAL-SIZE FIT:
  Scale mapping from Settings (configurable):
    strategic  → needs large flagship shows
    enterprise → needs significant shows
    high       → any mid-size+ B2B show
    medium     → any B2B show qualifies
  If est_attendees = 0 → deal-size factor SKIPPED.
"""
from __future__ import annotations

import re
from typing import Optional

from config import get_settings
from models.event import EventORM
from models.icp_profile import ICPProfile

settings = get_settings()

# ── Configurable parameters (not hardcoded — read from Settings) ──
# Add these to your config.py / .env for easy tuning:
#   DM_RATIO          = 0.35  (fraction of B2B attendees who are decision-makers)
#   ICP_UNCERTAINTY   = 0.30  (±30% confidence band around ICP estimate)
#   ICP_ROUND_TO      = 10    (round ICP estimate to nearest N)
#   DEAL_MIN_STRATEGIC = 5000 (min attendees to count as "flagship" for $500K+ deals)
#   DEAL_MIN_ENTERPRISE = 1000
#   DEAL_MIN_HIGH      = 500
DM_RATIO           = getattr(settings, "dm_ratio",          0.35)
ICP_UNCERTAINTY    = getattr(settings, "icp_uncertainty",   0.30)
ICP_ROUND_TO       = getattr(settings, "icp_round_to",      10)
DEAL_MIN_STRATEGIC = getattr(settings, "deal_min_strategic", 5000)
DEAL_MIN_ENTERPRISE= getattr(settings, "deal_min_enterprise",1000)
DEAL_MIN_HIGH      = getattr(settings, "deal_min_high",      500)
RULE_SCORE_MAX     = 0.60   # max possible rule_score from scorer.py (0.35 ind + 0.25 persona)

# ── Grade thresholds ──────────────────────────────────────────────
# Applied AFTER normalisation to 0–100.
GRADE_THRESHOLDS = [
    (80, "A+", "Exceptional fit"),
    (65, "A",  "Strong fit"),
    (50, "B+", "Good fit"),
    (35, "B",  "Reasonable fit"),
    (0,  "C",  "Marginal fit"),
]

# ── Industry → competitor keyword expansions ──────────────────────
# Used to count competitor exhibitors from event.sponsors.
# These are industry terms, not company names — we look for these
# as substrings inside sponsor names (e.g. "Stripe" contains "stripe"
# which matches under fintech keywords via "payment").
# Kept as domain knowledge, not hardcoded business logic.
_INDUSTRY_KEYWORDS: dict[str, list[str]] = {
    "fintech":            ["fintech","payment","banking","lending","insurtech","neobank","open banking"],
    "cloud computing":    ["cloud","aws","azure","gcp","saas","iaas","paas","kubernetes","docker"],
    "cybersecurity":      ["cyber","security","firewall","siem","soc","endpoint","zero trust","xdr"],
    "healthcare":         ["medtech","health","pharma","biotech","ehr","telemedicine","diagnostics"],
    "manufacturing":      ["automation","robotics","cnc","plc","scada","industrial","iiot"],
    "logistics":          ["logistics","freight","shipping","warehouse","supply chain","last mile"],
    "ai":                 ["ai","ml","machine learning","nlp","llm","data science","analytics"],
    "retail":             ["retail","ecommerce","pos","omnichannel","commerce","marketplace"],
    "energy":             ["solar","wind","renewable","grid","utility","cleantech","battery"],
    "marketing":          ["martech","crm","marketing automation","demand gen","adtech"],
    "hr tech":            ["hris","hrms","payroll","talent","workforce","ats","lms"],
    "real estate":        ["proptech","real estate","realestate","property management","bim"],
    "finance":            ["finance","investment","asset management","trading","risk","compliance"],
    "education":          ["edtech","lms","e-learning","learning management","training platform"],
}


def _geo_text(event: EventORM) -> str:
    city    = (event.city    or "").strip()
    country = (event.country or "").strip()
    # Normalise "UK - United Kingdom" → include both variants
    if " - " in country:
        parts   = country.split(" - ")
        country = " ".join(parts)
    return f"{city} {country}".lower().strip()


def _event_text(event: EventORM) -> str:
    return " ".join(filter(None, [
        event.name        or "",
        event.description or "",
        event.category    or "",
        event.industry_tags or "",
        event.audience_personas or "",
    ])).lower()


# ─────────────────────────────────────────────────────────────────
# Factor scorers — each returns (raw_score, max_weight, available: bool, notes: str)
# ─────────────────────────────────────────────────────────────────

def _factor_icp_density(
    event: EventORM, profile: ICPProfile, rule_score: float
) -> tuple:
    """
    ICP density — max weight 40.
    Always available: we always have industry_tags + persona data from DB + profile.
    
    raw = (rule_score / RULE_SCORE_MAX) × 40
    Capped so a perfect industry + persona match = full 40 points.
    """
    density = min(rule_score / RULE_SCORE_MAX, 1.0) if rule_score > 0 else 0.0
    raw     = round(density * 40.0, 2)
    notes   = f"ICP density {int(density*100)}% (industry + persona match)"
    return raw, 40, True, notes


def _factor_deal_size(
    event: EventORM, profile: ICPProfile
) -> tuple:
    """
    Deal-size fit — max weight 25.
    AVAILABLE only when est_attendees > 0.
    If attendees unknown → skip this factor entirely (not scored as partial).
    
    Logic: match deal size to show scale.
    Also bonus for executive-level language in event description.
    """
    att = int(event.est_attendees or 0)
    if att == 0:
        return 0, 25, False, "skipped: no attendee count in DB yet"

    deal_cat = (profile.avg_deal_size_category or "medium").lower()
    text     = _event_text(event)

    # Minimum show size for each deal tier (from configurable settings)
    min_att = {
        "strategic": DEAL_MIN_STRATEGIC,
        "enterprise":DEAL_MIN_ENTERPRISE,
        "high":      DEAL_MIN_HIGH,
        "medium":    0,
    }.get(deal_cat, 0)

    # Executive signals in the event itself
    exec_terms   = ["executive","cxo","ceo","coo","cio","cto","leadership",
                    "enterprise","global","world","flagship","tier 1"]
    exec_match   = any(t in text for t in exec_terms)
    exec_bonus   = 4.0 if exec_match else 0.0

    if att >= min_att * 2:      # well above minimum
        base = 21.0
    elif att >= min_att:        # meets minimum
        base = 17.0
    elif min_att == 0:          # medium deal — any show
        base = 18.0
    else:                       # below minimum for this deal tier
        base = 6.0

    raw   = round(min(base + exec_bonus, 25.0), 2)
    notes = (f"deal-size fit: {deal_cat} deal × {att:,} attendees "
             f"{'+ exec signal' if exec_match else ''}")
    return raw, 25, True, notes


def _factor_geo_match(
    event: EventORM, profile: ICPProfile
) -> tuple:
    """
    Geographic match — max weight 15.
    AVAILABLE only when event has city or country populated.
    If both are empty → skip this factor.
    
    Full 15 if location matches or profile is global.
    """
    city    = (event.city    or "").strip()
    country = (event.country or "").strip()

    if not city and not country:
        return 0, 15, False, "skipped: event location not yet in DB"

    if not profile.target_geographies:
        # No geo preference = global scope = always match
        return 15.0, 15, True, "geographic match: global scope"

    is_global = any(
        g.lower().strip() in ("global", "worldwide", "international", "any", "remote")
        for g in profile.target_geographies
    )
    if is_global:
        return 15.0, 15, True, "geographic match: global preference"

    geo_text = _geo_text(event)
    for geo in profile.target_geographies:
        words = [w for w in re.split(r"[\s,/\-]+", geo.lower()) if len(w) > 2]
        if any(w in geo_text for w in words):
            return 15.0, 15, True, f"geographic match: {geo}"

    # Check virtual/hybrid (no geo restriction)
    if getattr(event, "is_virtual", False) or getattr(event, "is_hybrid", False):
        return 8.0, 15, True, "geographic match: virtual/hybrid (partial)"

    return 0.0, 15, True, "geographic miss: outside target regions"


def _factor_competitive_intensity(
    event: EventORM, profile: ICPProfile
) -> tuple:
    """
    Competitive intensity — max weight 10.
    AVAILABLE only when event.sponsors is populated.
    If sponsors empty → skip this factor entirely.
    
    Counts competitor-like sponsors using ICP industry keywords.
    More competitors = positive (your buyers are definitely there).
    """
    sponsors_raw = (event.sponsors or "").strip()
    if not sponsors_raw:
        return 0, 10, False, "skipped: no exhibitor/sponsor data in DB"

    sponsor_list = [s.strip().lower() for s in sponsors_raw.split(",") if s.strip()]
    if not sponsor_list:
        return 0, 10, False, "skipped: sponsors field empty after parsing"

    # Build keyword set from ICP industries
    keywords: set[str] = set()
    for ind in (profile.target_industries or []):
        ind_l = ind.lower()
        for key, kws in _INDUSTRY_KEYWORDS.items():
            if key in ind_l or ind_l in key or any(kw in ind_l for kw in kws[:3]):
                keywords.update(kws)
    # Add persona signals
    for p in (profile.target_personas or []):
        pl = p.lower()
        if any(t in pl for t in ("cio","cto","it","tech","digital","software")):
            keywords.update(["tech","software","cloud","saas","platform","digital"])
        if any(t in pl for t in ("cfo","finance","banking","treasury")):
            keywords.update(["fintech","banking","finance","payment","risk"])

    count = sum(1 for s in sponsor_list if any(kw in s for kw in keywords))

    # Score graduated by competitor count — more = better signal
    if   count >= 12: raw = 10.0
    elif count >= 8:  raw = 8.0
    elif count >= 4:  raw = 6.0
    elif count >= 1:  raw = 4.0
    else:             raw = 1.5   # sponsors exist but none matched = weak signal

    notes = f"competitive intensity: {count} relevant exhibitors found in {len(sponsor_list)} sponsors"
    return raw, 10, True, notes



# ─────────────────────────────────────────────────────────────────
# Public: calculate_fit_score
# ─────────────────────────────────────────────────────────────────

def calculate_fit_score(
    event:      EventORM,
    profile:    ICPProfile,
    rule_score: float,    # 0..1 from scorer.py (industry + persona)
) -> dict:
    """
    Calculate the fit score using available-factor normalisation.
    
    Only scores factors where real data exists.
    Normalises to 0–100 based on available evidence.
    Returns confidence level (high/medium/low) reflecting data completeness.
    
    Returns:
      fit_score      int 0–100
      fit_grade      str A+/A/B+/B/C
      fit_label      str
      confidence     str high/medium/low
      factors_used   int  how many factors were scored
      factors_total  int  how many factors exist (excl. always-skipped historical)
      factor_scores  dict per-factor raw scores
      factor_notes   dict per-factor explanation strings
      data_gaps      list factors that were skipped and WHY
    """
    factors = [
        ("icp_density",          *_factor_icp_density(event, profile, rule_score)),
        ("deal_size_fit",        *_factor_deal_size(event, profile)),
        ("geo_match",            *_factor_geo_match(event, profile)),
        ("competitive_intensity",*_factor_competitive_intensity(event, profile)),
    ]

    raw_total   = 0.0
    avail_weight= 0.0
    factor_scores = {}
    factor_notes  = {}
    data_gaps     = []
    factors_used  = 0
    # historical is always skipped — don't count it in total measurable
    factors_total = len(factors)  # all 4 factors

    for name, raw, max_w, available, notes in factors:
        factor_notes[name] = notes
        if available:
            raw_total    += raw
            avail_weight += max_w
            factor_scores[name] = round(raw, 2)
            factors_used += 1
        else:
            factor_scores[name] = None   # explicitly null = not scored
            data_gaps.append({"factor": name, "reason": notes})

    # Normalise to 0–100 over available weight only
    if avail_weight > 0:
        fit_score = int(round(raw_total / avail_weight * 100))
    else:
        fit_score = 0

    fit_score = min(max(fit_score, 0), 100)

    # Grade from normalised score
    grade = "C"; label = "Marginal fit"
    for threshold, g, l in GRADE_THRESHOLDS:
        if fit_score >= threshold:
            grade = g; label = l; break

    # Confidence level based on available weight vs maximum possible
    # Maximum available weight = 40+25+15+10 = 90
    MAX_AVAILABLE_WEIGHT = 90
    coverage = avail_weight / MAX_AVAILABLE_WEIGHT
    if   coverage >= 0.70: confidence = "high"
    elif coverage >= 0.40: confidence = "medium"
    else:                  confidence = "low"

    return {
        "fit_score":     fit_score,
        "fit_grade":     grade,
        "fit_label":     label,
        "confidence":    confidence,
        "factors_used":  factors_used,
        "factors_total": factors_total,
        "factor_scores": factor_scores,
        "factor_notes":  factor_notes,
        "data_gaps":     data_gaps,
    }


# ─────────────────────────────────────────────────────────────────
# Public: estimate_icp_count
# ─────────────────────────────────────────────────────────────────

def estimate_icp_count(
    event:      EventORM,
    profile:    ICPProfile,
    rule_score: float,
) -> Optional[dict]:
    """
    Estimate your decision-makers attending this event.
    Returns None when est_attendees = 0 (never fakes a number).
    
    Formula:
      estimate = est_attendees × DM_RATIO × density_ratio
      DM_RATIO      from Settings.dm_ratio (default 0.35)
      density_ratio = min(rule_score / RULE_SCORE_MAX, 1.0)
    
    Confidence range: ±ICP_UNCERTAINTY (default 30%)
    Rounded to nearest ICP_ROUND_TO (default 10)
    """
    att = int(event.est_attendees or 0)
    if att == 0:
        return None

    density = min(rule_score / RULE_SCORE_MAX, 1.0) if rule_score > 0 else 0.10
    raw     = att * DM_RATIO * density
    est     = max(ICP_ROUND_TO, round(raw / ICP_ROUND_TO) * ICP_ROUND_TO)

    low  = max(ICP_ROUND_TO, round(est * (1 - ICP_UNCERTAINTY) / ICP_ROUND_TO) * ICP_ROUND_TO)
    high = round(est * (1 + ICP_UNCERTAINTY) / ICP_ROUND_TO) * ICP_ROUND_TO

    uncertainty_pct = int(ICP_UNCERTAINTY * 100)
    dm_pct          = int(DM_RATIO * 100)
    density_pct     = int(density * 100)

    return {
        "estimate":      est,
        "low":           low,
        "high":          high,
        "display":       f"~{est:,}",
        "range_display": f"{low:,} – {high:,}",
        "methodology": (
            f"Based on {att:,} total attendees at this event. "
            f"~{dm_pct}% of B2B show attendees are decision-makers (not vendors). "
            f"Of those, ~{density_pct}% match your specific ICP profile. "
            f"Range shows ±{uncertainty_pct}% confidence interval."
        ),
    }


def count_competitors(event: EventORM, profile: ICPProfile) -> int:
    """Returns the number of competitor-like sponsors found. 0 = no data or no matches."""
    raw, _, available, _ = _factor_competitive_intensity(event, profile)
    if not available:
        return 0
    sponsors = [s.strip().lower() for s in (event.sponsors or "").split(",") if s.strip()]
    keywords: set[str] = set()
    for ind in (profile.target_industries or []):
        ind_l = ind.lower()
        for key, kws in _INDUSTRY_KEYWORDS.items():
            if key in ind_l or ind_l in key or any(kw in ind_l for kw in kws[:3]):
                keywords.update(kws)
    return sum(1 for s in sponsors if any(kw in s for kw in keywords))


# ─────────────────────────────────────────────────────────────────
# Public: calculate_universe_stats
# ─────────────────────────────────────────────────────────────────

def calculate_universe_stats(
    all_scored_events: list[dict],
    total_indexed:     int = 0,   # pass db event count from caller — never hardcode
) -> dict:
    """
    Universe stats for the ranking page banner.
    
    total_indexed: pass from routes_events via count_events(db).
                   Never hardcoded — always the real DB count.
    
    Returns:
      total_icps_across_shows  — sum of icp_count.estimate (None-safe)
      shows_worth_considering  — total non-skip events returned
      strongly_recommended     — A+ or A grade
      total_indexed            — real DB count (from caller)
    """
    total_icps   = 0
    strong_count = 0

    for ev in all_scored_events:
        icp = ev.get("icp_count")
        if isinstance(icp, dict) and icp.get("estimate"):
            total_icps += icp["estimate"]
        grade = ev.get("fit_grade", "")
        if grade in ("A+", "A"):
            strong_count += 1

    return {
        "total_icps_across_shows": total_icps if total_icps > 0 else None,
        "shows_worth_considering": len(all_scored_events),
        "strongly_recommended":    strong_count,
        "total_indexed":           total_indexed,   # real DB count from caller
    }
