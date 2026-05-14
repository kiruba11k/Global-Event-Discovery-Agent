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


def _within_requested_dates(event, date_from, date_to) -> bool:
    event_start = _parse_date(getattr(event, "start_date", None))
    if not event_start:
        return False
    if date_from and event_start < _parse_date(date_from):
        return False
    if date_to   and event_start > _parse_date(date_to):
        return False
    return True


def _apply_result_mix(ranked: Iterable) -> list:
    """
    Return up to RESULT_LIMIT events, GO first then CONSIDER.
    SKIP events are excluded.
    Groq's actual verdict is preserved — we never force-assign GO/CONSIDER.
    """
    all_ranked  = list(ranked)
    go_events       = [r for r in all_ranked if r.fit_verdict == "GO"]
    consider_events = [r for r in all_ranked if r.fit_verdict == "CONSIDER"]
 
    # Fill with GO first, then CONSIDER
    selected_go      = go_events[:GO_RESULT_COUNT]
    remaining_slots  = RESULT_LIMIT - len(selected_go)
    selected_consider= consider_events[:remaining_slots]
 
    return selected_go + selected_consider


# ─────────────────────────────────────────────────────────────
# PDF extraction
# ─────────────────────────────────────────────────────────────



def _norm(value: str | None) -> str:
    return (value or "").strip()
 
def _csv_value(row: dict, *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if _norm(value):
            return _norm(value)
    return ""
 
def _split_city_country(raw_location: str) -> tuple[str, str]:
    cleaned = _norm(raw_location)
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
 
def _csv_dedup_hash(name: str, start_date: str, city: str, country: str) -> str:
    raw = "|".join([_norm(name).lower(), _norm(start_date), _norm(city).lower(), _norm(country).lower()])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()
 
def _csv_int(row: dict, *keys: str, default: int = 0) -> int:
    value = _csv_value(row, *keys)
    if not value:
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default
 
def _csv_float(row: dict, *keys: str, default: float = 0.0) -> float:
    value = _csv_value(row, *keys)
    if not value:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
 
def _csv_bool(row: dict, *keys: str, default: bool = False) -> bool:
    value = _csv_value(row, *keys).lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "y"}
 
 
def _parse_csv_event_row(row: dict, row_number: int) -> EventCreate:
    normalized_row = {_norm(str(k)).lower().lstrip("\ufeff"): v for k, v in row.items() if k is not None}
 
    name       = _csv_value(normalized_row, "name", "event_name", "title")
    start_date = _csv_value(normalized_row, "start_date", "start", "from_date")
    end_date   = _csv_value(normalized_row, "end_date", "end", "to_date")
 
    if not start_date and _parse_date(end_date):
        start_date = end_date
 
    if not name or not start_date:
        raise ValueError(f"row {row_number}: 'name' and 'start_date' are required")
    if not _parse_date(start_date):
        raise ValueError(f"row {row_number}: invalid start_date '{start_date}'")
 
    event_id   = _csv_value(normalized_row, "id", "event_id") or str(uuid.uuid4())
    source_url = _csv_value(normalized_row, "source_url", "url")
 
    # ── Prefer "website" column for the official event URL ──────────
    # This becomes registration_url AND website so _get_link() can find it.
    website_url = _csv_value(normalized_row, "website", "registration_url", "event_url", "link")
 
    city        = _csv_value(normalized_row, "city")
    country     = _csv_value(normalized_row, "country")
    event_cities= _csv_value(normalized_row, "event_cities", "event_city", "location")
 
    if (not city or not country) and event_cities:
        fallback_city, fallback_country = _split_city_country(event_cities)
        city    = city    or fallback_city
        country = country or fallback_country
 
    related_industries = _csv_value(normalized_row, "related_industries", "industry_tags", "industries", "industry")
    csv_source         = _csv_value(normalized_row, "source", "source_platform")
 
    return EventCreate(
        id=event_id,
        dedup_hash=_csv_dedup_hash(name, start_date, city, country),
        source_platform=csv_source or "CSV_UPLOAD",
        # source_url: prefer actual URL, fall back to marker (not csv://)
        source_url=source_url or website_url or f"https://example.com/event/{event_id}",
        name=name,
        description=_csv_value(normalized_row, "description", "summary"),
        short_summary=_csv_value(normalized_row, "short_summary"),
        edition_number=_csv_value(normalized_row, "edition_number", "edition"),
        industry_tags=related_industries,
        related_industries=related_industries,
        audience_personas=_csv_value(normalized_row, "audience_personas", "buyer_persona", "personas"),
        start_date=start_date,
        end_date=end_date or start_date,
        duration_days=_csv_int(normalized_row, "duration_days", default=1),
        venue_name=_csv_value(normalized_row, "venue", "event_venues", "venue_name"),
        event_venues=_csv_value(normalized_row, "event_venues", "venue"),
        event_cities=event_cities or f"{city}, {country}".strip(", "),
        address=_csv_value(normalized_row, "address"),
        city=city,
        country=country,
        is_virtual=_csv_bool(normalized_row, "is_virtual"),
        is_hybrid=_csv_bool(normalized_row, "is_hybrid"),
        est_attendees=_csv_int(normalized_row, "est_attendees", "attendees", "expected_attendance"),
        category=_csv_value(normalized_row, "category"),
        ticket_price_usd=_csv_float(normalized_row, "ticket_price_usd", "price_usd"),
        price_description=_csv_value(normalized_row, "price_description", "pricing"),
        registration_url=website_url,   # official event URL
        website=website_url,            # stored in BOTH fields so _get_link() finds it
        sponsors=_csv_value(normalized_row, "sponsors"),
        speakers_url=_csv_value(normalized_row, "speakers_url"),
        agenda_url=_csv_value(normalized_row, "agenda_url"),
    )
 
def _extract_pdf_text(file_bytes: bytes) -> str:
    try:
        import pypdf, io as _io
        reader = pypdf.PdfReader(_io.BytesIO(file_bytes))
        texts  = []
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
        raise HTTPException(status_code=422, detail=f"Invalid company_data JSON: {e}")
 
    deck_text, deck_filename = "", ""
    if deck and deck.filename:
        deck_filename = deck.filename
        file_bytes    = await deck.read()
        if deck.filename.lower().endswith(".pdf"):
            deck_text = _extract_pdf_text(file_bytes)
 
    company = await create_company_profile(db, profile_data, deck_text, deck_filename)
    return {
        "id":             company.id,
        "message":        "Company profile saved.",
        "deck_extracted": len(deck_text) > 0,
        "deck_chars":     len(deck_text),
    }

# ─────────────────────────────────────────────────────────────
# GET /api/company-profile/{id}
# ─────────────────────────────────────────────────────────────

@router.get("/company-profile/{profile_id}")
async def fetch_company_profile(profile_id: str, db: AsyncSession = Depends(get_db)):
    cp = await get_company_profile(db, profile_id)
    if not cp:
        raise HTTPException(status_code=404, detail="Company profile not found.")
    return {
        "id": cp.id, "company_name": cp.company_name, "founded_year": cp.founded_year,
        "location": cp.location, "what_we_do": cp.what_we_do, "what_we_need": cp.what_we_need,
        "deck_filename": cp.deck_filename, "has_deck": bool(cp.deck_text),
    }
 


# ─────────────────────────────────────────────────────────────
# POST /api/search
# ─────────────────────────────────────────────────────────────

@router.post("/search", response_model=SearchResponse)
async def search_events(request: SearchRequest, db: AsyncSession = Depends(get_db)):
    profile    = request.profile
    profile_id = str(uuid.uuid4())
 
    # FIX 3: read avg_deal_size_category from profile (now in ICPProfile model)
    deal_size_category = profile.avg_deal_size_category or "medium"
 
    logger.info(
        f"Search: {profile.company_name} | "
        f"industries={profile.target_industries} | "
        f"geo={profile.target_geographies} | "
        f"deal_size={deal_size_category}"
    )
 
    # ── Resolve company context ──────────────────────────────────────
    company_ctx: CompanyContext | None = request.company_context
    if request.company_profile_id and not company_ctx:
        cp = await get_company_profile(db, request.company_profile_id)
        if cp:
            company_ctx = CompanyContext(
                company_name=cp.company_name, founded_year=cp.founded_year,
                location=cp.location, what_we_do=cp.what_we_do,
                what_we_need=cp.what_we_need, deck_text=cp.deck_text,
            )
 
    # ── Step 1: DB filter — searches city, country AND event_cities ──
    candidates = await get_candidate_events(
        db=db,
        geographies=profile.target_geographies,
        industries=profile.target_industries,
        date_from=profile.date_from,
        date_to=profile.date_to,
        min_attendees=0,   # don't pre-filter by attendees; SerpAPI fills gaps
        limit=300,
    )
 
    if len(candidates) < 5:
        logger.warning(f"Only {len(candidates)} candidates — running seed ingestion.")
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
    candidates = [e for e in candidates if _within_requested_dates(e, profile.date_from, profile.date_to)]
 
    if not candidates:
        logger.info("No candidates in requested date range.")
        _last_results[profile_id] = []
        return SearchResponse(
            profile_id=profile_id, company_name=profile.company_name,
            total_found=0, events=[],
            generated_at=datetime.utcnow().isoformat() + "Z",
        )
 
    logger.info(f"Candidates after date filter: {len(candidates)}")
 
    # ── Step 2: Semantic search (optional) ──────────────────────────
    cosine_scores: dict = {}
    if settings.enable_semantic_search:
        try:
            from relevance.embedder import build_profile_text, search_similar, add_events_to_index, get_index
            profile_text  = build_profile_text(profile)
            idx           = get_index()
            if idx.ntotal == 0:
                add_events_to_index(candidates)
            similar       = search_similar(profile_text, top_k=100)
            cosine_scores = {r["id"]: r["cosine_score"] for r in similar}
        except Exception as e:
            logger.warning(f"Semantic search error: {e}")
 
    # ── Step 3: Hybrid scoring ───────────────────────────────────────
    scored = score_candidates(candidates, profile, cosine_scores)
    top    = scored[:settings.top_k_for_llm]
 
    top_events  = [e for e, _, _, _ in top]
    pre_scores  = {e.id: s for e, s, _, _ in top}
    pre_tiers   = {e.id: t for e, _, t, _ in top}
    pre_details = {e.id: d for e, _, _, d in top}
 
    # ── Step 4: SerpAPI enrichment — FIX 2: correct import + function ─
    enrichments: dict = {}
    if settings.serpapi_key:
        try:
            from enrichment.serp_enricher import enrich_events_batch   # ← FIXED
            enrichments = await enrich_events_batch(
                events     = top_events,
                serpapi_key= settings.serpapi_key,
                max_enrich = 7,
            )
            if enrichments:
                filled_fields = sum(len(v) for v in enrichments.values())
                logger.info(f"SerpAPI enriched {len(enrichments)} events ({filled_fields} fields).")
        except Exception as e:
            logger.warning(f"SerpAPI enrichment error (non-fatal): {e}")
 
    # ── Step 5: Groq ranking ─────────────────────────────────────────
    ranked = await rank_with_groq(
        events=top_events, profile=profile,
        pre_scores=pre_scores, pre_tiers=pre_tiers, pre_details=pre_details,
        company_ctx=company_ctx, enrichments=enrichments,
        deal_size_category=deal_size_category,
    )
 
    ranked.sort(key=lambda r: -r.relevance_score)
 
    # FIX 1: use the fixed _apply_result_mix that respects Groq verdicts
    ranked = _apply_result_mix(ranked)
    _last_results[profile_id] = ranked
 
    go_n  = sum(1 for r in ranked if r.fit_verdict == "GO")
    con_n = sum(1 for r in ranked if r.fit_verdict == "CONSIDER")
    enr_n = sum(1 for r in ranked if getattr(r, "serpapi_enriched", False))
    logger.info(f"Search done: {len(ranked)} results | GO={go_n} CONSIDER={con_n} | SerpAPI-enriched={enr_n}")
 
    return SearchResponse(
        profile_id=profile_id, company_name=profile.company_name,
        total_found=len(ranked),
        events=[r.model_dump() for r in ranked],
        generated_at=datetime.utcnow().isoformat() + "Z",
    )




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
    errors: list[str]         = []
    for idx, row in enumerate(reader, start=2):
        try:
            parsed.append(_parse_csv_event_row(row, idx))
        except ValueError as exc:
            errors.append(str(exc))
 
    if not parsed:
        raise HTTPException(status_code=400, detail={"message": "No valid rows", "errors": errors[:20]})
 
    inserted, skipped = await batch_upsert_events(db, parsed, skip_past=False)
    total             = await count_events(db)
    return {
        "message":               "CSV processed and persisted to DATABASE_URL.",
        "filename":              file.filename,
        "rows_read":             len(parsed) + len(errors),
        "valid_rows":            len(parsed),
        "inserted":              inserted,
        "duplicates_or_skipped": max(0, len(parsed) - inserted) + skipped,
        "invalid_rows":          len(errors),
        "errors_preview":        errors[:20],
        "total_events_in_db":    total,
    }
 
# ─────────────────────────────────────────────────────────────
# GET /api/events
# ─────────────────────────────────────────────────────────────

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
                "city":            getattr(e, "event_cities", "") or e.city,
                "country":         e.country,
                "est_attendees":   e.est_attendees,
                "category":        e.category,
                "source_platform": e.source_platform,
                "registration_url": (
                    getattr(e, "website", "") or e.registration_url or e.source_url or ""
                ),
            }
            for e in all_evs[start: start + limit]
        ],
    }
 
 
# ─────────────────────────────────────────────────────────────────────
# GET /api/events/{id}
# ─────────────────────────────────────────────────────────────────────
 
@router.get("/events/{event_id}")
async def get_event(event_id: str, db: AsyncSession = Depends(get_db)):
    event = await get_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return {
        "id":              event.id,
        "name":            event.name,
        "description":     event.description,
        "start_date":      event.start_date,
        "end_date":        event.end_date,
        "venue":           getattr(event, "event_venues", "") or event.venue_name or "",
        "city":            getattr(event, "event_cities", "") or event.city or "",
        "country":         event.country,
        "est_attendees":   event.est_attendees,
        "category":        event.category,
        "industry":        getattr(event, "related_industries", "") or event.industry_tags or "",
        "audience_personas": event.audience_personas,
        "price_description": event.price_description,
        "website":         getattr(event, "website", "") or event.registration_url or event.source_url or "",
        "sponsors":        event.sponsors,
        "source_platform": event.source_platform,
        "source_url":      event.source_url,
        "ingested_at":     event.ingested_at.isoformat() if event.ingested_at else None,
    }
 

# ─────────────────────────────────────────────────────────────
# GET /api/stats
# ─────────────────────────────────────────────────────────────

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
        "apis_configured": {
            "ticketmaster": bool(settings.ticketmaster_key),
            "eventbrite":   bool(settings.eventbrite_token),
            "meetup":       True,
            "luma":         bool(settings.luma_api_key),
        },
    }
 


# ─────────────────────────────────────────────────────────────
# POST /api/refresh
# ─────────────────────────────────────────────────────────────

@router.post("/refresh")
async def refresh_events(background_tasks: BackgroundTasks):
    background_tasks.add_task(_do_refresh)
    return {"message": "Refresh started. Poll /api/stats for progress."}
 
async def _do_refresh():
    logger.info("Manual /api/refresh triggered.")
    try:
        stats = await run_ingestion()
        logger.info(
            f"Manual refresh done — fetched={stats['total_fetched']} "
            f"inserted={stats['total_inserted']} total_in_db={stats['total_in_db']}"
        )
    except Exception as e:
        logger.error(f"Manual refresh error: {e}")
 

# ─────────────────────────────────────────────────────────────
# Seed 10Times Protection
# ─────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────
# POST /api/seed-10times
# ─────────────────────────────────────────────────────────────

@router.post("/seed-10times")
async def seed_10times_events(
    background_tasks: BackgroundTasks,
    limit_events: int          = Query(1000, ge=1, le=2000),
    max_pages_per_listing: int = Query(10, ge=1, le=50),
    concurrency: int           = Query(1, ge=1, le=3),
    delay_seconds: float       = Query(3.0, ge=0.0, le=30.0),
    timeout_seconds: float     = Query(25.0, ge=1.0, le=60.0),
    dry_run: bool              = Query(False),
    x_seed_token: str | None   = Header(default=None),
):
    _require_seed_token(x_seed_token)
    if _seed_10times_status["running"]:
        raise HTTPException(status_code=409, detail="A 10times seed job is already running.")
 
    config = CrawlConfig(
        max_pages_per_listing=max_pages_per_listing, limit_events=limit_events,
        concurrency=concurrency, delay_seconds=delay_seconds,
        timeout_seconds=timeout_seconds, dry_run=dry_run,
    )
    _seed_10times_status.update({
        "running": True,
        "started_at": datetime.utcnow().isoformat() + "Z",
        "last_error": None,
    })
    background_tasks.add_task(_do_seed_10times, config)
    return {"message": "10times seed started. Check /api/seed-10times/status."}


# ─────────────────────────────────────────────────────────────
# GET /api/seed-10times/status
# ─────────────────────────────────────────────────────────────

@router.get("/seed-10times/status")
async def get_seed_10times_status(x_seed_token: str | None = Header(default=None)):
    _require_seed_token(x_seed_token)
    return _seed_10times_status
 
async def _do_seed_10times(config: CrawlConfig):
    try:
        result = await run_10times_seed(config)
        _seed_10times_status.update({"running": False, "last_result": result, "last_error": None,
                                      "finished_at": datetime.utcnow().isoformat() + "Z"})
        logger.info(f"10times seed done: {result}")
    except Exception as exc:
        _seed_10times_status.update({"running": False, "last_error": str(exc),
                                      "finished_at": datetime.utcnow().isoformat() + "Z"})
        logger.exception(f"10times seed failed: {exc}")



@router.post("/seed-conferencealerts")
async def seed_conferencealerts_events(
    background_tasks: BackgroundTasks,
    limit_events: int       = Query(1000, ge=1, le=5000),
    dry_run: bool           = Query(False),
    x_seed_token: str | None= Header(default=None),
):
    _require_seed_token(x_seed_token)
    if _seed_conferencealerts_status["running"]:
        raise HTTPException(status_code=409, detail="A conferencealerts seed job is already running.")
 
    config = ConferenceAlertsSeedConfig(limit_events=limit_events, dry_run=dry_run)
    _seed_conferencealerts_status.update({
        "running": True, "started_at": datetime.utcnow().isoformat() + "Z", "last_error": None,
    })
    background_tasks.add_task(_do_seed_conferencealerts, config)
    return {"message": "ConferenceAlerts seed started. Check /api/seed-conferencealerts/status."}
 

@router.get("/seed-conferencealerts/status")
async def get_seed_conferencealerts_status(x_seed_token: str | None = Header(default=None)):
    _require_seed_token(x_seed_token)
    return _seed_conferencealerts_status
 
 
async def _do_seed_conferencealerts(config: ConferenceAlertsSeedConfig):
    try:
        result = await run_conferencealerts_seed(config)
        _seed_conferencealerts_status.update({"running": False, "last_result": result, "last_error": None,
                                               "finished_at": datetime.utcnow().isoformat() + "Z"})
    except Exception as exc:
        _seed_conferencealerts_status.update({"running": False, "last_error": str(exc),
                                               "finished_at": datetime.utcnow().isoformat() + "Z"})
        logger.exception(f"conferencealerts seed failed: {exc}")


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
        _seed_global_status.update({
            "running": False, "finished_at": datetime.utcnow().isoformat() + "Z",
            "last_error": str(exc),
        })
        logger.exception(f"Global seed failed: {exc}")
