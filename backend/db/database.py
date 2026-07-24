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
    # Without these, a stalled connection or a DDL statement blocked on a
    # lock held by another session (e.g. init_db()'s ALTER TABLE ADD COLUMN
    # IF NOT EXISTS migration) hangs indefinitely with NO error logged —
    # observed in production as startup logging up through "Database URL"
    # and then going silent for 5+ minutes before Render force-restarted
    # the process, repeating on every retry. Bounded timeouts turn that
    # into a loud, diagnosable failure instead of a silent stall.
    _engine_kw["connect_args"] = {
        "timeout":         15,      # seconds to establish a new connection
        "command_timeout": 30,      # seconds per query/statement, incl. DDL
        "server_settings": {"lock_timeout": "10000"},  # ms — fail fast if a lock can't be acquired
    }

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
    # These two DateTime columns were missed in the original pass at
    # making this list exhaustive against EventORM — found in production
    # via "column events.ingested_at does not exist" on every /api/search.
    ("ingested_at",        "TIMESTAMP", "NOW()"),
    ("last_verified_at",   "TIMESTAMP", "NOW()"),
]

# (table, column_name) pairs that must be TEXT/VARCHAR, not TIMESTAMP —
# a Neon CSV-console import can auto-infer "2026-05-01"-style strings as
# a `timestamp` column, which then breaks every `start_date >= :string`
# comparison the app makes (EventORM.start_date is a plain String).
_FORCE_TEXT_COLUMNS = [
    ("events", "start_date"),
    ("events", "end_date"),
]


async def _run_isolated(conn, description: str, coro_fn):
    """
    Run one DDL/DML step in its own SAVEPOINT (conn.begin_nested()) so a
    failure there can't poison the rest of init_db()'s shared outer
    transaction. Without this, Postgres aborts the ENTIRE transaction on
    the first statement that errors — every later statement on the same
    connection then fails with PendingRollbackError regardless of what it
    is, which is what turned one failing "ADD COLUMN IF NOT EXISTS" into
    a full application-startup crash in production. The individual
    try/except blocks around each statement never actually isolated
    anything: catching the exception in Python doesn't roll back the
    Postgres transaction state, so every step after the first failure
    was doomed before it even ran.
    """
    try:
        async with conn.begin_nested():
            await coro_fn()
        return True
    except Exception as e:
        logger.debug(f"{description}: {e}")
        return False


async def _add_missing_columns(conn):
    """
    Add new columns to `events` without dropping data.
    Uses IF NOT EXISTS — safe to run on every startup.
    """
    # (table, column_name, sql_type, default_value)
    _TABLE_COLUMNS = [
        ("events", col, typ, dflt) for col, typ, dflt in _NEW_COLUMNS
    ]

    if IS_POSTGRES:
        for table, col_name, col_type, default in _TABLE_COLUMNS:
            ok = await _run_isolated(
                conn, f"{table}.{col_name} check",
                lambda t=table, c=col_name, ty=col_type, d=default: conn.execute(text(
                    f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS {c} {ty} DEFAULT {d}"
                )),
            )
            if ok:
                logger.debug(f"{table}.{col_name} ensured.")

        # Fix columns a CSV console-import may have auto-typed as TIMESTAMP
        # instead of TEXT (see _FORCE_TEXT_COLUMNS comment above).
        for table, col_name in _FORCE_TEXT_COLUMNS:
            async def _fix_text_column(t=table, c=col_name):
                row = (await conn.execute(text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_name = :t AND column_name = :c"
                ), {"t": t, "c": c})).fetchone()
                if row and row[0] not in ("text", "character varying"):
                    await conn.execute(text(
                        f"ALTER TABLE {t} ALTER COLUMN {c} "
                        f"TYPE TEXT USING {c}::text"
                    ))
                    logger.info(f"{t}.{c} converted {row[0]} → TEXT")
            await _run_isolated(conn, f"{table}.{col_name} type fix failed", _fix_text_column)
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
    # NOTE: company_profiles and search_submissions are retired — no
    # longer imported here, so create_all() won't recreate them after
    # they're dropped. See models/company_profile.py and
    # models/search_submission.py for why (superseded by
    # models/analytics.py's analytics_icp_submissions, which captures
    # the same submission data with normalized, actually-populated columns).
    from models.analytics import (  # noqa: registers tables
        AnalyticsEventORM, AnalyticsICPSubmissionORM,
        AnalyticsSearchResultORM, AnalyticsSessionORM,
    )

    async with engine.begin() as conn:
        # Create tables that don't exist yet
        await conn.run_sync(EventBase.metadata.create_all)
        # Add any missing columns to existing tables
        await _add_missing_columns(conn)
        # create_all() only creates indexes for brand-new tables — an
        # `events` table that already existed before this unique index
        # was added to the ORM model never gets it retroactively, which
        # silently breaks every `ON CONFLICT (dedup_hash)` upsert (falls
        # through to a Postgres error, 0 rows inserted). Ensure it exists
        # on every startup, idempotent.
        async def _ensure_dedup_index():
            await conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_events_dedup_hash "
                "ON events (dedup_hash)"
            ))
        if await _run_isolated(conn, "events.dedup_hash unique index check failed", _ensure_dedup_index):
            logger.debug("events.dedup_hash unique index ensured.")

        # source_health circuit-breaker state (survives cold starts)
        async def _ensure_source_health():
            from ingestion.source_health import ensure_table as _ensure_sh_table
            await _ensure_sh_table(conn)
        await _run_isolated(conn, "source_health table", _ensure_source_health)

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
