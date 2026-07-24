"""
backend/main.py  —  LeadStrategus Event Intelligence Agent
"""
import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from config import get_settings
from db.database import init_db
from api.routes_events import router as events_router

settings = get_settings()

_worker_tasks: list = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Event Intelligence Agent — starting up")
    logger.info(f"Database URL : {str(settings.database_url)[:60]}...")
    logger.info("=" * 60)
    await init_db()
    # NOTE: profile_feedback table init intentionally removed — the
    # table stored recall-boost data that's being retired (see
    # relevance/profile_store.py). Not calling init_profile_feedback_table()
    # here means the table won't be silently recreated after it's dropped.
    # Restore circuit-breaker state so a cold start on a free-tier host
    # (Render spins idle instances down) doesn't re-probe endpoints we
    # already know are dead/quota-exhausted from before the restart.
    try:
        from ingestion.source_health import load_from_db
        from db.database import AsyncSessionLocal as _SessionLocal
        await load_from_db(_SessionLocal)
    except Exception as _e:
        logger.warning(f"source_health restore skipped: {_e}")

    # POST /api/search job queue workers — no-ops (worker_loop returns
    # immediately) unless REDIS_URL is set; see queueing/search_queue.py.
    try:
        from queueing.search_queue import worker_loop
        from api.routes_events import _process_search_job
        for i in range(max(1, settings.search_queue_workers)):
            _worker_tasks.append(
                asyncio.create_task(worker_loop(f"search-{i}", _process_search_job))
            )
        logger.info(f"Search queue: {len(_worker_tasks)} worker(s) started")
    except Exception as _e:
        logger.warning(f"Search queue workers not started: {_e}")

    yield

    for t in _worker_tasks:
        t.cancel()
    for t in _worker_tasks:
        try:
            await t
        except asyncio.CancelledError:
            pass
    logger.info("Event Intelligence Agent — shutting down")


app = FastAPI(
    title       = "LeadStrategus Event Intelligence API",
    description = "AI-powered B2B trade show ranking and ICP matching",
    version     = "2.0.0",
    lifespan    = lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins  = ["*"],
    allow_methods  = ["*"],
    allow_headers  = ["*"],
)

# Main search + stats routes
app.include_router(events_router, prefix="/api", tags=["events"])

# Email PDF report — was defined but never mounted, so every
# POST /api/email-report 404'd. weasyprint/resend are imported lazily
# inside the handler, so this is safe to mount even if either package
# is missing from the environment (the endpoint just errors at call
# time instead of failing app startup).
try:
    from api.routes_email import router as email_router
    app.include_router(email_router, prefix="/api", tags=["email"])
    logger.info("Email report routes mounted at /api/email-report")
except ImportError as e:
    logger.warning(f"Email report routes not loaded: {e}")

# Admin routes: CSV upload + manual TM/PHQ ingest
try:
    from api.routes_admin import router as admin_router
    app.include_router(admin_router, prefix="/admin", tags=["admin"])
    logger.info("Admin routes mounted at /admin")
except ImportError as e:
    logger.warning(f"Admin routes not loaded: {e}")

# Analytics: session/activity tracking (write) + dashboard read API
try:
    from api.routes_analytics import router as analytics_router
    app.include_router(analytics_router, prefix="/api", tags=["analytics"])
    logger.info("Analytics routes mounted at /api/analytics")
except ImportError as e:
    logger.warning(f"Analytics routes not loaded: {e}")


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}
