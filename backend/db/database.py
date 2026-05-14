"""
db/database.py — with safe ALTER TABLE migration.

The Neon PostgreSQL DB already has events with the old schema.
We need to ADD new columns without dropping or re-creating the table.

`add_missing_columns()` runs ALTER TABLE ... ADD COLUMN IF NOT EXISTS
for each new column. This is idempotent and safe to run on every startup.
"""
import os
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy import text
from loguru import logger


def _resolve_db_url() -> str:
    raw = os.environ.get("DATABASE_URL", "")

    # PostgreSQL (Neon, Render) — always persistent
    if raw and ("postgresql" in raw or "postgres" in raw):
        # Ensure we use the asyncpg driver
        url = raw.replace("postgresql://", "postgresql+asyncpg://", 1)
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        logger.info(f"PostgreSQL (Neon): {url[:60]}...")
        return url

    # Absolute SQLite path already set
    if raw and "sqlite" in raw:
        path_part = raw.split("///", 1)[-1]
        if path_part.startswith("/"):
            logger.info(f"SQLite (absolute): {path_part}")
            return raw

    # Auto-detect Render → use mounted disk
    render_disk = os.environ.get("RENDER_DISK_PATH", "/opt/render/project/src/backend")
    if os.environ.get("RENDER") or os.path.exists("/opt/render"):
        data_dir = os.path.join(render_disk, "data")
        os.makedirs(data_dir, exist_ok=True)
        db_path = os.path.join(data_dir, "events.db")
        logger.info(f"Render SQLite: {db_path}")
        return f"sqlite+aiosqlite:///{db_path}"

    # Local dev
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.abspath(os.path.join(base_dir, "..", "data"))
    os.makedirs(data_dir, exist_ok=True)
    db_path  = os.path.join(data_dir, "events.db")
    logger.info(f"Local SQLite: {db_path}")
    return f"sqlite+aiosqlite:///{db_path}"


DATABASE_URL = _resolve_db_url()
IS_SQLITE    = "sqlite" in DATABASE_URL
IS_POSTGRES  = "postgresql" in DATABASE_URL

_engine_kw: dict = {
    "echo":          os.environ.get("DEBUG", "false").lower() == "true",
    "pool_pre_ping": True,
}
if IS_SQLITE:
    _engine_kw["connect_args"] = {"check_same_thread": False}
if IS_POSTGRES:
    # Neon: limit pool size to avoid connection exhaustion on free tier
    _engine_kw["pool_size"]    = 3
    _engine_kw["max_overflow"] = 2
    _engine_kw["pool_timeout"] = 30

engine            = create_async_engine(DATABASE_URL, **_engine_kw)
AsyncSessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)


# New columns that need to be added to the existing `events` table
# Format: (column_name, sql_type, default_value)
_NEW_COLUMNS = [
    ("event_venues",       "TEXT",    "''"),
    ("event_cities",       "TEXT",    "''"),
    ("related_industries", "TEXT",    "''"),
    ("website",            "TEXT",    "''"),
    ("organizer",          "TEXT",    "''"),
    ("serpapi_enriched",   "BOOLEAN", "FALSE"),
    ("vip_count",          "INTEGER", "0"),
    ("exhibitor_count",    "INTEGER", "0"),
    ("speaker_count",      "INTEGER", "0"),
]


async def _add_missing_columns(conn):
    """
    Add new columns to the `events` table without dropping existing data.
    Uses IF NOT EXISTS — safe to run on every startup.
    """
    if IS_POSTGRES:
        for col_name, col_type, default in _NEW_COLUMNS:
            try:
                await conn.execute(text(
                    f"ALTER TABLE events "
                    f"ADD COLUMN IF NOT EXISTS {col_name} {col_type} DEFAULT {default}"
                ))
                logger.debug(f"Column '{col_name}' ensured.")
            except Exception as e:
                logger.debug(f"Column '{col_name}' check: {e}")
    elif IS_SQLITE:
        # SQLite doesn't support IF NOT EXISTS on ALTER TABLE
        # Check existing columns first
        result = await conn.execute(text("PRAGMA table_info(events)"))
        existing = {row[1] for row in result.fetchall()}
        for col_name, col_type, default in _NEW_COLUMNS:
            if col_name not in existing:
                try:
                    await conn.execute(text(
                        f"ALTER TABLE events ADD COLUMN {col_name} {col_type} DEFAULT {default}"
                    ))
                    logger.info(f"Added column: {col_name}")
                except Exception as e:
                    logger.debug(f"Column '{col_name}' add failed: {e}")


async def init_db():
    """
    Create all tables + add any missing columns.
    Idempotent — safe to call on every startup.
    """
    from models.event import Base as EventBase
    from models.company_profile import CompanyProfileORM  # noqa: registers table

    async with engine.begin() as conn:
        # Create tables that don't exist yet
        await conn.run_sync(EventBase.metadata.create_all)
        # Add any missing columns to existing tables
        await _add_missing_columns(conn)

    # SQLite performance tweaks
    if IS_SQLITE:
        async with AsyncSessionLocal() as session:
            await session.execute(text("PRAGMA journal_mode=WAL"))
            await session.execute(text("PRAGMA synchronous=NORMAL"))
            await session.execute(text("PRAGMA cache_size=-32000"))
            await session.execute(text("PRAGMA temp_store=MEMORY"))
            await session.commit()

    logger.info(f"DB ready. URL: {DATABASE_URL[:70]}")


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
