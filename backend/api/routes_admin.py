"""
api/routes_admin.py  —  Admin-only backend routes (never exposed to frontend)

Three capabilities:
  POST /admin/upload-csv        Upload events CSV → parse → smart-upsert to Neon DB
  POST /admin/ingest/ticketmaster  Manual trigger for Ticketmaster live scrape
  POST /admin/ingest/predicthq     Manual trigger for PredictHQ live scrape
  GET  /admin/ingest/status        Last-run summary for all manual ingestions

Security:
  All routes require  X-Admin-Key: {ADMIN_SECRET_KEY}  header.
  Set ADMIN_SECRET_KEY in your Render environment variables.
  These routes are never called by the frontend — admin/curl/Postman only.

Smart upsert (merge strategy):
  When an event already exists in DB (matched by dedup_hash):
    - If API / CSV field is non-empty AND current DB value is empty/zero → REPLACE
    - If est_attendees in API > DB value → REPLACE (better data wins)
    - If source_url / registration_url in DB is a bad/homepage URL → REPLACE with API
    - Scoring fields (relevance_score, rationale) are NEVER overwritten by ingestion
    - last_verified_at is always updated to NOW on any match

  This means re-running ingestion is always safe — it only improves the data.

Mount in main.py — add AFTER app = FastAPI(...) is defined:
  from api.routes_admin import router as admin_router
  app.include_router(admin_router, prefix="/admin", tags=["admin"])

  IMPORTANT: this line must come AFTER  app = FastAPI(lifespan=lifespan)
  NOT at the top of the file before app is created.
"""
from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import time
import uuid
from datetime import datetime, date
from typing import Any, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from loguru import logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from db.crud import batch_upsert_events
from db.database import get_db
from ingestion.icp_query_builder import build_queries
from ingestion.platform_normaliser import normalise
from ingestion.ticketmaster_realtime import run_ticketmaster_queries
from ingestion.predicthq_realtime import run_predicthq_queries
from models.event import EventORM

router   = APIRouter()
settings = get_settings()

# ── In-memory run log (last 10 runs per source) ───────────────────
_run_log: list[dict] = []
_MAX_LOG = 20


# ─────────────────────────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────────────────────────

def _check_admin(x_admin_key: str = Header(default="")) -> None:
    """Require X-Admin-Key header matching ADMIN_SECRET_KEY env var."""
    secret = getattr(settings, "admin_secret_key", "") or ""
    if not secret:
        raise HTTPException(503, "ADMIN_SECRET_KEY not configured on server")
    if x_admin_key != secret:
        raise HTTPException(401, "Invalid or missing X-Admin-Key header")


# ─────────────────────────────────────────────────────────────────
# Smart merge helpers
# ─────────────────────────────────────────────────────────────────

_BAD_DOMAINS = frozenset({
    "singaporeexpo.com.sg", "excel.london", "expoforum-center.ru",
    "fierapordenone.it", "twtc.org.tw", "thecharlottecountyfair.com",
    "fair.ee", "biec.in", "necc.co.in", "jiexpo.com", "bigsight.jp",
    "messe-berlin.de", "gouda.nl", "uzexpocentre.uz", "facebook.com",
    "m.facebook.com", "twitter.com", "linkedin.com", "instagram.com",
    "wikipedia.org", "visitumea.se", "stazione-leopolda.com",
})


def _is_bad_url(url: str) -> bool:
    if not url: return True
    if url.startswith("https://www.google.com/search"): return True
    try:
        host = urlparse(url).netloc.lower().lstrip("www.").lstrip("m.")
        if host in _BAD_DOMAINS: return True
        path = urlparse(url).path.strip("/")
        if not path: return True   # root-domain homepage
    except Exception:
        pass
    return False


def _should_replace(db_val: Any, api_val: Any, field: str) -> bool:
    """
    Returns True if the API/CSV value is better than what's in the DB.

    Rules:
    1. DB is empty/zero/null  AND  API has a real value  →  always replace
    2. est_attendees: API > DB (higher = more reliable)
    3. registration_url / website / source_url: bad URL in DB  AND  good URL in API
    4. description: DB has placeholder-style text AND API has real description
    5. country: DB is empty or a 2-letter code AND API has full name (or vice-versa) → prefer non-empty
    6. Scoring fields (relevance_score, rationale, relevance_tier): NEVER replace
    7. ingested_at: NEVER replace (preserve original)
    8. serpapi_enriched: only replace False → True, never True → False
    """
    # Fields that ingestion must never overwrite
    IMMUTABLE = {"relevance_score", "relevance_tier", "rationale",
                 "ingested_at", "confidence_score"}
    if field in IMMUTABLE:
        return False

    api_empty = (api_val is None or api_val == "" or api_val == 0 or api_val is False)
    db_empty  = (db_val  is None or db_val  == "" or db_val  == 0 or db_val  is False)

    if api_empty:
        return False    # never overwrite good data with nothing

    if db_empty:
        return True     # always fill an empty field with real data

    # est_attendees: use whichever is larger
    if field == "est_attendees":
        try:
            return int(api_val) > int(db_val)
        except (TypeError, ValueError):
            return False

    # URL fields: replace if DB has a bad/homepage URL
    if field in ("registration_url", "website", "source_url"):
        db_bad  = _is_bad_url(str(db_val))
        api_bad = _is_bad_url(str(api_val))
        if db_bad and not api_bad:
            return True
        return False

    # serpapi_enriched: only promote False → True
    if field == "serpapi_enriched":
        return bool(api_val) is True and bool(db_val) is False

    # description: replace if DB looks like an auto-generated placeholder
    if field == "description":
        db_str  = str(db_val).strip()
        api_str = str(api_val).strip()
        looks_placeholder = (
            len(db_str) < 60 or
            " — " in db_str and len(db_str) < 100 or
            db_str.lower().startswith(("business events", "conference in "))
        )
        if looks_placeholder and len(api_str) > len(db_str):
            return True
        return False

    return False    # all other fields: keep existing DB value


async def _smart_upsert_batch(
    db:     AsyncSession,
    events: list[dict],
) -> dict:
    """
    For each event:
      - If dedup_hash NOT in DB → INSERT
      - If dedup_hash IN DB     → UPDATE only fields where API data is better
    Returns {"inserted": N, "updated": N, "unchanged": N, "skipped": N}
    """
    if not events:
        return {"inserted": 0, "updated": 0, "unchanged": 0, "skipped": 0}

    today     = date.today().isoformat()
    inserted  = updated = unchanged = skipped = 0

    # UPDATABLE fields (not scoring, not ingested_at)
    UPDATABLE = [
        "source_url", "name", "description", "category",
        "start_date", "end_date", "venue_name", "city", "country",
        "industry_tags", "audience_personas", "est_attendees",
        "price_description", "registration_url", "website",
        "sponsors", "speakers_url", "agenda_url", "serpapi_enriched",
    ]

    for ev in events:
        dh = ev.get("dedup_hash", "")
        if not dh:
            skipped += 1
            continue

        # Skip past events
        start = ev.get("start_date", "")
        if start and start < today:
            skipped += 1
            continue

        # Check if exists
        result = await db.execute(
            select(EventORM).where(EventORM.dedup_hash == dh)
        )
        existing: Optional[EventORM] = result.scalar_one_or_none()

        if existing is None:
            # New event — INSERT
            try:
                new_id = ev.get("id") or str(uuid.uuid4())
                obj = EventORM(
                    id                = new_id,
                    source_platform   = ev.get("source_platform", ""),
                    source_url        = ev.get("source_url", ""),
                    dedup_hash        = dh,
                    name              = ev.get("name", ""),
                    description       = ev.get("description", ""),
                    category          = ev.get("category", ""),
                    start_date        = ev.get("start_date", ""),
                    end_date          = ev.get("end_date", ""),
                    venue_name        = ev.get("venue_name", ""),
                    city              = ev.get("city", ""),
                    country           = ev.get("country", ""),
                    industry_tags     = ev.get("industry_tags", ""),
                    audience_personas = ev.get("audience_personas", ""),
                    est_attendees     = int(ev.get("est_attendees") or 0),
                    price_description = ev.get("price_description", ""),
                    registration_url  = ev.get("registration_url", ""),
                    website           = ev.get("website", ""),
                    sponsors          = ev.get("sponsors", ""),
                    speakers_url      = ev.get("speakers_url", ""),
                    agenda_url        = ev.get("agenda_url", ""),
                    relevance_score   = float(ev.get("relevance_score") or 0.0),
                    relevance_tier    = ev.get("relevance_tier", ""),
                    rationale         = ev.get("rationale", ""),
                    confidence_score  = float(ev.get("confidence_score") or 0.8),
                    ingested_at       = datetime.utcnow(),
                    last_verified_at  = datetime.utcnow(),
                    serpapi_enriched  = bool(ev.get("serpapi_enriched", False)),
                )
                db.add(obj)
                inserted += 1
            except Exception as exc:
                logger.debug(f"Insert error [{ev.get('name','?')[:40]}]: {exc}")
                skipped += 1

        else:
            # Existing event — check field-by-field
            patches: dict = {}
            for field in UPDATABLE:
                api_val = ev.get(field)
                db_val  = getattr(existing, field, None)
                if _should_replace(db_val, api_val, field):
                    patches[field] = api_val

            if patches:
                patches["last_verified_at"] = datetime.utcnow()
                await db.execute(
                    update(EventORM)
                    .where(EventORM.dedup_hash == dh)
                    .values(**patches)
                )
                updated += 1
            else:
                # Still update last_verified_at so we know we checked it
                await db.execute(
                    update(EventORM)
                    .where(EventORM.dedup_hash == dh)
                    .values(last_verified_at=datetime.utcnow())
                )
                unchanged += 1

    await db.commit()
    return {"inserted": inserted, "updated": updated,
            "unchanged": unchanged, "skipped": skipped}


# ─────────────────────────────────────────────────────────────────
# CSV parsing
# ─────────────────────────────────────────────────────────────────

def _parse_csv(content: bytes) -> list[dict]:
    """
    Parse CSV bytes → list of normaliser-ready dicts.
    Tolerates both clean 28-column exports and old 47-column exports.
    Detects delimiter (comma or semicolon).
    """
    text = content.decode("utf-8-sig", errors="replace")
    dialect = "excel"
    sample = text[:2000]
    if sample.count(";") > sample.count(","):
        dialect = "excel-semicolon"

    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    rows   = []
    skipped = 0

    for row in reader:
        # Strip whitespace from keys and values
        row = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items()}

        name = row.get("name", "").strip()
        if not name:
            skipped += 1
            continue

        # Determine source_platform
        raw_platform = row.get("source_platform", "CSV_UPLOAD")
        clean = normalise(row, raw_platform)
        rows.append(clean)

    logger.info(f"CSV parse: {len(rows)} valid rows, {skipped} skipped (no name)")
    return rows


# ─────────────────────────────────────────────────────────────────
# Route 1: CSV Upload
# ─────────────────────────────────────────────────────────────────

@router.post(
    "/upload-csv",
    summary="Upload events CSV to Neon DB",
    description=(
        "Upload a CSV file of events. Parses and smart-upserts into Neon DB. "
        "Accepts both 28-column clean schema and old 47-column schema. "
        "Existing events are updated only where API/CSV data is better."
    ),
)
async def upload_csv(
    file: UploadFile = File(..., description="CSV file with event rows"),
    dry_run: bool = Form(default=False, description="Parse + count only, no DB writes"),
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(_check_admin),
):
    t0 = time.perf_counter()

    if not file.filename.endswith(".csv"):
        raise HTTPException(400, "File must be a .csv")

    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(413, "CSV exceeds 50 MB limit")

    try:
        events = _parse_csv(content)
    except Exception as exc:
        raise HTTPException(422, f"CSV parse error: {exc}")

    if not events:
        raise HTTPException(422, "No valid event rows found in CSV (all rows missing 'name')")

    if dry_run:
        return {
            "dry_run":     True,
            "rows_parsed": len(events),
            "sample":      [{"name": e.get("name"), "start_date": e.get("start_date"),
                              "city": e.get("city"), "dedup_hash": e.get("dedup_hash")}
                             for e in events[:5]],
        }

    result = await _smart_upsert_batch(db, events)
    elapsed = round(time.perf_counter() - t0, 2)

    log_entry = {
        "source":    "csv_upload",
        "file":      file.filename,
        "timestamp": datetime.utcnow().isoformat(),
        "elapsed_s": elapsed,
        **result,
    }
    _run_log.insert(0, log_entry)
    del _run_log[_MAX_LOG:]

    logger.info(
        f"CSV upload '{file.filename}': "
        f"inserted={result['inserted']} updated={result['updated']} "
        f"unchanged={result['unchanged']} skipped={result['skipped']} "
        f"in {elapsed}s"
    )
    return {"file": file.filename, "elapsed_s": elapsed, **result}


# ─────────────────────────────────────────────────────────────────
# Route 2: Manual Ticketmaster ingestion
# ─────────────────────────────────────────────────────────────────

@router.post(
    "/ingest/ticketmaster",
    summary="Manually trigger Ticketmaster live scrape",
    description=(
        "Runs Ticketmaster Discovery API queries and stores results. "
        "Existing events are updated only where TM data is better. "
        "Use keywords and countries to scope the search."
    ),
)
async def ingest_ticketmaster(
    keywords:    str = Form(
        default="conference,summit,expo,trade show",
        description="Comma-separated keywords to search (each becomes a query)",
    ),
    countries:   str = Form(
        default="US,GB,SG,IN,DE,AU",
        description="Comma-separated 2-letter ISO country codes",
    ),
    date_from:   str = Form(default="", description="ISO date YYYY-MM-DD (default: today)"),
    date_to:     str = Form(default="", description="ISO date YYYY-MM-DD (default: +12 months)"),
    max_pages:   int = Form(default=2,  description="Pages per query (50 events/page, max 4)"),
    dry_run:     bool = Form(default=False),
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(_check_admin),
):
    api_key = getattr(settings, "tm_api_key", "") or ""
    if not api_key:
        raise HTTPException(503, "TM_API_KEY not configured on server")

    max_pages = min(max_pages, 4)

    # Build query objects from keywords × countries
    from ingestion.icp_query_builder import TicketmasterQuery

    today    = date.today().isoformat()
    df       = date_from or today
    dt       = date_to   or f"{int(today[:4]) + 1}{today[4:]}"   # +1 year
    start_dt = f"{df}T00:00:00Z"
    end_dt   = f"{dt}T23:59:59Z"

    kw_list  = [k.strip() for k in keywords.split(",") if k.strip()]
    cc_list  = [c.strip().upper() for c in countries.split(",") if c.strip()]

    queries: list[TicketmasterQuery] = []
    for kw in kw_list:
        for cc in cc_list:
            q = TicketmasterQuery()
            q.keyword      = kw
            q.country_code = cc
            q.start_dt     = start_dt
            q.end_dt       = end_dt
            queries.append(q)

    logger.info(
        f"TM manual ingest: {len(queries)} queries "
        f"({len(kw_list)} keywords × {len(cc_list)} countries)"
    )
    t0 = time.perf_counter()

    events = await run_ticketmaster_queries(
        queries             = queries,
        api_key             = api_key,
        date_from           = df,
        date_to             = dt,
        max_pages_per_query = max_pages,
    )

    if dry_run or not events:
        elapsed = round(time.perf_counter() - t0, 2)
        return {
            "dry_run":      dry_run,
            "events_found": len(events),
            "elapsed_s":    elapsed,
            "sample": [{"name": e.get("name"), "start_date": e.get("start_date"),
                        "city": e.get("city"), "country": e.get("country"),
                        "est_attendees": e.get("est_attendees")}
                       for e in events[:5]],
        }

    result  = await _smart_upsert_batch(db, events)
    elapsed = round(time.perf_counter() - t0, 2)

    log_entry = {
        "source":    "ticketmaster",
        "keywords":  keywords,
        "countries": countries,
        "timestamp": datetime.utcnow().isoformat(),
        "elapsed_s": elapsed,
        "events_fetched": len(events),
        **result,
    }
    _run_log.insert(0, log_entry)
    del _run_log[_MAX_LOG:]

    logger.info(
        f"TM ingest done: fetched={len(events)} "
        f"inserted={result['inserted']} updated={result['updated']} "
        f"in {elapsed}s"
    )
    return {
        "source":        "ticketmaster",
        "events_fetched": len(events),
        "elapsed_s":     elapsed,
        **result,
    }


# ─────────────────────────────────────────────────────────────────
# Route 3: Manual PredictHQ ingestion
# ─────────────────────────────────────────────────────────────────

@router.post(
    "/ingest/predicthq",
    summary="Manually trigger PredictHQ live scrape",
    description=(
        "Runs PredictHQ Events API queries and stores results. "
        "PHQ provides phq_attendance (AI-predicted) and covers events not "
        "on mainstream platforms. Best for conferences, expos, trade shows. "
        "Existing events are updated only where PHQ data is better (esp. est_attendees)."
    ),
)
async def ingest_predicthq(
    keywords:    str  = Form(
        default="conference,summit,expo,trade show,B2B",
        description="Comma-separated full-text search keywords",
    ),
    countries:   str  = Form(
        default="US,GB,SG,IN,DE,AU,UAE",
        description="Comma-separated 2-letter ISO country codes",
    ),
    date_from:   str  = Form(default="", description="ISO date YYYY-MM-DD (default: today)"),
    date_to:     str  = Form(default="", description="ISO date YYYY-MM-DD (default: +12 months)"),
    min_rank:    int  = Form(default=30,  description="PHQ minimum rank filter (0-100)"),
    max_pages:   int  = Form(default=2,   description="Pages per query (50 events/page, max 4)"),
    dry_run:     bool = Form(default=False),
    db: AsyncSession  = Depends(get_db),
    _auth: None       = Depends(_check_admin),
):
    api_key = getattr(settings, "predicthq_key", "") or ""
    if not api_key:
        raise HTTPException(503, "PREDICTHQ_KEY not configured on server")

    max_pages = min(max_pages, 4)

    from ingestion.icp_query_builder import PredictHQQuery

    today  = date.today().isoformat()
    df     = date_from or today
    dt     = date_to   or f"{int(today[:4]) + 1}{today[4:]}"

    kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
    cc_list = [c.strip().upper() for c in countries.split(",") if c.strip()]

    queries: list[PredictHQQuery] = []
    for kw in kw_list:
        for cc in cc_list:
            q = PredictHQQuery()
            q.q            = kw
            q.country_code = cc
            q.start_gte    = df
            q.end_lte      = dt
            queries.append(q)

    logger.info(
        f"PHQ manual ingest: {len(queries)} queries "
        f"({len(kw_list)} keywords × {len(cc_list)} countries) "
        f"min_rank={min_rank}"
    )
    t0 = time.perf_counter()

    events = await run_predicthq_queries(
        queries    = queries,
        api_key    = api_key,
        date_from  = df,
        date_to    = dt,
        max_pages  = max_pages,
    )

    if dry_run or not events:
        elapsed = round(time.perf_counter() - t0, 2)
        return {
            "dry_run":      dry_run,
            "events_found": len(events),
            "elapsed_s":    elapsed,
            "sample": [{"name": e.get("name"), "start_date": e.get("start_date"),
                        "city": e.get("city"), "country": e.get("country"),
                        "est_attendees": e.get("est_attendees"),
                        "industry_tags": e.get("industry_tags")}
                       for e in events[:5]],
        }

    result  = await _smart_upsert_batch(db, events)
    elapsed = round(time.perf_counter() - t0, 2)

    log_entry = {
        "source":    "predicthq",
        "keywords":  keywords,
        "countries": countries,
        "timestamp": datetime.utcnow().isoformat(),
        "elapsed_s": elapsed,
        "events_fetched": len(events),
        **result,
    }
    _run_log.insert(0, log_entry)
    del _run_log[_MAX_LOG:]

    logger.info(
        f"PHQ ingest done: fetched={len(events)} "
        f"inserted={result['inserted']} updated={result['updated']} "
        f"in {elapsed}s"
    )
    return {
        "source":         "predicthq",
        "events_fetched": len(events),
        "elapsed_s":      elapsed,
        **result,
    }


# ─────────────────────────────────────────────────────────────────
# Route 4: Status / run log
# ─────────────────────────────────────────────────────────────────

@router.get(
    "/ingest/status",
    summary="Last ingestion run summary",
    description="Returns the last 20 ingestion run results (CSV + TM + PHQ).",
)
async def ingest_status(
    _auth: None = Depends(_check_admin),
):
    return {
        "runs":       _run_log,
        "total_runs": len(_run_log),
    }


@router.get(
    "/db/count",
    summary="Count events in DB",
    description="Returns total row count and counts by source_platform.",
)
async def db_count(
    db: AsyncSession = Depends(get_db),
    _auth: None      = Depends(_check_admin),
):
    from sqlalchemy import func, select
    total_r  = await db.execute(select(func.count()).select_from(EventORM))
    total    = total_r.scalar() or 0

    platform_r = await db.execute(
        select(EventORM.source_platform, func.count().label("n"))
        .group_by(EventORM.source_platform)
        .order_by(func.count().desc())
    )
    by_platform = {row.source_platform: row.n for row in platform_r}

    future_r = await db.execute(
        select(func.count()).select_from(EventORM)
        .where(EventORM.start_date >= date.today().isoformat())
    )
    future = future_r.scalar() or 0

    return {
        "total_events":       total,
        "future_events":      future,
        "events_by_platform": by_platform,
    }
