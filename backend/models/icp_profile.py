from pydantic import BaseModel
from typing import List, Optional


class ICPProfile(BaseModel):
    company_name: str
    company_description: str
    target_industries: List[str]        # ["fintech", "healthcare", "logistics"]
    target_personas: List[str]          # ["CIO", "CTO", "Head of Data"]
    target_geographies: List[str]       # ["Singapore", "India", "US", "Global"]
    preferred_event_types: List[str]    # ["conference", "trade show", "summit", "expo"]
    budget_usd: Optional[float] = None  # max ticket/exhibit budget
    date_from: Optional[str] = None     # YYYY-MM-DD
    date_to: Optional[str] = None       # YYYY-MM-DD
    min_attendees: Optional[int] = 200
    max_results: int = 30


class CompanyContext(BaseModel):
    """Optional enriched context from saved company profile + deck."""
    company_name: str = ""
    founded_year: str = ""
    location: str = ""
    what_we_do: str = ""
    what_we_need: str = ""
    deck_text: str = ""          # extracted from PDF upload


class SearchRequest(BaseModel):
    profile: ICPProfile
    company_profile_id: Optional[str] = None  # links to saved CompanyProfile
    company_context: Optional[CompanyContext] = None  # inline context (fallback)


class SearchResponse(BaseModel):
    profile_id: str
    company_name: str
    total_found: int
    events: list
    generated_at: str
