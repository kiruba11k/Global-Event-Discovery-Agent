"""
routes_events.py — SEARCH endpoint wired to real-time pipeline.

Key change: POST /api/search now calls fetch_realtime_candidates() which:
  1. Fires SerpAPI google_events + Ticketmaster + Eventbrite + PredictHQ in parallel
  2. Upserts all new events to DB
  3. Queries DB (now including newly stored real-time events)
  4. Returns combined candidates for scoring

All other routes (upload-csv, stats, seeding, etc.) are unchanged.
"""

import csv
import hashlib
import io
import json
import uuid
from datetime import date, datetime
from typing import Iterable, Optional

from fastapi import (
    APIRouter, BackgroundTasks, Depends, File, Form, Header,
    HTTPException, Query, UploadFile,
)
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from db.crud import (
    batch_upsert_events, count_events,
    create_company_profile, get_all_events,
    get_candidate_events, get_company_profile, get_event_by_id,
)
from db.database import get_db
from ingestion.ingestion_manager import run_ingestion, run_seed_only
from ingestion.realtime_pipeline import fetch_realtime_candidates
from models.company_profile import CompanyProfileCreate
from models.event import EventCreate
from models.icp_profile import CompanyContext, SearchRequest, SearchResponse
from relevance.groq_ranker import rank_with_groq
from relevance.scorer import score_candidates
from scripts.seed_10times_global import CrawlConfig, run_10times_seed
from scripts.seed_conferencealerts_global import (
    ConferenceAlertsSeedConfig, run_conferencealerts_seed,
)
from scripts.seed_eventseye_global import run_eventseye_seed

router   = APIRouter()
settings = get_settings()

_last_results: dict  = {}
RESULT_LIMIT          = 7
GO_RESULT_COUNT       = 4
CONSIDER_RESULT_COUNT = 3

_seed_10times_status: dict = {"running": False, "last_result": None, "last_error": None}
_seed_conferencealerts_status: dict = {"running": False, "last_result": None, "last_error": None}
_seed_global_status: dict = {"running": False, "last_result": None, "last_error": None}


# ── Helpers ────────────────────────────────────────────────────────

def _parse_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d")
    except (TypeError, ValueError):
        return None


def _within_dates(event, date_from, date_to) -> bool:
    start = _parse_date(getattr(event, "start_date", None))
    if not start:
        return False
    if date_from and start < _parse_date(date_from):
        return False
    if date_to   and start > _parse_date(date_to):
        return False
    return True


def _apply_result_mix(ranked: Iterable) -> list:
    all_ranked      = list(ranked)
    go_events       = [r for r in all_ranked if r.fit_verdict == "GO"]
    consider_events = [r for r in all_ranked if r.fit_verdict == "CONSIDER"]
    selected_go     = go_events[:GO_RESULT_COUNT]
    remaining       = RESULT_LIMIT - len(selected_go)
    return selected_go + consider_events[:remaining]


# ── CSV helpers (unchanged) ────────────────────────────────────────

def _norm(value: str | None) -> str:
    return (value or "").strip()

def _csv_value(row: dict, *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if _norm(value):
            return _norm(value)
    return ""

def _split_city_country(raw: str) -> tuple[str, str]:
    cleaned = _norm(raw)
    if not cleaned:
        return "", ""
    if "(" in cleaned and ")" in cleaned:
        city    = cleaned.split("(", 1)[0].strip(" -,")
        country = cleaned.split("(", 1)[1].split(")", 1)[0].strip()
        return city, country
    if "," in cleaned:
        city, country = [p.strip() for p in cleaned.split(",", 1)]
        return city, country
    return cleaned, ""

def _csv_dedup_hash(name, start_date, city, country):
    raw = "|".join([_norm(name).lower(), _norm(start_date), _norm(city).lower(), _norm(country).lower()])
    return hashlib.sha1(raw.encode()).hexdigest()

def _csv_int(row, *keys, default=0):
    value = _csv_value(row, *keys)
    if not value: return default
    try: return int(float(value))
    except: return default

def _csv_float(row, *keys, default=0.0):
    value = _csv_value(row, *keys)
    if not value: return default
    try: return float(value)
    except: return default

def _csv_bool(row, *keys, default=False):
    value = _csv_value(row, *keys).lower()
    if not value: return default
    return value in {"1", "true", "yes", "y"}

def _parse_csv_event_row(row: dict, row_number: int) -> EventCreate:
    normalized_row = {_norm(str(k)).lower().lstrip("\ufeff"): v for k, v in row.items() if k is not None}
    name       = _csv_value(normalized_row, "name", "event_name", "title")
    start_date = _csv_value(normalized_row, "start_date", "start", "from_date")
    end_date   = _csv_value(normalized_row, "end_date", "end", "to_date")
    if not start_date and _parse_date(end_date): start_date = end_date
    if not name or not start_date: raise ValueError(f"row {row_number}: 'name' and 'start_date' required")
    if not _parse_date(start_date): raise ValueError(f"row {row_number}: invalid start_date '{start_date}'")
    event_id    = _csv_value(normalized_row, "id", "event_id") or str(uuid.uuid4())
    source_url  = _csv_value(normalized_row, "source_url", "source url", "url")
    website_url = _csv_value(normalized_row, "website", "website_url", "official_website",
                              "registration_url", "event_url", "event_link", "link")
    city    = _csv_value(normalized_row, "city")
    country = _csv_value(normalized_row, "country")
    event_cities = _csv_value(normalized_row, "event_cities", "event_city", "location")
    if (not city or not country) and event_cities:
        fallback_city, fallback_country = _split_city_country(event_cities)
        city    = city    or fallback_city
        country = country or fallback_country
    related_industries = _csv_value(normalized_row, "related_industries", "industry_tags", "industries", "industry")
    csv_source = _csv_value(normalized_row, "source", "source_platform")
    return EventCreate(
        id=event_id, dedup_hash=_csv_dedup_hash(name, start_date, city, country),
        source_platform=csv_source or "CSV_UPLOAD",
        source_url=source_url or website_url or f"https://example.com/event/{event_id}",
        name=name, description=_csv_value(normalized_row, "description", "summary"),
        short_summary=_csv_value(normalized_row, "short_summary"),
        edition_number=_csv_value(normalized_row, "edition_number", "edition"),
        industry_tags=related_industries, related_industries=related_industries,
        audience_personas=_csv_value(normalized_row, "audience_personas", "buyer_persona"),
        start_date=start_date, end_date=end_date or start_date,
        duration_days=_csv_int(normalized_row, "duration_days", default=1),
        venue_name=_csv_value(normalized_row, "venue", "event_venues", "venue_name"),
        event_venues=_csv_value(normalized_row, "event_venues", "venue"),
        event_cities=event_cities or f"{city}, {country}".strip(", "),
        address=_csv_value(normalized_row, "address"),
        city=city, country=country,
        is_virtual=_csv_bool(normalized_row, "is_virtual"),
        is_hybrid=_csv_bool(normalized_row, "is_hybrid"),
        est_attendees=_csv_int(normalized_row, "est_attendees", "estimated_attendees", "attendees"),
        category=_csv_value(normalized_row, "category"),
        ticket_price_usd=_csv_float(normalized_row, "ticket_price_usd", "price_usd"),
        price_description=_csv_value(normalized_row, "price_description", "pricing"),
        registration_url=website_url, website=website_url,
        sponsors=_csv_value(normalized_row, "sponsors"),
        speakers_url=_csv_value(normalized_row, "speakers_url"),
        agenda_url=_csv_value(normalized_row, "agenda_url"),
    )

def _extract_pdf_text(file_bytes: bytes) -> str:
    try:
        import pypdf, io as _io
        reader = pypdf.PdfReader(_io.BytesIO(file_bytes))
        texts  = [page.extract_text() or "" for page in reader.pages[:20]]
        return "\n".join(texts)[:8000]
    except Exception as exc:
        logger.warning(f"PDF extraction failed: {exc}")
        return ""


# ══════════════════════════════════════════════════════════════════════
# POST /api/company-profile
# ══════════════════════════════════════════════════════════════════════

@router.post("/company-profile")
async def save_company_profile(
    company_data: str = Form(...),
    deck: UploadFile = File(None),
    db: AsyncSession = Depends(get_db),
):
    try:
        profile_data = CompanyProfileCreate(**json.loads(company_data))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid company_data JSON: {exc}")
    deck_text, deck_filename = "", ""
    if deck and deck.filename:
        deck_filename = deck.filename
        file_bytes    = await deck.read()
        if deck.filename.lower().endswith(".pdf"):
            deck_text = _extract_pdf_text(file_bytes)
    company = await create_company_profile(db, profile_data, deck_text, deck_filename)
    return {"id": company.id, "message": "Company profile saved.",
            "deck_extracted": len(deck_text) > 0, "deck_chars": len(deck_text)}


@router.get("/company-profile/{profile_id}")
async def fetch_company_profile(profile_id: str, db: AsyncSession = Depends(get_db)):
    cp = await get_company_profile(db, profile_id)
    if not cp:
        raise HTTPException(status_code=404, detail="Company profile not found.")
    return {"id": cp.id, "company_name": cp.company_name, "founded_year": cp.founded_year,
            "location": cp.location, "what_we_do": cp.what_we_do, "what_we_need": cp.what_we_need,
            "deck_filename": cp.deck_filename, "has_deck": bool(cp.deck_text)}


# ══════════════════════════════════════════════════════════════════════
# POST /api/search  — REAL-TIME PIPELINE
# ══════════════════════════════════════════════════════════════════════

@router.post("/search", response_model=SearchResponse)
async def search_events(request: SearchRequest, db: AsyncSession = Depends(get_db)):
    profile    = request.profile
    profile_id = str(uuid.uuid4())
    deal_size_category = profile.avg_deal_size_category or "medium"

    logger.info(
        f"Search: '{profile.company_name}' | "
        f"industries={profile.target_industries[:2]} | "
        f"geo={profile.target_geographies[:2]} | "
        f"dates={profile.date_from}→{profile.date_to} | "
        f"deal={deal_size_category}"
    )

    # ── Resolve company context ────────────────────────────────────
    company_ctx: CompanyContext | None = request.company_context
    if request.company_profile_id and not company_ctx:
        cp = await get_company_profile(db, request.company_profile_id)
        if cp:
            company_ctx = CompanyContext(
                company_name  = cp.company_name,
                founded_year  = cp.founded_year,
                location      = cp.location,
                what_we_do    = cp.what_we_do,
                what_we_need  = cp.what_we_need,
                deck_text     = cp.deck_text,
            )

    # ── Step 1: Real-time pipeline ─────────────────────────────────
    # Fires SerpAPI + Ticketmaster + Eventbrite + PredictHQ in parallel,
    # upserts new events to DB, then queries DB for all candidates.
    candidates = await fetch_realtime_candidates(db, profile)

    # ── Step 2: DB-only fallback if real-time returned nothing ─────
    if len(candidates) < 5:
        total_in_db = await count_events(db)
        if total_in_db < 5:
            logger.warning("DB nearly empty — seeding curated events")
            await run_seed_only()

        # Wide DB query without industry filter
        today = date.today().isoformat()
        from sqlalchemy import select as _select
        from models.event import EventORM as _ORM
        stmt = _select(_ORM).where(
            _ORM.start_date >= (profile.date_from or today),
            _ORM.start_date <= (profile.date_to   or "2030-12-31"),
        )
        r = await db.execute(stmt.limit(500))
        candidates = list(r.scalars().all())
        logger.info(f"Wide fallback: {len(candidates)} candidates")

    # ── Step 3: Date filter ────────────────────────────────────────
    if profile.date_from or profile.date_to:
        candidates = [
            e for e in candidates
            if _within_dates(e, profile.date_from, profile.date_to)
        ]

    if not candidates:
        logger.info("No candidates after date filter.")
        _last_results[profile_id] = []
        return SearchResponse(
            profile_id=profile_id, company_name=profile.company_name,
            total_found=0, events=[],
            generated_at=datetime.utcnow().isoformat() + "Z",
        )

    logger.info(f"Candidates for scoring: {len(candidates)}")

    # ── Step 4: Optional semantic scoring ─────────────────────────
    cosine_scores: dict = {}
    if settings.enable_semantic_search:
        try:
            from relevance.embedder import (
                add_events_to_index, build_profile_text,
                get_index, search_similar,
            )
            profile_text = build_profile_text(profile)
            idx = get_index()
            if idx.ntotal == 0:
                add_events_to_index(candidates)
            similar      = search_similar(profile_text, top_k=100)
            cosine_scores = {r["id"]: r["cosine_score"] for r in similar}
        except Exception as exc:
            logger.warning(f"Semantic search error: {exc}")

    # ── Step 5: Rule-based scoring ─────────────────────────────────
    scored      = score_candidates(candidates, profile, cosine_scores)
    top         = scored[:settings.top_k_for_llm]
    top_events  = [e for e, _, _, _ in top]
    pre_scores  = {e.id: s for e, s, _, _ in top}
    pre_tiers   = {e.id: t for e, _, t, _ in top}
    pre_details = {e.id: d for e, _, _, d in top}

    # ── Step 6: SerpAPI enrichment (fills attendees, price, links) ─
    enrichments: dict = {}
    if settings.serpapi_key:
        try:
            from enrichment.serp_enricher import enrich_events_batch
            enrichments = await enrich_events_batch(
                events      = top_events,
                serpapi_key = settings.serpapi_key,
                max_enrich  = min(len(top_events), settings.top_k_for_llm),
            )
            if enrichments:
                att_n  = sum(1 for d in enrichments.values() if d.get("est_attendees"))
                prc_n  = sum(1 for d in enrichments.values() if d.get("price_description"))
                link_n = sum(1 for d in enrichments.values() if d.get("event_link"))
                per_n  = sum(1 for d in enrichments.values() if d.get("audience_personas"))
                logger.info(
                    f"SerpAPI enriched {len(enrichments)} events — "
                    f"att={att_n} prc={prc_n} link={link_n} personas={per_n}"
                )
        except Exception as exc:
            logger.warning(f"SerpAPI enrichment error (non-fatal): {exc}")

    # ── Step 7: Groq LLM ranking ───────────────────────────────────
    ranked = await rank_with_groq(
        events             = top_events,
        profile            = profile,
        pre_scores         = pre_scores,
        pre_tiers          = pre_tiers,
        pre_details        = pre_details,
        company_ctx        = company_ctx,
        enrichments        = enrichments,
        deal_size_category = deal_size_category,
    )

    ranked.sort(key=lambda r: -r.relevance_score)

    # ── Step 8: Enforce 4 GO + 3 CONSIDER ─────────────────────────
    ranked = _apply_result_mix(ranked)
    _last_results[profile_id] = ranked

    go_n  = sum(1 for r in ranked if r.fit_verdict == "GO")
    con_n = sum(1 for r in ranked if r.fit_verdict == "CONSIDER")
    enr_n = sum(1 for r in ranked if getattr(r, "serpapi_enriched", False))
    logger.info(
        f"Search done: {len(ranked)} results | GO={go_n} CONSIDER={con_n} | enriched={enr_n}"
    )

    return SearchResponse(
        profile_id   = profile_id,
        company_name = profile.company_name,
        total_found  = len(ranked),
        events       = [r.model_dump() for r in ranked],
        generated_at = datetime.utcnow().isoformat() + "Z",
    )


# ══════════════════════════════════════════════════════════════════════
# POST /api/events/upload-csv
# ══════════════════════════════════════════════════════════════════════

@router.post("/events/upload-csv")
async def upload_events_csv(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
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
        raise HTTPException(status_code=400, detail="Missing required column: name")

    parsed: list[EventCreate] = []
    errors: list[str] = []
    for idx, row in enumerate(reader, start=2):
        try:
            parsed.append(_parse_csv_event_row(row, idx))
        except ValueError as exc:
            errors.append(str(exc))

    if not parsed:
        raise HTTPException(status_code=400, detail={"message": "No valid rows", "errors": errors[:20]})

    inserted, skipped = await batch_upsert_events(db, parsed, skip_past=False)
    total = await count_events(db)
    return {
        "message": "CSV processed.", "filename": file.filename,
        "rows_read": len(parsed) + len(errors), "valid_rows": len(parsed),
        "inserted": inserted,
        "duplicates_or_skipped": max(0, len(parsed) - inserted) + skipped,
        "invalid_rows": len(errors), "errors_preview": errors[:20],
        "total_events_in_db": total,
    }


# ══════════════════════════════════════════════════════════════════════
# GET /api/events
# ══════════════════════════════════════════════════════════════════════

@router.get("/events")
async def list_events(
    page:  int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    all_evs = await get_all_events(db, limit=limit * page)
    start   = (page - 1) * limit
    total   = await count_events(db)
    return {
        "total": total, "page": page, "limit": limit,
        "events": [
            {
                "id":              e.id,
                "name":            e.name,
                "start_date":      e.start_date,
                "city":            getattr(e, "event_cities", "") or e.city or "",
                "country":         e.country,
                "est_attendees":   e.est_attendees,
                "category":        e.category,
                "source_platform": e.source_platform,
                "registration_url": getattr(e, "website", "") or e.registration_url or e.source_url or "",
            }
            for e in all_evs[start: start + limit]
        ],
    }


@router.get("/events/{event_id}")
async def get_event(event_id: str, db: AsyncSession = Depends(get_db)):
    event = await get_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return {
        "id": event.id, "name": event.name, "description": event.description,
        "start_date": event.start_date, "end_date": event.end_date,
        "venue": getattr(event, "event_venues", "") or event.venue_name or "",
        "city": getattr(event, "event_cities", "") or event.city or "",
        "country": event.country, "est_attendees": event.est_attendees,
        "category": event.category,
        "industry": getattr(event, "related_industries", "") or event.industry_tags or "",
        "audience_personas": event.audience_personas,
        "price_description": event.price_description,
        "website": getattr(event, "website", "") or event.registration_url or event.source_url or "",
        "sponsors": event.sponsors, "source_platform": event.source_platform,
        "source_url": event.source_url,
        "ingested_at": event.ingested_at.isoformat() if event.ingested_at else None,
    }


# ══════════════════════════════════════════════════════════════════════
# GET /api/stats
# ══════════════════════════════════════════════════════════════════════

@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    total = await count_events(db)
    try:
        from db.crud import count_by_source
        by_source = await count_by_source(db)
    except Exception:
        by_source = {}

    index_size = 0
    if settings.enable_semantic_search:
        try:
            from relevance.embedder import get_index
            index_size = get_index().ntotal
        except Exception:
            pass

    return {
        "total_events_in_db": total,
        "events_by_source":   by_source,
        "faiss_vectors":      index_size,
        "groq_enabled":       bool(settings.groq_api_key),
        "serpapi_enabled":    bool(settings.serpapi_key),
        "resend_enabled":     bool(settings.resend_api_key),
        # Real-time API status
        "realtime_apis": {
            "serpapi_google_events": bool(settings.serpapi_key),
            "ticketmaster":          bool(settings.ticketmaster_key),
            "eventbrite":            bool(settings.eventbrite_token),
            "predicthq":             bool(getattr(settings, "predicthq_key", "")),
            "luma":                  bool(settings.luma_api_key),
        },
        "apis_configured": {
            "ticketmaster": bool(settings.ticketmaster_key),
            "eventbrite":   bool(settings.eventbrite_token),
            "meetup":       True,
            "luma":         bool(settings.luma_api_key),
        },
    }


# ══════════════════════════════════════════════════════════════════════
# POST /api/refresh
# ══════════════════════════════════════════════════════════════════════

@router.post("/refresh")
async def refresh_events(background_tasks: BackgroundTasks):
    background_tasks.add_task(_do_refresh)
    return {"message": "Refresh started. Poll /api/stats for progress."}

async def _do_refresh():
    logger.info("Manual /api/refresh triggered.")
    try:
        stats = await run_ingestion()
        logger.info(f"Refresh done — fetched={stats['total_fetched']} inserted={stats['total_inserted']}")
    except Exception as exc:
        logger.error(f"Manual refresh error: {exc}")


# ══════════════════════════════════════════════════════════════════════
# Seed endpoints (unchanged)
# ══════════════════════════════════════════════════════════════════════

def _require_seed_token(x_seed_token: str | None) -> None:
    if not settings.seed_admin_token:
        raise HTTPException(status_code=503, detail="SEED_ADMIN_TOKEN not configured.")
    if x_seed_token != settings.seed_admin_token:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Seed-Token header.")

@router.post("/seed-eventseye")
async def seed_eventseye_events(x_seed_token: str | None = Header(default=None)):
    _require_seed_token(x_seed_token)
    result = await run_eventseye_seed()
    return {"message": "EventsEye seed finished.", "result": result}

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
        raise HTTPException(status_code=409, detail="A 10times seed job is already running.")
    config = CrawlConfig(max_pages_per_listing=max_pages_per_listing, limit_events=limit_events,
                         concurrency=concurrency, delay_seconds=delay_seconds,
                         timeout_seconds=timeout_seconds, dry_run=dry_run)
    _seed_10times_status.update({"running": True, "started_at": datetime.utcnow().isoformat() + "Z", "last_error": None})
    background_tasks.add_task(_do_seed_10times, config)
    return {"message": "10times seed started."}

@router.get("/seed-10times/status")
async def get_seed_10times_status(x_seed_token: str | None = Header(default=None)):
    _require_seed_token(x_seed_token)
    return _seed_10times_status

async def _do_seed_10times(config):
    try:
        result = await run_10times_seed(config)
        _seed_10times_status.update({"running": False, "last_result": result, "last_error": None,
                                      "finished_at": datetime.utcnow().isoformat() + "Z"})
    except Exception as exc:
        _seed_10times_status.update({"running": False, "last_error": str(exc),
                                      "finished_at": datetime.utcnow().isoformat() + "Z"})

@router.post("/seed-conferencealerts")
async def seed_conferencealerts_events(
    background_tasks: BackgroundTasks,
    limit_events: int = Query(1000, ge=1, le=5000),
    dry_run: bool = Query(False),
    x_seed_token: str | None = Header(default=None),
):
    _require_seed_token(x_seed_token)
    if _seed_conferencealerts_status["running"]:
        raise HTTPException(status_code=409, detail="Already running.")
    config = ConferenceAlertsSeedConfig(limit_events=limit_events, dry_run=dry_run)
    _seed_conferencealerts_status.update({"running": True, "started_at": datetime.utcnow().isoformat() + "Z", "last_error": None})
    background_tasks.add_task(_do_seed_conferencealerts, config)
    return {"message": "ConferenceAlerts seed started."}

@router.get("/seed-conferencealerts/status")
async def get_seed_conferencealerts_status(x_seed_token: str | None = Header(default=None)):
    _require_seed_token(x_seed_token)
    return _seed_conferencealerts_status

async def _do_seed_conferencealerts(config):
    try:
        result = await run_conferencealerts_seed(config)
        _seed_conferencealerts_status.update({"running": False, "last_result": result, "last_error": None,
                                               "finished_at": datetime.utcnow().isoformat() + "Z"})
    except Exception as exc:
        _seed_conferencealerts_status.update({"running": False, "last_error": str(exc),
                                               "finished_at": datetime.utcnow().isoformat() + "Z"})

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
    _require_seed_token(x_seed_token)
    if _seed_global_status["running"]:
        raise HTTPException(status_code=409, detail="A global seed job is already running.")
    _seed_global_status.update({"running": True, "started_at": datetime.utcnow().isoformat() + "Z", "last_error": None})
    background_tasks.add_task(
        _do_seed_global,
        CrawlConfig(max_pages_per_listing=max_pages_per_listing, limit_events=limit_events_10times,
                    concurrency=concurrency, delay_seconds=delay_seconds,
                    timeout_seconds=timeout_seconds, dry_run=dry_run),
        ConferenceAlertsSeedConfig(limit_events=limit_events_conferencealerts, dry_run=dry_run),
        dry_run,
    )
    return {"message": "Global seed started."}

@router.get("/seed-global/status")
async def get_seed_global_status(x_seed_token: str | None = Header(default=None)):
    _require_seed_token(x_seed_token)
    return _seed_global_status

async def _do_seed_global(times_config, ca_config, dry_run):
    started = datetime.utcnow().isoformat() + "Z"
    try:
        ten_times        = await run_10times_seed(times_config)
        conferencealerts = await run_conferencealerts_seed(ca_config)
        eventseye        = await run_eventseye_seed(dry_run=dry_run)
        _seed_global_status.update({
            "running": False, "finished_at": datetime.utcnow().isoformat() + "Z",
            "last_error": None,
            "last_result": {"started_at": started, "10times": ten_times,
                            "conferencealerts": conferencealerts, "eventseye": eventseye},
        })
    except Exception as exc:
        _seed_global_status.update({"running": False, "finished_at": datetime.utcnow().isoformat() + "Z",
                                     "last_error": str(exc)})
        logger.exception(f"Global seed failed: {exc}")
