"""
Database setup — SQLite (local dev) + PostgreSQL (production).

WHY THIS FILE WAS CHANGED
─────────────────────────
Render free tier has NO persistent disk. The `disk:` block in render.yaml
requires a paid plan ($7/mo Starter). On free tier the SQLite file sits on
ephemeral storage and is wiped on every restart / spin-down.

RECOMMENDED SETUP (free, permanent)
────────────────────────────────────
1. Create a free account at https://neon.tech
2. Create a new project (one click)
3. Copy the connection string shown in the dashboard — it looks like:
      postgresql://user:pass@ep-xxx.us-east-2.aws.neon.tech/neondb?sslmode=require
4. In Render → your backend service → Environment → add:
      DATABASE_URL = <the string from step 3>
5. Redeploy. Done. Data now persists forever across restarts and spin-downs.

This module auto-detects the driver and normalises the URL so you never have
to think about asyncpg vs aiosqlite differences.
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from config import get_settings
from models.event import Base as EventBase
from models.company_profile import CompanyProfileORM  # registers table in metadata
from loguru import logger

settings = get_settings()


# ── URL normalisation ──────────────────────────────────────────────

def _normalise_url(url: str) -> str:
    """
    Convert any DB URL to its async-driver form.

    postgres://…          → postgresql+asyncpg://…
    postgresql://…        → postgresql+asyncpg://…   (if no driver specified)
    sslmode=require       → ssl=require              (asyncpg syntax)
    sqlite+aiosqlite://…  → unchanged
    """
    # Heroku / Render / Neon / Supabase all emit "postgres://"
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgresql://") and "+asyncpg" not in url and "+psycopg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    # asyncpg uses ?ssl=require, not ?sslmode=require
    url = url.replace("sslmode=require", "ssl=require")
    url = url.replace("sslmode=prefer", "ssl=prefer")
    url = url.replace("sslmode=disable", "")

    return url


_db_url    = _normalise_url(settings.database_url)
_is_sqlite = _db_url.startswith("sqlite")

# ── Engine kwargs ──────────────────────────────────────────────────

_engine_kwargs: dict = {
    "echo":          settings.debug,
    "pool_pre_ping": True,
}

if _is_sqlite:
    # SQLite: disable thread-safety guard (async is single-process safe)
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # PostgreSQL via asyncpg: tune pool for Render free tier (512 MB RAM)
    _engine_kwargs["pool_size"]    = 5
    _engine_kwargs["max_overflow"] = 5
    _engine_kwargs["pool_timeout"] = 30
    _engine_kwargs["pool_recycle"] = 300   # recycle connections every 5 min


engine = create_async_engine(_db_url, **_engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(EventBase.metadata.create_all)
    db_type = "SQLite (local)" if _is_sqlite else "PostgreSQL (persistent)"
    logger.info(f"Database initialised [{db_type}] — events + company_profiles ready.")


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
