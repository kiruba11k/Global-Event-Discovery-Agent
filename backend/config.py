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

    # ── Event APIs ───────────────────────────────
    ticketmaster_key: str = ""
    eventbrite_token: str = ""
    meetup_key: str = ""
    allevents_key: str = ""
    luma_api_key: str = ""
    serpapi_key: str = ""

    # ── Scraping ─────────────────────────────────
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
    # Get your free API key at: https://resend.com
    # Free tier: 3,000 emails/month, 100/day — more than enough
    resend_api_key: str = ""
    # Must be a verified domain in your Resend account.
    # On free tier you can send from: onboarding@resend.dev (for testing)
    # For production: reports@yourdomain.com
    resend_from_email: str = "kirubakaran.p@leadstrategus.com"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
