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

    # ── Groq LLM (free tier) ─────────────────────
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_temperature: float = 0.1
    groq_max_tokens: int = 4096
    groq_timeout_seconds: int = 20

    # ── Embedding model (local, free) ────────────
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dim: int = 384
    enable_semantic_search: bool = True
    preload_index_on_startup: bool = False

    # ── Event APIs (free tiers) ──────────────────
    ticketmaster_key: str = ""          # developer.ticketmaster.com  → 5000/day
    eventbrite_token: str = ""          # eventbrite.com/platform/api → 2000/hr
    meetup_key: str = ""                # meetup.com/api              → OAuth
    allevents_key: str = ""             # allevents.in/developer      → free tier
    luma_api_key: str = ""              # lu.ma/developers            → free
    serpapi_key: str = ""               # serpapi.com                 → 100/month

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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
