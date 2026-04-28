"""
Event Intelligence Agent — FastAPI Application
Run locally: uvicorn main:app --reload --port 8000
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from config import get_settings
from db.database import init_db
from api.routes_events import router as events_router
from relevance.embedder import load_index, add_events_to_index
from ingestion.ingestion_manager import run_seed_only

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB, load FAISS index, seed events if empty."""
    logger.info("=== Event Intelligence Agent starting up ===")

    # 1. Init database tables
    await init_db()

    # 2. Load FAISS index from disk (if exists)
    load_index()

    # 3. Seed curated events if DB is empty
    from db.database import AsyncSessionLocal
    from db.crud import count_events
    async with AsyncSessionLocal() as db:
        total = await count_events(db)

    if total == 0:
        logger.info("DB is empty — seeding curated events...")
        stats = await run_seed_only()
        logger.info(f"Seed complete: {stats}")

        # 4. Build FAISS index from seed events
        from db.database import AsyncSessionLocal
        from db.crud import get_all_events
        async with AsyncSessionLocal() as db:
            events = await get_all_events(db, limit=500)
        if events:
            add_events_to_index(events)
            logger.info(f"FAISS index built with {len(events)} events.")
    else:
        logger.info(f"DB has {total} events. Loading into FAISS...")
        from db.database import AsyncSessionLocal
        from db.crud import get_all_events
        from relevance.embedder import get_index
        idx = get_index()
        if idx.ntotal == 0:
            async with AsyncSessionLocal() as db:
                events = await get_all_events(db, limit=500)
            add_events_to_index(events)
            logger.info(f"FAISS rebuilt: {idx.ntotal} vectors.")

    logger.info("=== Startup complete. Ready. ===")
    yield

    # Shutdown
    from relevance.embedder import save_index
    save_index()
    logger.info("=== Shutdown complete ===")


# ─── Create app ───────────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="AI-powered B2B event discovery and relevance ranking agent.",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ─── CORS ─────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_origin,
        "http://localhost:5173",
        "http://localhost:3000",
        "https://*.onrender.com",
        "*",  # tighten in production
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routes ───────────────────────────────────────────────────────
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


# ─── Global exception handler ─────────────────────────────────────
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
