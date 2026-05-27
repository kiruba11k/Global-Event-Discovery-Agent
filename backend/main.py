"""
backend/main.py  —  LeadStrategus Event Intelligence Agent

Fixed: admin_router mounted AFTER app = FastAPI(...) is created.
The NameError was caused by calling app.include_router() before app existed.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from config import get_settings
from db.database import init_db
from api.routes_events import router as events_router

settings = get_settings()


# ── Lifespan (startup / shutdown) ────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Event Intelligence Agent — starting up")
    logger.info(f"Database URL : {str(settings.database_url)[:60]}...")
    logger.info(f"Render env   : {'YES' if settings.is_render else 'NO'}")
    logger.info("=" * 60)
    await init_db()
    yield
    logger.info("Event Intelligence Agent — shutting down")


# ── App creation ─────────────────────────────────────────────────
app = FastAPI(
    title       = "LeadStrategus Event Intelligence API",
    description = "AI-powered B2B trade show ranking and ICP matching",
    version     = "2.0.0",
    lifespan    = lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins  = ["*"],
    allow_methods  = ["*"],
    allow_headers  = ["*"],
)

# ── Routers ──────────────────────────────────────────────────────
# Main search + stats routes
app.include_router(events_router, prefix="/api", tags=["events"])

# Admin routes (CSV upload, manual TM/PHQ ingest, DB stats)
# Protected by X-Admin-Key header — never called by frontend
try:
    from api.routes_admin import router as admin_router
    app.include_router(admin_router, prefix="/admin", tags=["admin"])
    logger.info("Admin routes mounted at /admin")
except ImportError as e:
    logger.warning(f"Admin routes not loaded: {e}")

# ── Health check ─────────────────────────────────────────────────
@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "service": "leadstrategus-event-intelligence"}
