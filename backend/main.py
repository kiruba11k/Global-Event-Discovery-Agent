"""
Event Intelligence Agent — FastAPI Application
Run: uvicorn main:app --reload --port 8000

Startup logic (fixed):
  1. init DB tables
  2. Count events
  3. If 0 → seed (fast, no purge)
  4. If > 0 → skip seed entirely (events already in DB)
  5. If < 100 → schedule a full ingestion in 90s to top up
  6. APScheduler runs full ingestion daily at 02:00 UTC
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
from api.routes_email  import router as email_router

settings = get_settings()


def get_allowed_origins() -> list[str]:
    origins = [o.strip() for o in settings.frontend_origin.split(",") if o.strip()]
    for default in ["http://localhost:5173", "http://localhost:3000"]:
        if default not in origins:
            origins.append(default)
    return origins


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=== Event Intelligence Agent starting ===")

    await init_db()

    from db.database import AsyncSessionLocal
    from db.crud import count_events
    async with AsyncSessionLocal() as db:
        total = await count_events(db)

    logger.info(f"DB has {total} events on startup.")

    # ── Step 1: seed only if completely empty ───────────────
    if total == 0:
        logger.info("DB empty — running seed (fast, no purge).")
        from ingestion.ingestion_manager import run_seed_only
        seed_stats = await run_seed_only()
        logger.info(f"Seed done: {seed_stats['total_inserted']} events inserted.")
        async with AsyncSessionLocal() as db:
            total = await count_events(db)
    else:
        logger.info(f"DB has {total} events — skipping seed.")

    # ── Step 2: start APScheduler ───────────────────────────
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        import pytz

        scheduler = AsyncIOScheduler(timezone=pytz.utc)

        async def _full_refresh():
            """Full ingestion — called daily and optionally on startup."""
            logger.info("=== Scheduled refresh: running full ingestion ===")
            from ingestion.ingestion_manager import run_ingestion
            try:
                stats = await run_ingestion()
                logger.info(
                    f"Refresh done — "
                    f"fetched={stats['total_fetched']} "
                    f"inserted={stats['total_inserted']} "
                    f"total_in_db={stats['total_in_db']}"
                )
            except Exception as exc:
                logger.error(f"Refresh error: {exc}")

        # Daily at 02:00 UTC
        scheduler.add_job(
            _full_refresh,
            CronTrigger(hour=2, minute=0, timezone=pytz.utc),
            id="daily_full_refresh",
            replace_existing=True,
            misfire_grace_time=3600,
        )

        # If DB is still small after seeding, kick off a full scrape in 90s.
        # This runs ONCE and populates the DB from all scrapers.
        # It does NOT purge seed events (purge_past_events skips Seed rows).
        if total < 100:
            logger.info(
                f"DB has only {total} events — "
                "scheduling full ingestion in 90s to populate from all scrapers."
            )
            scheduler.add_job(
                _full_refresh,
                "date",
                run_date=datetime.utcnow() + timedelta(seconds=90),
                id="startup_populate",
                replace_existing=True,
            )

        scheduler.start()
        app.state.scheduler = scheduler
        logger.info("APScheduler running — daily full refresh at 02:00 UTC.")

    except ImportError:
        logger.warning("APScheduler not installed. Run: pip install apscheduler pytz")
        app.state.scheduler = None

    # ── Step 3: optional semantic index warm-up ─────────────
    if settings.enable_semantic_search and settings.preload_index_on_startup:
        try:
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
        except Exception as e:
            logger.warning(f"Semantic index warm-up skipped: {e}")

    logger.info("=== Startup complete ===")
    yield

    # ── Shutdown ────────────────────────────────────────────
    if hasattr(app.state, "scheduler") and app.state.scheduler:
        app.state.scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped.")

    if settings.enable_semantic_search:
        try:
            from relevance.embedder import save_index
            save_index()
        except Exception:
            pass

    logger.info("=== Shutdown complete ===")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI-powered B2B event discovery and relevance ranking.",
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
app.include_router(email_router,  prefix="/api", tags=["email"])


@app.get("/")
async def root():
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "status":  "ok",
        "docs":    "/docs",
    }


@app.get("/health")
async def health():
    """
    Lightweight health check.
    Used by external cron services (cron-job.org, GitHub Actions)
    to keep the free-tier Render service awake.
    """
    from db.database import AsyncSessionLocal
    from db.crud import count_events
    try:
        async with AsyncSessionLocal() as db:
            total = await count_events(db)
        return {"status": "ok", "events_in_db": total}
    except Exception:
        return {"status": "ok"}   # don't fail health check on DB error


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
