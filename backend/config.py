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

    # ── Shared cache / rate-limit state (Redis) ───
    # Optional. When empty, relevance/llm_client.py falls back to
    # in-process memory automatically — fine for a single worker, but
    # once you run multiple Uvicorn workers or instances (needed for
    # 1k-concurrent-style load) the LLM response cache, the daily $
    # budget counter, and the TPM throttle window all need to be SHARED
    # across processes, or each worker enforces its own independent
    # budget and the real spend cap becomes (budget × worker count).
    # Set this (e.g. redis://localhost:6379/0, or a managed Redis URL)
    # before scaling past one worker.
    redis_url: str = ""
    # Number of background workers consuming POST /api/search jobs from the
    # Redis queue (see queueing/search_queue.py). Only relevant when
    # redis_url is set — with no Redis, search runs inline per-request
    # regardless of this value. Bound by openai_tpm_limit/db pool size
    # more than raw worker count — more workers just means more jobs
    # racing those same shared ceilings concurrently.
    #
    # Kept low (1) on purpose: each worker polls the queue every
    # search_queue_poll_seconds REGARDLESS of whether there's a job
    # waiting — that's N workers × 1 Redis command every poll interval,
    # 24/7, forever. On a metered free tier (Upstash: 500k commands/mo)
    # this adds up fast at idle — 3 workers @ 5s used to burn ~1.5M/mo
    # on its own. This app's real traffic ceiling is tiny (one search
    # per IP per day, see api/rate_limit.py), so raise this only if
    # you've actually confirmed jobs are queuing up faster than 1
    # worker clears them.
    search_queue_workers: int = 1
    # Seconds between each worker's queue poll when idle. See the comment
    # above — this is the primary lever for Redis command budget, not
    # worker count. 3 workers × poll every N seconds = ~3 × (86400×30/N)
    # commands/month from idle polling alone.
    search_queue_poll_seconds: int = 10

    # ── OpenAI LLM ─────────────────────────────────
    # Paid API — token cost is real money, so every knob here exists to
    # cap spend, not just to configure behaviour. See llm_client.py for
    # how tpm_limit / max_tokens / daily_usd_budget are enforced.
    openai_api_key: str = ""
    # gpt-4o-mini is the cheapest model that reliably follows this app's
    # JSON-mode ranking/tagging/parsing prompts — roughly 1/10th the
    # price of a full-size model (~$0.15/1M input, ~$0.60/1M output).
    openai_model: str = "gpt-4o-mini"
    openai_temperature: float = 0.1
    openai_max_tokens: int = 1024        # completion cap — output tokens cost ~4x input
    openai_timeout_seconds: int = 45

    # Separate, higher ceiling for the ranker specifically (groq_ranker.py's
    # _completion_budget). It outputs one JSON object per candidate event
    # (~180 tokens each) — up to top_k_for_llm=15 events needs ~2,700
    # tokens. openai_max_tokens=1024 above was clamping this and silently
    # truncating the ranker's JSON output mid-object on every call,
    # producing "unparseable JSON" and forcing every search onto the
    # rule-based fallback even with a healthy OpenAI account. Sized for
    # up to ~20 events with headroom; still far below what a full-size
    # model call would cost.
    openai_ranker_max_tokens: int = 4000

    # Comma-separated fallback chain tried when the primary model errors
    # or rate-limits. Keep every entry on the mini/nano tier — putting a
    # full-size model here defeats the cost cap.
    openai_fallback_models: str = "gpt-4o-mini,gpt-4.1-mini"

    # Self-imposed tokens-per-minute ceiling. This is a spend throttle,
    # not an OpenAI-enforced limit — it exists so a traffic spike queues
    # briefly instead of firing an unbounded number of billed calls at
    # once.
    openai_tpm_limit: int = 40000
    # Longest we'll queue a call waiting for TPM headroom before falling
    # back to the next model / giving up. Keep short — under concurrent
    # load a long wait here multiplies instead of adding once.
    openai_tpm_max_wait_seconds: float = 10.0

    # ── Hard cost ceiling ──────────────────────────
    # Once estimated spend for the current UTC day crosses this, chat_json()
    # refuses new calls (returns None) instead of silently keeping billing.
    # Every call site already degrades gracefully on None (skip validation,
    # fall back to rule-based scoring), so this fails safe.
    openai_daily_usd_budget: float = 5.0

    # ── Embedding model ───────────────────────────
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dim: int = 384
    enable_semantic_search: bool = False
    preload_index_on_startup: bool = False

    # ── pgvector semantic matching (Postgres/Neon only) ──
    # OFF by default — must be explicitly enabled. On a Render free
    # instance (512MB), loading the local ONNX embedding model
    # (fastembed + onnxruntime, ~250-300MB resident) is enough on its
    # own to exceed the memory limit and get the whole process killed
    # mid-request. Only flip this on if the instance has headroom, or
    # rely on the Jina API provider (network call, no local model).
    pgvector_enabled: bool = False
    pgvector_embed_batch: int = 64      # events embedded per search request (lazy backfill cap)
    pgvector_top_k: int = 80            # semantic hits pulled per search
    jina_api_key: str = ""
    jina_embedding_model: str = "jina-embeddings-v3"
    # fastembed loads a local ONNX model into process memory the first
    # time it's used — never do this unless the instance has spare RAM.
    # Even with pgvector_enabled=true, the Jina API provider (if
    # JINA_API_KEY is set) is preferred and fastembed is skipped unless
    # this is explicitly turned on too.
    pgvector_allow_local_embeddings: bool = False

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

    # ITA Trade Events API (data.trade.gov) — U.S. Commercial Service
    # trade shows, missions & conferences for exporters. Free with a
    # data.trade.gov account | https://developer.trade.gov/api-details#api=trade-events
    ita_api_key: str = ""

    # ── Scraper tuning ────────────────────────────
    scrape_delay_seconds: float = 2.0
    scrape_timeout_seconds: int = 15

    # ── Relevance tuning ─────────────────────────
    cosine_weight: float = 0.65
    rule_weight: float = 0.35
    go_threshold: float = 0.68
    consider_threshold: float = 0.42
    top_k_for_llm: int = 10   # aggressive pre-filter — only the top-scored candidates ever reach the LLM

    # ── Scheduler ────────────────────────────────
    refresh_interval_hours: int = 24

    # ── Email / Resend ────────────────────────────
    resend_api_key: str = ""
    resend_from_email: str = "kirubakaran.p@leadstrategus.com"

    # ── Fit scorer tuning (configurable via .env / Render env vars) ──
    # Fraction of B2B show attendees who are decision-makers (not vendors/booth staff)
    dm_ratio:             float = 0.35
    # ±% confidence interval around ICP estimate (shown as range in UI)
    icp_uncertainty:      float = 0.30
    # Round ICP estimate to nearest N for honest uncertainty display
    icp_round_to:         int   = 10
    # Minimum show scale per deal tier (for deal-size fit scoring)
    deal_min_strategic:   int   = 5000   # $500K+ deals need flagship events
    deal_min_enterprise:  int   = 1000   # $100K+ deals need significant events
    deal_min_high:        int   = 500    # $50K+ deals need mid-size events

    # ── Seed protection ───────────────────────────
    seed_admin_token: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
