"""
db/database.py — with safe ALTER TABLE migration.

The Neon PostgreSQL DB already has events with the old schema.
We need to ADD new columns without dropping or re-creating the table.

`add_missing_columns()` runs ALTER TABLE ... ADD COLUMN IF NOT EXISTS
for each new column. This is idempotent and safe to run on every startup.
"""
import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
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

        # asyncpg expects `ssl`, not `sslmode`.
        # Some managed Postgres providers (e.g., Neon) provide URLs with
        # `?sslmode=require`, which causes:
        # TypeError: connect() got an unexpected keyword argument 'sslmode'
        parts = urlsplit(url)
        query_pairs = parse_qsl(parts.query, keep_blank_values=True)
        normalized_pairs = []
        for key, value in query_pairs:
            if key == "sslmode":
                normalized_pairs.append(("ssl", value))
            else:
                normalized_pairs.append((key, value))
        normalized_query = urlencode(normalized_pairs)
        url = urlunsplit((parts.scheme, parts.netloc, parts.path, normalized_query, parts.fragment))
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
    # Neon: limit pool size to avoid connection exhaustion on free tier.
    # NOTE: each Uvicorn worker process (see Procfile's WEB_CONCURRENCY)
    # gets its OWN pool of this size — total connections against Neon is
    # pool_size × worker_count. Raising WEB_CONCURRENCY without checking
    # this against Neon's actual connection limit is how you get
    # "too many connections" errors under load.
    _engine_kw["pool_size"]    = 3
    _engine_kw["max_overflow"] = 2
    _engine_kw["pool_timeout"] = 30

engine            = create_async_engine(DATABASE_URL, **_engine_kw)
AsyncSessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)


# New columns that need to be added to the existing `events` table
# Format: (column_name, sql_type, default_value)
#
# Kept exhaustive against models/event.py::EventORM on purpose — a
# manually recreated / CSV-imported `events` table (e.g. after dropping
# the table in the Neon console and re-uploading a cleaned CSV) only has
# the columns present in that CSV. Every EventORM column not in the CSV
# needs to be listed here so ADD COLUMN IF NOT EXISTS backfills it on
# next startup, instead of the app crashing with UndefinedColumnError.
_NEW_COLUMNS = [
    ("event_venues",       "TEXT",     "''"),
    ("event_cities",       "TEXT",     "''"),
    ("related_industries", "TEXT",     "''"),
    ("website",            "TEXT",     "''"),
    ("organizer",          "TEXT",     "''"),
    ("serpapi_enriched",   "BOOLEAN",  "FALSE"),
    ("vip_count",          "INTEGER",  "0"),
    ("exhibitor_count",    "INTEGER",  "0"),
    ("speaker_count",      "INTEGER",  "0"),
    ("short_summary",      "TEXT",     "''"),
    ("edition_number",     "TEXT",     "''"),
    ("duration_days",      "INTEGER",  "1"),
    ("venue_name",         "TEXT",     "''"),
    ("address",            "TEXT",     "''"),
    ("is_virtual",         "BOOLEAN",  "FALSE"),
    ("is_hybrid",          "BOOLEAN",  "FALSE"),
    ("est_attendees",      "INTEGER",  "0"),
    ("ticket_price_usd",   "FLOAT",    "0.0"),
    ("price_description",  "TEXT",     "''"),
    ("registration_url",   "TEXT",     "''"),
    ("sponsors",           "TEXT",     "''"),
    ("speakers_url",       "TEXT",     "''"),
    ("agenda_url",         "TEXT",     "''"),
    ("category",           "TEXT",     "''"),
    ("industry_tags",      "TEXT",     "''"),
    ("audience_personas",  "TEXT",     "''"),
    ("relevance_score",    "FLOAT",    "0.0"),
    ("relevance_tier",     "TEXT",     "''"),
    ("rationale",          "TEXT",     "''"),
    ("confidence_score",   "FLOAT",    "0.8"),
    ("source_platform",    "TEXT",     "''"),
    ("source_url",         "TEXT",     "''"),
]

# (table, column_name) pairs that must be TEXT/VARCHAR, not TIMESTAMP —
# a Neon CSV-console import can auto-infer "2026-05-01"-style strings as
# a `timestamp` column, which then breaks every `start_date >= :string`
# comparison the app makes (EventORM.start_date is a plain String).
_FORCE_TEXT_COLUMNS = [
    ("events", "start_date"),
    ("events", "end_date"),
]


async def _add_missing_columns(conn):
    """
    Add new columns to `events` and `company_profiles` without dropping data.
    Uses IF NOT EXISTS — safe to run on every startup.
    """
    # (table, column_name, sql_type, default_value)
    _TABLE_COLUMNS = [
        ("events", col, typ, dflt) for col, typ, dflt in _NEW_COLUMNS
    ] + [
        ("company_profiles", "client_names", "TEXT", "''"),
    ]

    if IS_POSTGRES:
        for table, col_name, col_type, default in _TABLE_COLUMNS:
            try:
                await conn.execute(text(
                    f"ALTER TABLE {table} "
                    f"ADD COLUMN IF NOT EXISTS {col_name} {col_type} DEFAULT {default}"
                ))
                logger.debug(f"{table}.{col_name} ensured.")
            except Exception as e:
                logger.debug(f"{table}.{col_name} check: {e}")

        # Fix columns a CSV console-import may have auto-typed as TIMESTAMP
        # instead of TEXT (see _FORCE_TEXT_COLUMNS comment above).
        for table, col_name in _FORCE_TEXT_COLUMNS:
            try:
                row = (await conn.execute(text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_name = :t AND column_name = :c"
                ), {"t": table, "c": col_name})).fetchone()
                if row and row[0] not in ("text", "character varying"):
                    await conn.execute(text(
                        f"ALTER TABLE {table} ALTER COLUMN {col_name} "
                        f"TYPE TEXT USING {col_name}::text"
                    ))
                    logger.info(f"{table}.{col_name} converted {row[0]} → TEXT")
            except Exception as e:
                logger.warning(f"{table}.{col_name} type fix failed: {e}")
    elif IS_SQLITE:
        for table, col_name, col_type, default in _TABLE_COLUMNS:
            try:
                result  = await conn.execute(text(f"PRAGMA table_info({table})"))
                existing = {row[1] for row in result.fetchall()}
                if col_name not in existing:
                    await conn.execute(text(
                        f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type} DEFAULT {default}"
                    ))
                    logger.info(f"Added column: {table}.{col_name}")
            except Exception as e:
                logger.debug(f"{table}.{col_name} add failed: {e}")


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
        # source_health circuit-breaker state (survives cold starts)
        try:
            from ingestion.source_health import ensure_table as _ensure_sh_table
            await _ensure_sh_table(conn)
        except Exception as e:
            logger.debug(f"source_health table: {e}")

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
