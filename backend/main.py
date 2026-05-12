"""
Event Intelligence Agent — main.py v3

Key fixes vs v2:
  1. Logs the exact DB file path on startup so you can verify it's on the disk
  2. Shows event count by source in startup logs
  3. Never re-seeds if any events already exist in DB
  4. Startup populate only fires if total < 60 (seed count)
  5. /health returns DB path and event breakdown for diagnostics
"""
import os
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from config import get_settings
from db.database import init_db, DATABASE_URL
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
    logger.info("=" * 60)
    logger.info("Event Intelligence Agent — starting up")
    logger.info(f"Database URL : {DATABASE_URL[:80]}")
    logger.info(f"Render env   : {'YES' if os.environ.get('RENDER') else 'NO (local)'}")
    logger.info("=" * 60)

    # Init DB tables (idempotent — safe every restart)
    await init_db()

    # Check current state
    from db.database import AsyncSessionLocal
    from db.crud import count_events, count_by_source
    async with AsyncSessionLocal() as db:
        total   = await count_events(db)
        by_src  = await count_by_source(db)

    logger.info(f"DB has {total} events on startup.")
    if by_src:
        for src, cnt in sorted(by_src.items(), key=lambda x: -x[1]):
            logger.info(f"  {src:<20} {cnt:>5} events")

    # ── Seed ONLY if completely empty ──────────────────────────
    if total == 0:
        logger.info("DB is empty → seeding curated events (no purge).")
        from ingestion.ingestion_manager import run_seed_only
        seed_stats = await run_seed_only()
        logger.info(
            f"Seed done: inserted={seed_stats['total_inserted']} "
            f"total_in_db={seed_stats['total_in_db']}"
        )
        total = seed_stats["total_in_db"]
    else:
        logger.info("DB has events → skipping seed.")

    # ── APScheduler ────────────────────────────────────────────
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        import pytz

        scheduler = AsyncIOScheduler(timezone=pytz.utc)

        async def _full_refresh():
            logger.info("APScheduler: running full ingestion...")
            from ingestion.ingestion_manager import run_ingestion
            try:
                stats = await run_ingestion()
                from db.crud import count_by_source
                from db.database import AsyncSessionLocal
                async with AsyncSessionLocal() as db:
                    by_src = await count_by_source(db)
                logger.info(
                    f"Refresh done — "
                    f"fetched={stats['total_fetched']} "
                    f"inserted={stats['total_inserted']} "
                    f"total_in_db={stats['total_in_db']}"
                )
                for src, cnt in sorted(by_src.items(), key=lambda x: -x[1]):
                    logger.info(f"  {src:<20} {cnt:>5} events")
            except Exception as exc:
                logger.error(f"Full refresh error: {exc}")

        # Daily at 02:00 UTC
        scheduler.add_job(
            _full_refresh,
            CronTrigger(hour=2, minute=0, timezone=pytz.utc),
            id="daily_full_refresh",
            replace_existing=True,
            misfire_grace_time=3600,
        )

        # Fire a full populate 2 minutes after startup if DB is small
        # (< 60 = basically just seeds, not yet scraped)
        if total < 60:
            logger.info(
                f"DB has only {total} events (likely just seeds). "
                "Scheduling full ingestion in 2 minutes."
            )
            scheduler.add_job(
                _full_refresh,
                "date",
                run_date=datetime.utcnow() + timedelta(seconds=120),
                id="startup_populate",
                replace_existing=True,
            )

        scheduler.start()
        app.state.scheduler = scheduler
        logger.info("APScheduler started — daily refresh at 02:00 UTC.")

    except ImportError:
        logger.warning("apscheduler not installed — add 'apscheduler pytz' to requirements.txt")
        app.state.scheduler = None

    logger.info("=" * 60)
    logger.info("Startup complete. Serving requests.")
    logger.info("=" * 60)
    yield

    # ── Shutdown ────────────────────────────────────────────────
    if hasattr(app.state, "scheduler") and app.state.scheduler:
        app.state.scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")
    logger.info("Shutdown complete.")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
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
    Detailed health check — shows DB path, event counts by source.
    Use this to verify the disk is working and data is persisting.
    """
    from db.database import AsyncSessionLocal, DATABASE_URL
    from db.crud import count_events, count_by_source
    try:
        async with AsyncSessionLocal() as db:
            total  = await count_events(db)
            by_src = await count_by_source(db)
        return {
            "status":          "ok",
            "version":         settings.app_version,
            "database_url":    DATABASE_URL[:60] + "...",
            "total_events":    total,
            "events_by_source": by_src,
            "render_env":      bool(os.environ.get("RENDER")),
            "disk_path":       os.environ.get("RENDER_DISK_PATH", "not set"),
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error."},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), reload=True)
