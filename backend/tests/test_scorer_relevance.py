"""
Regression tests for relevance/scorer.py industry matching.

Guards against the production bug where substring matching let unrelated
industries cross-match:
  - "auto" fired inside "automation", "ev" inside "event"
  - taxonomy key "tech" activated for "medtech" profiles
  - result: a manufacturing summit outranked a health summit for a
    healthcare-CISO ICP.

Runs without backend dependencies installed (config/models are stubbed).
"""
import sys
import types

# ── Stub heavy imports so scorer.py loads standalone ───────────────
sys.modules.setdefault("loguru", types.SimpleNamespace(
    logger=types.SimpleNamespace(
        info=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        debug=lambda *a, **k: None,
    )
))


class _Settings:
    go_threshold = 0.5
    consider_threshold = 0.3
    cosine_weight = 0.5
    rule_weight = 0.5


sys.modules.setdefault("config", types.SimpleNamespace(get_settings=lambda: _Settings()))
sys.modules.setdefault("models.event", types.SimpleNamespace(EventORM=object))
sys.modules.setdefault("models.icp_profile", types.SimpleNamespace(ICPProfile=object))

from relevance import scorer  # noqa: E402


class Ev:
    def __init__(self, name, tags, desc, city="Pune", country="India"):
        self.name = name
        self.industry_tags = tags
        self.description = desc
        self.city = city
        self.country = country
        self.related_industries = None
        self.event_cities = ""
        self.event_venues = ""
        self.short_summary = ""
        self.audience_personas = ""
        self.category = "trade show"
        self.venue_name = ""
        self.organizer = ""
        self.is_virtual = False
        self.is_hybrid = False
        self.est_attendees = 0
        self.id = name


def _profile(industries, personas=None, desc=""):
    class P:
        target_industries = industries
        target_personas = personas or []
        target_geographies = ["India"]
        preferred_event_types = ["conference", "trade show", "summit", "expo"]
        company_description = desc or " ".join(industries)
        buyer_description = desc or ""
        min_attendees = 0
    return P()


MFG = Ev(
    "India Manufacturing Summit 2026",
    "manufacturing, India, automation",
    "The India Manufacturing Summit covers manufacturing technology, automation and Industry 4.0.",
)
HEALTH = Ev(
    "India Health Summit 2026",
    "healthcare, medtech, digital health",
    "Healthcare technology and innovation event attracting Hospital CIOs and other senior IT leaders.",
    city="Bangalore",
)


def test_healthcare_icp_ranks_health_event_above_manufacturing():
    prof = _profile(["Healthcare / Medtech"], ["CISO"],
                    "CISO at healthcare organisations")
    mfg_score, mfg_detail = scorer._rule_score(MFG, prof)
    h_score, h_detail = scorer._rule_score(HEALTH, prof)
    assert h_detail["industry_matched"] == ["Healthcare / Medtech"]
    assert mfg_detail["industry_matched"] == []
    assert h_score > mfg_score


def test_medtech_profile_does_not_activate_tech_taxonomy_key():
    # "tech" inside "medtech" must NOT pull in technology synonyms
    prof = _profile(["Healthcare / Medtech"])
    _, detail = scorer._rule_score(MFG, prof)
    assert detail["industry_matched"] == []


def test_automotive_profile_does_not_match_automation_events():
    # "auto" must not fire inside "automation"
    prof = _profile(["Automotive"])
    _, detail = scorer._rule_score(MFG, prof)
    assert detail["industry_matched"] == []


def test_true_positives_still_match():
    cases = [
        (["Fintech"], Ev("Fintech Festival", "fintech, payments, banking",
                         "Digital banking and payments expo.", "Mumbai")),
        (["Manufacturing"], Ev("Metal Working Expo",
                               "Metal Working Industries, Mechanical Components",
                               "Machine tools trade fair.")),
        (["Cybersecurity"], Ev("InfoSec World", "cybersecurity, information security",
                               "Security conference.", "Delhi")),
        (["Technology"], Ev("Tech Summit", "technology, software",
                            "Enterprise technology conference.", "Bangalore")),
        (["Automotive"], Ev("Auto Expo", "automotive, vehicles",
                            "Vehicle and mobility show.", "Delhi")),
    ]
    for industries, ev in cases:
        _, detail = scorer._rule_score(ev, _profile(industries))
        assert detail["industry_matched"] == industries, \
            f"{industries} should match {ev.name}"


def test_primary_industry_match_outscores_secondary_only():
    prof = _profile(["Healthcare / Medtech", "Technology"])
    tech_event = Ev("Tech Summit", "technology, software",
                    "Enterprise technology conference.", "Bangalore")
    p_score, p_matched = scorer._score_industry(HEALTH, prof)
    s_score, s_matched = scorer._score_industry(tech_event, prof)
    assert "Healthcare / Medtech" in p_matched
    assert s_matched == ["Technology"]
    assert p_score > s_score
