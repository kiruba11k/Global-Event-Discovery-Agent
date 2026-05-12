"""
Event Routes v2
POST /api/search             — ICP + optional company context
POST /api/company-profile    — save company profile (multipart: JSON + optional PDF)
GET  /api/company-profile/{id}
GET  /api/events             — paginated list
GET  /api/events/{id}
GET  /api/stats
POST /api/refresh
POST /api/seed-10times       — protected background 10times bulk seed
GET  /api/seed-10times/status

UPDATED:
- Accurate refresh ingestion stats logging
- resend_enabled added in /stats
- Improved refresh endpoint documentation/logging
- Preserved seed-10times functionality from old version
"""

import csv, hashlib, io, json, uuid
from datetime import date, datetime
from typing import Iterable, Optional

from fastapi import (
    APIRouter, Depends, HTTPException, Query,
    BackgroundTasks, UploadFile, File, Form, Header,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.crud import (
    get_candidate_events, get_all_events, get_event_by_id, count_events,
    create_company_profile, get_company_profile, batch_upsert_events,
)

from models.icp_profile import SearchRequest, SearchResponse, CompanyContext
from models.company_profile import CompanyProfileCreate
from models.event import EventCreate

from relevance.scorer import score_candidates
from relevance.groq_ranker import rank_with_groq

from ingestion.ingestion_manager import run_ingestion, run_seed_only
from scripts.seed_10times_global import CrawlConfig, run_10times_seed
from scripts.seed_conferencealerts_global import ConferenceAlertsSeedConfig, run_conferencealerts_seed
from scripts.seed_eventseye_global import run_eventseye_seed
from config import get_settings
from loguru import logger

router = APIRouter()
settings = get_settings()

_last_results: dict = {}

_seed_10times_status: dict = {
    "running": False,
    "last_result": None,
    "last_error": None,
}

_seed_conferencealerts_status: dict = {
    "running": False,
    "last_result": None,
    "last_error": None,
}


_seed_global_status: dict = {
    "running": False,
    "last_result": None,
    "last_error": None,
}

RESULT_LIMIT = 7
GO_RESULT_COUNT = 4
CONSIDER_RESULT_COUNT = 3


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d")
    except (TypeError, ValueError):
        return None


def _within_requested_dates(event, date_from: Optional[str], date_to: Optional[str]) -> bool:
    """
    Require the event start date to stay inside the user-requested range.
    """
    event_start = _parse_date(getattr(event, "start_date", None))

    if not event_start:
        return False

    range_start = _parse_date(date_from)
    range_end = _parse_date(date_to)

    if range_start and event_start < range_start:
        return False

    if range_end and event_start > range_end:
        return False

    return True


def _apply_result_mix(ranked: Iterable) -> list:
    """
    Return at most seven events with exactly:
    - 4 GO
    - 3 CONSIDER
    when available.
    """
    selected = list(ranked)[:RESULT_LIMIT]

    for idx, event in enumerate(selected):
        event.fit_verdict = "GO" if idx < GO_RESULT_COUNT else "CONSIDER"

    return selected


# ─────────────────────────────────────────────────────────────
# PDF extraction
# ─────────────────────────────────────────────────────────────



def _norm(value: str | None) -> str:
    return (value or "").strip()


def _csv_dedup_hash(name: str, start_date: str, city: str, country: str) -> str:
    raw = "|".join([_norm(name).lower(), _norm(start_date), _norm(city).lower(), _norm(country).lower()])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _parse_csv_event_row(row: dict, row_number: int) -> EventCreate:
    normalized_row = {_norm(str(k)).lower(): v for k, v in row.items() if k is not None}

    name = _norm(normalized_row.get("name"))
    start_date = _norm(normalized_row.get("start_date"))
    end_date = _norm(normalized_row.get("end_date"))

    # Be tolerant with partial CSVs: if start_date is missing but end_date is valid, use end_date.
    if not start_date and _parse_date(end_date):
        start_date = end_date

    if not name or not start_date:
        raise ValueError(f"row {row_number}: 'name' and 'start_date' are required")

    if not _parse_date(start_date):
        raise ValueError(f"row {row_number}: invalid start_date '{start_date}' (expected YYYY-MM-DD)")

    event_id = _norm(normalized_row.get("id")) or str(uuid.uuid4())
    city = _norm(normalized_row.get("city"))
    country = _norm(normalized_row.get("country"))
    source_url = _norm(normalized_row.get("source_url"))
    website = _norm(normalized_row.get("website"))

    related_industries = _norm(normalized_row.get("related_industries"))

    return EventCreate(
        id=event_id,
        dedup_hash=_csv_dedup_hash(name, start_date, city, country),
        source_platform="CSV_UPLOAD",
        source_url=source_url or website or f"csv://upload/{event_id}",
        name=name,
        description=_norm(normalized_row.get("description")),
        industry_tags=related_industries,
        start_date=start_date,
        end_date=end_date or start_date,
        venue_name=_norm(normalized_row.get("venue")),
        city=city,
        country=country,
        registration_url=website,
    )

def _extract_pdf_text(file_bytes: bytes) -> str:
    try:
        import pypdf
        import io as _io

        reader = pypdf.PdfReader(_io.BytesIO(file_bytes))
        texts = []

        for page in reader.pages[:20]:
            try:
                texts.append(page.extract_text() or "")
            except Exception:
                pass

        return "\n".join(texts)[:8000]

    except Exception as e:
        logger.warning(f"PDF extraction failed: {e}")
        return ""


# ─────────────────────────────────────────────────────────────
# POST /api/company-profile
# ─────────────────────────────────────────────────────────────

@router.post("/company-profile")
async def save_company_profile(
    company_data: str = Form(...),
    deck: UploadFile = File(None),
    db: AsyncSession = Depends(get_db),
):
    try:
        profile_data = CompanyProfileCreate(**json.loads(company_data))

    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid company_data JSON: {e}"
        )

    deck_text = ""
    deck_filename = ""

    if deck and deck.filename:
        deck_filename = deck.filename
        file_bytes = await deck.read()

        if deck.filename.lower().endswith(".pdf"):
            deck_text = _extract_pdf_text(file_bytes)

            logger.info(
                f"Deck extracted: {len(deck_text)} chars from {deck_filename}"
            )

    company = await create_company_profile(
        db,
        profile_data,
        deck_text,
        deck_filename,
    )

    return {
        "id": company.id,
        "message": "Company profile saved.",
        "deck_extracted": len(deck_text) > 0,
        "deck_chars": len(deck_text),
    }


# ─────────────────────────────────────────────────────────────
# GET /api/company-profile/{id}
# ─────────────────────────────────────────────────────────────

@router.get("/company-profile/{profile_id}")
async def fetch_company_profile(
    profile_id: str,
    db: AsyncSession = Depends(get_db),
):
    cp = await get_company_profile(db, profile_id)

    if not cp:
        raise HTTPException(
            status_code=404,
            detail="Company profile not found."
        )

    return {
        "id": cp.id,
        "company_name": cp.company_name,
        "founded_year": cp.founded_year,
        "location": cp.location,
        "what_we_do": cp.what_we_do,
        "what_we_need": cp.what_we_need,
        "deck_filename": cp.deck_filename,
        "has_deck": bool(cp.deck_text),
    }


# ─────────────────────────────────────────────────────────────
# POST /api/search
# ─────────────────────────────────────────────────────────────

@router.post("/search", response_model=SearchResponse)
async def search_events(
    request: SearchRequest,
    db: AsyncSession = Depends(get_db),
):
    profile = request.profile
    profile_id = str(uuid.uuid4())

    logger.info(
        f"Search: {profile.company_name} | "
        f"industries={profile.target_industries} | "
        f"geo={profile.target_geographies}"
    )

    # ── Resolve company context ──────────────────────────

    company_ctx: CompanyContext | None = request.company_context

    if request.company_profile_id and not company_ctx:
        cp = await get_company_profile(db, request.company_profile_id)

        if cp:
            company_ctx = CompanyContext(
                company_name=cp.company_name,
                founded_year=cp.founded_year,
                location=cp.location,
                what_we_do=cp.what_we_do,
                what_we_need=cp.what_we_need,
                deck_text=cp.deck_text,
            )

            logger.info(
                f"Company context loaded: "
                f"{cp.company_name} "
                f"(deck: {len(cp.deck_text)} chars)"
            )

    # ── Step 1: DB filter ────────────────────────────────

    candidates = await get_candidate_events(
        db=db,
        geographies=profile.target_geographies,
        industries=profile.target_industries,
        date_from=profile.date_from,
        date_to=profile.date_to,
        min_attendees=profile.min_attendees or 0,
        limit=300,
    )

    if len(candidates) < 5:
        logger.warning(
            f"Only {len(candidates)} candidates — running seed ingestion..."
        )

        await run_seed_only()

        candidates = await get_candidate_events(
            db=db,
            geographies=profile.target_geographies,
            industries=profile.target_industries,
            date_from=profile.date_from,
            date_to=profile.date_to,
            min_attendees=0,
            limit=300,
        )

    # Hard date filter
    candidates = [
        event for event in candidates
        if _within_requested_dates(
            event,
            profile.date_from,
            profile.date_to,
        )
    ]

    if not candidates:
        logger.info("No candidates found inside the requested date range.")

        _last_results[profile_id] = []

        return SearchResponse(
            profile_id=profile_id,
            company_name=profile.company_name,
            total_found=0,
            events=[],
            generated_at=datetime.utcnow().isoformat() + "Z",
        )

    logger.info(f"Candidates: {len(candidates)}")

    # ── Step 2: Semantic search (optional) ───────────────

    cosine_scores: dict = {}

    if settings.enable_semantic_search:
        try:
            from relevance.embedder import (
                build_profile_text,
                search_similar,
                add_events_to_index,
                get_index,
            )

            profile_text = build_profile_text(profile)

            idx = get_index()

            if idx.ntotal == 0:
                add_events_to_index(candidates)

            similar = search_similar(profile_text, top_k=100)

            cosine_scores = {
                r["id"]: r["cosine_score"]
                for r in similar
            }

        except Exception as e:
            logger.warning(
                f"Semantic search error: {e} — falling back to rules only"
            )

    # ── Step 3: Hybrid scoring ───────────────────────────

    scored = score_candidates(
        candidates,
        profile,
        cosine_scores,
    )

    top = scored[:settings.top_k_for_llm]

    top_events = [e for e, _, _, _ in top]

    pre_scores = {
        e.id: s
        for e, s, _, _ in top
    }

    pre_tiers = {
        e.id: t
        for e, _, t, _ in top
    }

    pre_details = {
        e.id: d
        for e, _, _, d in top
    }

    # ── Step 4: Groq ranking ─────────────────────────────

    ranked = await rank_with_groq(
        events=top_events,
        profile=profile,
        pre_scores=pre_scores,
        pre_tiers=pre_tiers,
        pre_details=pre_details,
        company_ctx=company_ctx,
    )

    ranked.sort(key=lambda r: -r.relevance_score)

    ranked = _apply_result_mix(ranked)

    _last_results[profile_id] = ranked

    go_n = sum(1 for r in ranked if r.fit_verdict == "GO")
    con_n = sum(1 for r in ranked if r.fit_verdict == "CONSIDER")
    skip_n = sum(1 for r in ranked if r.fit_verdict == "SKIP")

    logger.info(
        f"Search done: {len(ranked)} results | "
        f"GO={go_n} CONSIDER={con_n} SKIP={skip_n}"
    )

    return SearchResponse(
        profile_id=profile_id,
        company_name=profile.company_name,
        total_found=len(ranked),
        events=[r.model_dump() for r in ranked],
        generated_at=datetime.utcnow().isoformat() + "Z",
    )




@router.post("/events/upload-csv")
async def upload_events_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload CSV and permanently upsert rows into DATABASE_URL DB with dedup by hash.

    Supported headers include: id,name,start_date,end_date,venue,city,country,description,related_industries,website,source_url
    """
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded CSV is empty")

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    normalized_headers = {_norm(h).lower() for h in (reader.fieldnames or []) if h}
    if "name" not in normalized_headers:
        raise HTTPException(status_code=400, detail="Missing required columns: name")

    parsed: list[EventCreate] = []
    errors: list[str] = []
    for idx, row in enumerate(reader, start=2):
        try:
            parsed.append(_parse_csv_event_row(row, idx))
        except ValueError as exc:
            errors.append(str(exc))

    if not parsed:
        raise HTTPException(status_code=400, detail={"message": "No valid rows in CSV", "errors": errors[:20]})

    inserted, skipped = await batch_upsert_events(db, parsed, skip_past=False)
    total = await count_events(db)

    return {
        "message": "CSV processed and persisted to DATABASE_URL.",
        "filename": file.filename,
        "rows_read": len(parsed) + len(errors),
        "valid_rows": len(parsed),
        "inserted": inserted,
        "duplicates_or_skipped": max(0, len(parsed) - inserted) + skipped,
        "invalid_rows": len(errors),
        "errors_preview": errors[:20],
        "total_events_in_db": total,
    }


# ─────────────────────────────────────────────────────────────
# GET /api/events
# ─────────────────────────────────────────────────────────────

@router.get("/events")
async def list_events(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    all_evs = await get_all_events(db, limit=limit * page)

    start = (page - 1) * limit

    total = await count_events(db)

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "events": [
            {
                "id": e.id,
                "name": e.name,
                "start_date": e.start_date,
                "city": e.city,
                "country": e.country,
                "est_attendees": e.est_attendees,
                "category": e.category,
                "source_platform": e.source_platform,
                "registration_url": e.registration_url,
            }
            for e in all_evs[start:start + limit]
        ],
    }


# ─────────────────────────────────────────────────────────────
# GET /api/events/{id}
# ─────────────────────────────────────────────────────────────

@router.get("/events/{event_id}")
async def get_event(
    event_id: str,
    db: AsyncSession = Depends(get_db),
):
    event = await get_event_by_id(db, event_id)

    if not event:
        raise HTTPException(
            status_code=404,
            detail="Event not found"
        )

    return {
        "id": event.id,
        "name": event.name,
        "description": event.description,
        "start_date": event.start_date,
        "end_date": event.end_date,
        "venue_name": event.venue_name,
        "address": event.address,
        "city": event.city,
        "country": event.country,
        "est_attendees": event.est_attendees,
        "vip_count": getattr(event, "vip_count", 0),
        "category": event.category,
        "industry_tags": event.industry_tags,
        "audience_personas": event.audience_personas,
        "price_description": event.price_description,
        "registration_url": event.registration_url,
        "sponsors": event.sponsors,
        "speakers_url": event.speakers_url,
        "agenda_url": event.agenda_url,
        "source_platform": event.source_platform,
        "source_url": event.source_url,
        "ingested_at": (
            event.ingested_at.isoformat()
            if event.ingested_at else None
        ),
    }


# ─────────────────────────────────────────────────────────────
# GET /api/stats
# ─────────────────────────────────────────────────────────────

@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    total = await count_events(db)

    index_size = 0

    if settings.enable_semantic_search:
        try:
            from relevance.embedder import get_index

            index_size = get_index().ntotal

        except Exception:
            pass

    return {
        "total_events_in_db": total,
        "faiss_vectors": index_size,
        "groq_enabled": bool(settings.groq_api_key),

        # Added from code 2
        "resend_enabled": bool(settings.resend_api_key),

        "apis_configured": {
            "ticketmaster": bool(settings.ticketmaster_key),
            "eventbrite": bool(settings.eventbrite_token),
            "meetup": True,
            "luma": bool(settings.luma_api_key),
        },
    }


# ─────────────────────────────────────────────────────────────
# POST /api/refresh
# ─────────────────────────────────────────────────────────────

@router.post("/refresh")
async def refresh_events(background_tasks: BackgroundTasks):
    """
    Trigger a full event refresh in the background.

    Returns immediately; check /api/stats for updated count.

    Also used by GitHub Actions / cron-job.org
    to keep service alive.
    """
    background_tasks.add_task(_do_refresh)

    return {
        "message": "Refresh started. Poll /api/stats for progress."
    }


async def _do_refresh():
    logger.info("Manual refresh triggered.")

    try:
        stats = await run_ingestion()

        logger.info(
            f"Manual refresh done — "
            f"fetched={stats['total_fetched']} "
            f"inserted={stats['total_inserted']} "
            f"total_in_db={stats['total_in_db']}"
        )

    except Exception as e:
        logger.error(f"Manual refresh error: {e}")


# ─────────────────────────────────────────────────────────────
# Seed 10Times Protection
# ─────────────────────────────────────────────────────────────

def _require_seed_token(x_seed_token: str | None) -> None:
    if not settings.seed_admin_token:
        raise HTTPException(
            status_code=503,
            detail="SEED_ADMIN_TOKEN is not configured on the backend service.",
        )

    if x_seed_token != settings.seed_admin_token:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing X-Seed-Token header."
        )




@router.post("/seed-eventseye")
async def seed_eventseye_events(
    x_seed_token: str | None = Header(default=None),
):
    """Protected manual EventsEye seed run (writes to configured DATABASE_URL DB)."""
    _require_seed_token(x_seed_token)
    result = await run_eventseye_seed()
    return {"message": "EventsEye seed finished.", "result": result}


# ─────────────────────────────────────────────────────────────
# POST /api/seed-10times
# ─────────────────────────────────────────────────────────────

@router.post("/seed-10times")
async def seed_10times_events(
    background_tasks: BackgroundTasks,
    limit_events: int = Query(1000, ge=1, le=2000),
    max_pages_per_listing: int = Query(10, ge=1, le=50),
    concurrency: int = Query(1, ge=1, le=3),
    delay_seconds: float = Query(3.0, ge=0.0, le=30.0),
    timeout_seconds: float = Query(25.0, ge=1.0, le=60.0),
    dry_run: bool = Query(False),
    x_seed_token: str | None = Header(default=None),
):
    _require_seed_token(x_seed_token)

    if _seed_10times_status["running"]:
        raise HTTPException(
            status_code=409,
            detail="A 10times seed job is already running."
        )

    config = CrawlConfig(
        max_pages_per_listing=max_pages_per_listing,
        limit_events=limit_events,
        concurrency=concurrency,
        delay_seconds=delay_seconds,
        timeout_seconds=timeout_seconds,
        dry_run=dry_run,
    )

    _seed_10times_status.update({
        "running": True,
        "started_at": datetime.utcnow().isoformat() + "Z",
        "last_error": None,
        "requested_config": {
            "limit_events": limit_events,
            "max_pages_per_listing": max_pages_per_listing,
            "concurrency": concurrency,
            "delay_seconds": delay_seconds,
            "timeout_seconds": timeout_seconds,
            "dry_run": dry_run,
        },
    })

    background_tasks.add_task(_do_seed_10times, config)

    return {
        "message": "10times seed started. Check /api/seed-10times/status.",
        "requested_config": _seed_10times_status["requested_config"],
    }


# ─────────────────────────────────────────────────────────────
# GET /api/seed-10times/status
# ─────────────────────────────────────────────────────────────

@router.get("/seed-10times/status")
async def get_seed_10times_status(
    x_seed_token: str | None = Header(default=None)
):
    _require_seed_token(x_seed_token)

    return _seed_10times_status




@router.post("/seed-conferencealerts")
async def seed_conferencealerts_events(
    background_tasks: BackgroundTasks,
    limit_events: int = Query(1000, ge=1, le=5000),
    dry_run: bool = Query(False),
    x_seed_token: str | None = Header(default=None),
):
    _require_seed_token(x_seed_token)

    if _seed_conferencealerts_status["running"]:
        raise HTTPException(status_code=409, detail="A conferencealerts seed job is already running.")

    config = ConferenceAlertsSeedConfig(limit_events=limit_events, dry_run=dry_run)
    _seed_conferencealerts_status.update({
        "running": True,
        "started_at": datetime.utcnow().isoformat() + "Z",
        "last_error": None,
        "requested_config": {"limit_events": limit_events, "dry_run": dry_run},
    })

    background_tasks.add_task(_do_seed_conferencealerts, config)
    return {
        "message": "ConferenceAlerts seed started. Check /api/seed-conferencealerts/status.",
        "requested_config": _seed_conferencealerts_status["requested_config"],
    }


@router.get("/seed-conferencealerts/status")
async def get_seed_conferencealerts_status(x_seed_token: str | None = Header(default=None)):
    _require_seed_token(x_seed_token)
    return _seed_conferencealerts_status


async def _do_seed_conferencealerts(config: ConferenceAlertsSeedConfig):
    logger.info("Background conferencealerts seed started...")
    try:
        result = await run_conferencealerts_seed(config)
        _seed_conferencealerts_status.update({
            "running": False,
            "finished_at": datetime.utcnow().isoformat() + "Z",
            "last_result": result,
            "last_error": None,
        })
    except Exception as exc:
        _seed_conferencealerts_status.update({
            "running": False,
            "finished_at": datetime.utcnow().isoformat() + "Z",
            "last_error": str(exc),
        })
        logger.exception(f"Background conferencealerts seed failed: {exc}")


async def _do_seed_10times(config: CrawlConfig):
    logger.info("Background 10times seed started...")

    try:
        result = await run_10times_seed(config)

        _seed_10times_status.update({
            "running": False,
            "finished_at": datetime.utcnow().isoformat() + "Z",
            "last_result": result,
            "last_error": None,
        })

        logger.info(f"Background 10times seed done: {result}")

    except Exception as exc:
        _seed_10times_status.update({
            "running": False,
            "finished_at": datetime.utcnow().isoformat() + "Z",
            "last_error": str(exc),
        })

        logger.exception(f"Background 10times seed failed: {exc}")


@router.post("/seed-global")
async def seed_all_global_sources(
    background_tasks: BackgroundTasks,
    limit_events_10times: int = Query(2000, ge=1, le=10000),
    max_pages_per_listing: int = Query(15, ge=1, le=60),
    concurrency: int = Query(2, ge=1, le=3),
    delay_seconds: float = Query(2.0, ge=0.0, le=30.0),
    timeout_seconds: float = Query(30.0, ge=1.0, le=90.0),
    limit_events_conferencealerts: int = Query(5000, ge=1, le=10000),
    dry_run: bool = Query(False),
    x_seed_token: str | None = Header(default=None),
):
    """Run 10Times + ConferenceAlerts + EventsEye seeding as one protected admin action."""
    _require_seed_token(x_seed_token)

    if _seed_global_status["running"]:
        raise HTTPException(status_code=409, detail="A global seed job is already running.")

    _seed_global_status.update({
        "running": True,
        "started_at": datetime.utcnow().isoformat() + "Z",
        "last_error": None,
        "requested_config": {
            "limit_events_10times": limit_events_10times,
            "max_pages_per_listing": max_pages_per_listing,
            "concurrency": concurrency,
            "delay_seconds": delay_seconds,
            "timeout_seconds": timeout_seconds,
            "limit_events_conferencealerts": limit_events_conferencealerts,
            "dry_run": dry_run,
        },
    })

    background_tasks.add_task(
        _do_seed_global,
        CrawlConfig(
            max_pages_per_listing=max_pages_per_listing,
            limit_events=limit_events_10times,
            concurrency=concurrency,
            delay_seconds=delay_seconds,
            timeout_seconds=timeout_seconds,
            dry_run=dry_run,
        ),
        ConferenceAlertsSeedConfig(limit_events=limit_events_conferencealerts, dry_run=dry_run),
        dry_run,
    )

    return {
        "message": "Global seed started. Check /api/seed-global/status.",
        "requested_config": _seed_global_status["requested_config"],
    }


@router.get("/seed-global/status")
async def get_seed_global_status(x_seed_token: str | None = Header(default=None)):
    _require_seed_token(x_seed_token)
    return _seed_global_status


async def _do_seed_global(
    times_config: CrawlConfig,
    conferencealerts_config: ConferenceAlertsSeedConfig,
    dry_run: bool,
):
    logger.info("Background global seed started...")
    started_at = datetime.utcnow().isoformat() + "Z"
    try:
        ten_times = await run_10times_seed(times_config)
        conferencealerts = await run_conferencealerts_seed(conferencealerts_config)
        eventseye = await run_eventseye_seed(dry_run=dry_run)

        _seed_global_status.update({
            "running": False,
            "finished_at": datetime.utcnow().isoformat() + "Z",
            "last_error": None,
            "last_result": {
                "started_at": started_at,
                "10times": ten_times,
                "conferencealerts": conferencealerts,
                "eventseye": eventseye,
            },
        })
        logger.info(f"Background global seed done: {_seed_global_status['last_result']}")
    except Exception as exc:
        _seed_global_status.update({
            "running": False,
            "finished_at": datetime.utcnow().isoformat() + "Z",
            "last_error": str(exc),
        })
        logger.exception(f"Background global seed failed: {exc}")
