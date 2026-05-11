"""
Database setup — FIXED for Render persistence.

Root cause of data loss:
  DATABASE_URL = sqlite+aiosqlite:///./events.db
  This stores the DB at CWD/events.db.
  On Render, CWD at runtime may NOT be inside the mounted disk,
  so every restart wipes the database.

Fix:
  1. Detect whether we're on Render (RENDER env var is set automatically)
  2. If on Render → use absolute path inside the mounted disk directory
  3. If local → use CWD as before
  4. Auto-create the data directory so it always exists

Render disk mount (render.yaml):
  mountPath: /opt/render/project/src/backend
  → DB lives at /opt/render/project/src/backend/data/events.db
  → This path survives restarts and redeploys
"""
import os
from sqlalchemy.ext.asyncio import (
    create_async_engine, AsyncSession, async_sessionmaker
)
from models.event import Base as EventBase
from models.company_profile import CompanyProfileORM  # registers table
from loguru import logger


def _resolve_database_url() -> str:
    """
    Return a database URL with an absolute, persistent path.

    Priority:
      1. DATABASE_URL env var if it's already an absolute path or postgres
      2. RENDER detected → use mounted disk absolute path
      3. Fallback → CWD relative (local dev)
    """
    raw = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./events.db")

    # PostgreSQL — always persistent, no path fix needed
    if "postgresql" in raw or "postgres" in raw:
        logger.info(f"Using PostgreSQL: {raw[:40]}...")
        return raw

    # Already an absolute SQLite path → use as-is
    if "sqlite" in raw and "///" in raw:
        after = raw.split("///", 1)[1]
        if after.startswith("/"):
            logger.info(f"Using absolute SQLite path: {after}")
            return raw

    # ── Render production environment ─────────────────────────
    # Render sets the RENDER env var automatically on all services.
    # The disk is mounted at RENDER_DISK_PATH (we set this in render.yaml env).
    render_disk = os.environ.get(
        "RENDER_DISK_PATH",
        "/opt/render/project/src/backend"
    )

    if os.environ.get("RENDER") or os.path.exists(render_disk):
        data_dir = os.path.join(render_disk, "data")
        os.makedirs(data_dir, exist_ok=True)
        db_path = os.path.join(data_dir, "events.db")
        url = f"sqlite+aiosqlite:///{db_path}"
        logger.info(f"Render mode — DB at absolute path: {db_path}")
        return url

    # ── Local development ──────────────────────────────────────
    local_dir = os.path.abspath(
        os.environ.get("LOCAL_DB_DIR", os.path.join(os.getcwd(), "data"))
    )
    os.makedirs(local_dir, exist_ok=True)
    db_path = os.path.join(local_dir, "events.db")
    url = f"sqlite+aiosqlite:///{db_path}"
    logger.info(f"Local mode — DB at: {db_path}")
    return url


# ── Build engine ───────────────────────────────────────────────
DATABASE_URL = _resolve_database_url()
IS_SQLITE    = "sqlite" in DATABASE_URL

engine_kwargs: dict = {
    "echo":         os.environ.get("DEBUG", "false").lower() == "true",
    "pool_pre_ping": True,
}
if IS_SQLITE:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
    # SQLite pragma tweaks for better concurrency and durability
    from sqlalchemy import event as sa_event

engine = create_async_engine(DATABASE_URL, **engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db():
    """Create all tables if they don't exist. Safe to call every startup."""
    async with engine.begin() as conn:
        await conn.run_sync(EventBase.metadata.create_all)

    # Enable WAL mode for SQLite — much better concurrent read performance
    # and prevents database locking during long ingestion runs
    if IS_SQLITE:
        async with AsyncSessionLocal() as session:
            await session.execute(
                __import__("sqlalchemy").text("PRAGMA journal_mode=WAL")
            )
            await session.execute(
                __import__("sqlalchemy").text("PRAGMA synchronous=NORMAL")
            )
            await session.execute(
                __import__("sqlalchemy").text("PRAGMA cache_size=-64000")   # 64MB cache
            )
            await session.execute(
                __import__("sqlalchemy").text("PRAGMA temp_store=MEMORY")
            )
            await session.commit()

    logger.info(f"Database initialised. URL: {DATABASE_URL[:60]}")


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
