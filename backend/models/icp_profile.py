from pydantic import BaseModel
from typing import List, Optional


class ICPProfile(BaseModel):
    company_name:           str
    company_description:    str
    target_industries:      List[str]       # ["fintech", "healthcare", "logistics"]
    target_personas:        List[str]       # ["CIO", "CTO", "Head of Data"]
    target_geographies:     List[str]       # ["Singapore", "India", "US", "Global"]
    preferred_event_types:  List[str]       # ["conference", "trade show", "summit"]
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
    company_profile_id: Optional[str]          = None
    company_context:    Optional[CompanyContext]= None


class SearchResponse(BaseModel):
    profile_id:  str
    company_name: str
    total_found: int
    events:      list
    generated_at: str
