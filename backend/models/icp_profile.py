from pydantic import BaseModel
from typing import List, Optional
from typing_extensions import TypedDict


class ICPSegment(TypedDict):
    personas:   List[str]
    industries: List[str]


class ICPProfile(BaseModel):
    company_name:           str
    target_industries:      List[str]       # ["fintech", "healthcare", "logistics"]
    target_personas:        List[str]       # ["CIO", "CTO", "Head of Data"]
    target_geographies:     List[str]       # ["Singapore", "India", "US", "Global"]
    preferred_event_types:  List[str]       # ["conference", "trade show", "summit"]

    # ── Paired persona/industry groups ─────────────────────────
    # When the buyer description names distinct role+vertical pairs
    # ("CEO at BFSI, CIO at Medtech companies"), target_industries and
    # target_personas above stay the UNION of everything mentioned (used
    # for coarse filtering / display / back-compat with older clients),
    # but icp_segments carries the actual pairing so the scorer can
    # require persona AND industry from the SAME group, instead of
    # scoring "any persona" against "any industry" and letting an event
    # that only matches CEO + Medtech (a pairing nobody asked for) count
    # as a full match. Empty means "no explicit pairing" - falls back to
    # the flat cross-product behaviour via target_industries/target_personas.
    icp_segments:            List[ICPSegment] = []
    budget_usd:             Optional[float] = None
    date_from:              Optional[str]   = None   # YYYY-MM-DD
    date_to:                Optional[str]   = None   # YYYY-MM-DD
    min_attendees:          Optional[int]   = 0
    max_results:            int             = 30

    # ── Deal size — used to drive pricing matrix ──────────────
    # Sent from ICPForm step 5. Previously stripped by the model.
    avg_deal_size_category: str = "medium"  # "low"|"medium"|"high"|"enterprise"

    # ── Company email — forwarded from CompanyForm step 0 ────
    email: str = ""

    # ── Client names — optional social-proof list ─────────────
    client_names: List[str] = []   # company names the user has served

    # ── Free-text buyer description (verbatim form input) ─────
    # Used by the scorer's context pass; previously sent by the
    # frontend but silently dropped by pydantic (undeclared field).
    buyer_description: str = ""

    # ── LLM-parsed niche keywords outside the canonical taxonomy ─
    # e.g. ["ambulatory surgery", "clinical operations"] — scored as
    # free-text evidence so long-tail ICPs still match events.
    extra_keywords: List[str] = []

    # ── Meeting-potential calculator inputs (from ICP form) ────
    # Also previously dropped by pydantic; getattr() fell back to
    # defaults, so the user's answers never affected the output.
    differentiator_score: int = 5          # 1-10 slider
    client_count_range:   str = "11-50"    # "0-10"|"11-50"|"51-200"|"201-500"|"500+"


class CompanyContext(BaseModel):
    """Optional enriched context from saved company profile + deck."""
    company_name:  str = ""
    founded_year:  str = ""
    location:      str = ""
    what_we_do:    str = ""
    what_we_need:  str = ""
    deck_text:     str = ""   # extracted from PDF upload


class SearchRequest(BaseModel):
    profile:            ICPProfile
    company_context:    Optional[CompanyContext] = None

    # ── Bot protection / consent (api/bot_protection.py) ──────
    captcha_token:      str  = ""    # Cloudflare Turnstile response token
    honeypot:           str  = ""    # hidden field — non-empty means a bot filled it
    consent:            bool = False # form-consent checkbox (required)


class SearchResponse(BaseModel):
    profile_id:  str
    company_name: str
    total_found: int
    events:      list
    generated_at: str
