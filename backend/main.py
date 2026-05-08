"""
Event Intelligence Agent — FastAPI Application
Run: uvicorn main:app --reload --port 8000

Daily scraping strategy (free-tier Render):
  1. APScheduler fires at 02:00 UTC daily inside the process.
  2. Pair with a FREE external cron at cron-job.org → POST /api/refresh every 24h.
     This also keeps the free-tier instance from spinning down.
  3. GitHub Actions free cron (.github/workflows/daily_ping.yml) is another option.
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from config import get_settings
from db.database import init_db
from api.routes_events import router as events_router
from ingestion.ingestion_manager import run_seed_only

settings = get_settings()


def get_allowed_origins() -> list[str]:
    origins = [o.strip() for o in settings.frontend_origin.split(",") if o.strip()]
    for default in ["http://localhost:5173", "http://localhost:3000"]:
        if default not in origins:
            origins.append(default)
    return origins


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=== Event Intelligence Agent starting up ===")

    # Init all DB tables (events + company_profiles)
    await init_db()

    # Seed if DB is empty
    from db.database import AsyncSessionLocal
    from db.crud import count_events
    async with AsyncSessionLocal() as db:
        total = await count_events(db)

    if total == 0:
        logger.info("DB is empty — seeding curated events...")
        stats = await run_seed_only()
        logger.info(f"Seed complete: {stats}")
    else:
        logger.info(f"DB has {total} events — skipping seed.")

    # ── Start APScheduler for daily event refresh ──────────
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        import pytz

        scheduler = AsyncIOScheduler(timezone=pytz.utc)

        async def _daily_refresh():
            logger.info("=== APScheduler: daily refresh triggered ===")
            from ingestion.ingestion_manager import run_ingestion
            try:
                stats = await run_ingestion()
                logger.info(f"=== Daily refresh done: {stats['total_saved']} events saved ===")
            except Exception as exc:
                logger.error(f"Daily refresh failed: {exc}")

        # Daily at 02:00 UTC
        scheduler.add_job(
            _daily_refresh,
            CronTrigger(hour=2, minute=0, timezone=pytz.utc),
            id="daily_event_refresh",
            replace_existing=True,
            misfire_grace_time=3600,
        )

        # Run full ingestion 90s after startup (not on every restart — only if DB is small)
        if total < 200:
            logger.info("DB has fewer than 200 events — scheduling immediate full ingestion.")
            scheduler.add_job(
                _daily_refresh,
                "date",
                run_date=datetime.utcnow() + timedelta(seconds=90),
                id="startup_full_refresh",
            )

        scheduler.start()
        logger.info("APScheduler running. Daily refresh at 02:00 UTC.")
        app.state.scheduler = scheduler

    except ImportError:
        logger.warning("APScheduler not installed — add 'apscheduler pytz' to requirements.txt")
        app.state.scheduler = None

    # Optional: warm up semantic index
    if settings.enable_semantic_search and settings.preload_index_on_startup:
        from db.database import AsyncSessionLocal
        from db.crud import get_all_events
        from relevance.embedder import load_index, add_events_to_index, get_index
        load_index()
        idx = get_index()
        if idx.ntotal == 0:
            async with AsyncSessionLocal() as db:
                events = await get_all_events(db, limit=500)
            if events:
                add_events_to_index(events)
                logger.info(f"FAISS rebuilt: {idx.ntotal} vectors.")

    logger.info("=== Startup complete ===")
    yield

    # Shutdown
    if hasattr(app.state, "scheduler") and app.state.scheduler:
        app.state.scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped.")

    if settings.enable_semantic_search:
        from relevance.embedder import save_index
        save_index()
    logger.info("=== Shutdown complete ===")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI-powered B2B event discovery and relevance ranking agent.",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(events_router, prefix="/api", tags=["events"])


@app.get("/")
async def root():
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "status": "ok",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    return {"status": "ok", "version": settings.app_version}


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Please try again."},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
