from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────
    app_name: str = "Event Intelligence Agent"
    app_version: str = "1.0.0"
    debug: bool = False
    frontend_origin: str = "http://localhost:5173"

    # ── Database ─────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./events.db"

    # ── Groq LLM ─────────────────────────────────
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_temperature: float = 0.1
    groq_max_tokens: int = 4096
    groq_timeout_seconds: int = 25

    # ── Embedding model ───────────────────────────
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dim: int = 384
    enable_semantic_search: bool = False
    preload_index_on_startup: bool = False

    # ── Real-time Event APIs ──────────────────────
    # All free tiers — see signup URLs in .env.example

    # SerpAPI — PRIMARY real-time source
    # engine=google_events gives live Google Events data
    # Free: 100 searches/month  |  https://serpapi.com
    serpapi_key: str = ""

    # Ticketmaster Discovery API
    # Free: 5,000 calls/day     |  https://developer.ticketmaster.com
    ticketmaster_key: str = ""

    # Eventbrite API
    # Free with account         |  https://www.eventbrite.com/platform/api
    eventbrite_token: str = ""

    # PredictHQ Event Intelligence
    # Free: 1,000 events/month  |  https://www.predicthq.com/signup
    predicthq_key: str = ""

    # Luma (lu.ma) API
    # Free with account         |  https://lu.ma/developers
    luma_api_key: str = ""

    # AllEvents.in API (optional)
    allevents_key: str = ""

    # ── Scraper tuning ────────────────────────────
    scrape_delay_seconds: float = 2.0
    scrape_timeout_seconds: int = 15

    # ── Relevance tuning ─────────────────────────
    cosine_weight: float = 0.65
    rule_weight: float = 0.35
    go_threshold: float = 0.68
    consider_threshold: float = 0.42
    top_k_for_llm: int = 20

    # ── Scheduler ────────────────────────────────
    refresh_interval_hours: int = 24

    # ── Email / Resend ────────────────────────────
    resend_api_key: str = ""
    resend_from_email: str = "kirubakaran.p@leadstrategus.com"

    # ── Seed protection ───────────────────────────
    seed_admin_token: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
