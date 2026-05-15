"""
api/routes_events.py — Search endpoint wired to real-time pipeline.

POST /api/search:
  1. build_queries()           — ICP form → targeted API queries
  2. fetch_realtime_candidates() — fires SerpAPI + TM + EB + PHQ in parallel
  3. score_candidates()        — rule-based + optional FAISS scoring
  4. enrich_events_batch()     — SerpAPI fills attendees/price/links
  5. rank_with_groq()          — LLM ranking + anti-hallucination validator
  6. _apply_result_mix()       — enforce 4 GO + 3 CONSIDER

GET /api/stats — shows realtime_apis status so frontend can warn about missing keys.
"""
import csv
import hashlib
import io
import json
import uuid
from datetime import date, datetime
from typing import Iterable, Optional

from fastapi import (
    APIRouter, BackgroundTasks, Depends, File, Form,
    Header, HTTPException, Query, UploadFile,
)
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from db.crud import (
    batch_upsert_events, count_events,
    create_company_profile, get_all_events,
    get_company_profile, get_event_by_id,
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
from scripts.seed_conferencealerts_global import ConferenceAlertsSeedConfig, run_conferencealerts_seed
from scripts.seed_eventseye_global import run_eventseye_seed

router   = APIRouter()
settings = get_settings()

_last_results: dict  = {}
RESULT_LIMIT          = 7
GO_RESULT_COUNT       = 4
CONSIDER_RESULT_COUNT = 3

_seed_10times_status: dict           = {"running": False, "last_result": None, "last_error": None}
_seed_conferencealerts_status: dict  = {"running": False, "last_result": None, "last_error": None}
_seed_global_status: dict            = {"running": False, "last_result": None, "last_error": None}


# ── Helpers ────────────────────────────────────────────────────────

def _parse_date(value):
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


# ── CSV helpers ────────────────────────────────────────────────────

def _norm(v): return (v or "").strip()
def _csv_value(row, *keys):
    for k in keys:
        v = row.get(k)
        if _norm(v): return _norm(v)
    return ""
def _csv_int(row, *keys, default=0):
    v = _csv_value(row, *keys)
    if not v: return default
    try: return int(float(v))
    except: return default
def _csv_float(row, *keys, default=0.0):
    v = _csv_value(row, *keys)
    if not v: return default
    try: return float(v)
    except: return default
def _csv_bool(row, *keys, default=False):
    v = _csv_value(row, *keys).lower()
    if not v: return default
    return v in {"1", "true", "yes", "y"}
def _csv_dedup_hash(name, start, city, country):
    raw = "|".join([_norm(name).lower(), _norm(start), _norm(city).lower(), _norm(country).lower()])
    return hashlib.sha1(raw.encode()).hexdigest()
def _split_city_country(raw):
    c = _norm(raw)
    if not c: return "", ""
    if "(" in c and ")" in c:
        return c.split("(")[0].strip(" -,"), c.split("(")[1].split(")")[0].strip()
    if "," in c:
        p = [x.strip() for x in c.split(",", 1)]
        return p[0], p[1]
    return c, ""

def _parse_csv_row(row, row_number):
    nr = {_norm(str(k)).lower().lstrip("\ufeff"): v for k, v in row.items() if k is not None}
    name       = _csv_value(nr, "name", "event_name", "title")
    start_date = _csv_value(nr, "start_date", "start", "from_date")
    end_date   = _csv_value(nr, "end_date", "end", "to_date")
    if not start_date and _parse_date(end_date): start_date = end_date
    if not name or not start_date: raise ValueError(f"row {row_number}: 'name' and 'start_date' required")
    if not _parse_date(start_date): raise ValueError(f"row {row_number}: invalid start_date")
    event_id   = _csv_value(nr, "id", "event_id") or str(uuid.uuid4())
    website    = _csv_value(nr, "website", "website_url", "registration_url", "event_url", "event_link", "link")
    source_url = _csv_value(nr, "source_url", "source url", "url") or website
    city       = _csv_value(nr, "city")
    country    = _csv_value(nr, "country")
    ec         = _csv_value(nr, "event_cities", "event_city", "location")
    if (not city or not country) and ec:
        fc, fco = _split_city_country(ec)
        city = city or fc; country = country or fco
    ind = _csv_value(nr, "related_industries", "industry_tags", "industries", "industry")
    src = _csv_value(nr, "source", "source_platform")
    return EventCreate(
        id=event_id, dedup_hash=_csv_dedup_hash(name, start_date, city, country),
        source_platform=src or "CSV_UPLOAD",
        source_url=source_url or f"https://example.com/event/{event_id}",
        name=name, description=_csv_value(nr, "description", "summary"),
        short_summary=_csv_value(nr, "short_summary"), edition_number=_csv_value(nr, "edition_number"),
        industry_tags=ind, related_industries=ind,
        audience_personas=_csv_value(nr, "audience_personas", "buyer_persona"),
        start_date=start_date, end_date=end_date or start_date,
        duration_days=_csv_int(nr, "duration_days", default=1),
        venue_name=_csv_value(nr, "venue", "venue_name"), event_venues=_csv_value(nr, "event_venues"),
        event_cities=ec or f"{city}, {country}".strip(", "),
        address=_csv_value(nr, "address"), city=city, country=country,
        is_virtual=_csv_bool(nr, "is_virtual"), is_hybrid=_csv_bool(nr, "is_hybrid"),
        est_attendees=_csv_int(nr, "est_attendees", "estimated_attendees", "attendees"),
        category=_csv_value(nr, "category"),
        ticket_price_usd=_csv_float(nr, "ticket_price_usd", "price_usd"),
        price_description=_csv_value(nr, "price_description", "pricing"),
        registration_url=website, website=website,
        sponsors=_csv_value(nr, "sponsors"),
        speakers_url=_csv_value(nr, "speakers_url"), agenda_url=_csv_value(nr, "agenda_url"),
    )

def _extract_pdf_text(fb):
    try:
        import pypdf, io as _io
        r = pypdf.PdfReader(_io.BytesIO(fb))
        return "\n".join((p.extract_text() or "") for p in r.pages[:20])[:8000]
    except Exception as exc:
        logger.warning(f"PDF extraction: {exc}")
        return ""


# ══════════════════════════════════════════════════════════════════════
# POST /api/company-profile
# ══════════════════════════════════════════════════════════════════════

@router.post("/company-profile")
async def save_company_profile(company_data: str = Form(...), deck: UploadFile = File(None),
                                db: AsyncSession = Depends(get_db)):
    try:
        pd = CompanyProfileCreate(**json.loads(company_data))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid JSON: {exc}")
    deck_text = deck_filename = ""
    if deck and deck.filename:
        deck_filename = deck.filename
        fb = await deck.read()
        if deck.filename.lower().endswith(".pdf"):
            deck_text = _extract_pdf_text(fb)
    co = await create_company_profile(db, pd, deck_text, deck_filename)
    return {"id": co.id, "message": "Saved.", "deck_extracted": bool(deck_text)}


@router.get("/company-profile/{profile_id}")
async def fetch_company_profile(profile_id: str, db: AsyncSession = Depends(get_db)):
    cp = await get_company_profile(db, profile_id)
    if not cp: raise HTTPException(status_code=404, detail="Not found.")
    return {"id": cp.id, "company_name": cp.company_name, "founded_year": cp.founded_year,
            "location": cp.location, "what_we_do": cp.what_we_do, "what_we_need": cp.what_we_need,
            "deck_filename": cp.deck_filename, "has_deck": bool(cp.deck_text)}


# ══════════════════════════════════════════════════════════════════════
# POST /api/search  —  REAL-TIME PIPELINE
# ══════════════════════════════════════════════════════════════════════

@router.post("/search", response_model=SearchResponse)
async def search_events(request: SearchRequest, db: AsyncSession = Depends(get_db)):
    profile    = request.profile
    profile_id = str(uuid.uuid4())
    deal_size  = profile.avg_deal_size_category or "medium"

    logger.info(
        f"SEARCH  company={profile.company_name!r}  "
        f"ind={profile.target_industries}  "
        f"geo={profile.target_geographies}  "
        f"persona={profile.target_personas[:2]}  "
        f"dates={profile.date_from}→{profile.date_to}  "
        f"deal={deal_size}"
    )

    # ── Company context ─────────────────────────────────────────────
    company_ctx: CompanyContext | None = request.company_context
    if request.company_profile_id and not company_ctx:
        cp = await get_company_profile(db, request.company_profile_id)
        if cp:
            company_ctx = CompanyContext(
                company_name=cp.company_name, founded_year=cp.founded_year,
                location=cp.location, what_we_do=cp.what_we_do,
                what_we_need=cp.what_we_need, deck_text=cp.deck_text,
            )

    # ── Step 1-4: Real-time pipeline ────────────────────────────────
    # SerpAPI + Ticketmaster + Eventbrite + PredictHQ → DB → EventORM list
    candidates = await fetch_realtime_candidates(db, profile)

    # ── Fallback: DB-only wide query if pipeline returned nothing ────
    if len(candidates) < 5:
        total = await count_events(db)
        if total < 5:
            logger.warning("DB almost empty → seeding curated events")
            await run_seed_only()
        today = date.today().isoformat()
        from sqlalchemy import select as _sel
        from models.event import EventORM as _ORM
        r = await db.execute(
            _sel(_ORM).where(
                _ORM.start_date >= (profile.date_from or today),
                _ORM.start_date <= (profile.date_to   or "2030-12-31"),
            ).limit(500)
        )
        candidates = list(r.scalars().all())
        logger.info(f"Wide fallback: {len(candidates)} candidates from DB")

    # Date filter
    if profile.date_from or profile.date_to:
        candidates = [e for e in candidates if _within_dates(e, profile.date_from, profile.date_to)]

    if not candidates:
        logger.info("No candidates after date filter.")
        _last_results[profile_id] = []
        return SearchResponse(profile_id=profile_id, company_name=profile.company_name,
                               total_found=0, events=[], generated_at=datetime.utcnow().isoformat() + "Z")

    logger.info(f"Candidates for scoring: {len(candidates)}")

    # ── Step 5: Semantic scoring (disabled on free tier) ─────────────
    cosine_scores: dict = {}
    if settings.enable_semantic_search:
        try:
            from relevance.embedder import add_events_to_index, build_profile_text, get_index, search_similar
            idx = get_index()
            if idx.ntotal == 0:
                add_events_to_index(candidates)
            cosine_scores = {r["id"]: r["cosine_score"] for r in search_similar(build_profile_text(profile), top_k=100)}
        except Exception as exc:
            logger.warning(f"Semantic search: {exc}")

    # ── Step 6: Rule-based scoring ───────────────────────────────────
    scored     = score_candidates(candidates, profile, cosine_scores)
    top        = scored[:settings.top_k_for_llm]
    top_events = [e for e, _, _, _ in top]
    pre_scores = {e.id: s for e, s, _, _ in top}
    pre_tiers  = {e.id: t for e, _, t, _ in top}
    pre_details= {e.id: d for e, _, _, d in top}

    logger.info(
        f"Scored top {len(top_events)}: "
        f"GO={sum(1 for _,_,t,_ in top if t=='GO')}  "
        f"CONSIDER={sum(1 for _,_,t,_ in top if t=='CONSIDER')}  "
        f"SKIP={sum(1 for _,_,t,_ in top if t=='SKIP')}"
    )

    # ── Step 7: SerpAPI enrichment ────────────────────────────────────
    enrichments: dict = {}
    if settings.serpapi_key:
        try:
            from enrichment.serp_enricher import enrich_events_batch
            enrichments = await enrich_events_batch(
                events      = top_events,
                serpapi_key = settings.serpapi_key,
                max_enrich  = min(len(top_events), 10),
            )
            if enrichments:
                logger.info(
                    f"Enriched {len(enrichments)} events — "
                    f"att={sum(1 for d in enrichments.values() if d.get('est_attendees'))} "
                    f"price={sum(1 for d in enrichments.values() if d.get('price_description'))} "
                    f"link={sum(1 for d in enrichments.values() if d.get('event_link'))}"
                )
        except Exception as exc:
            logger.warning(f"SerpAPI enrichment (non-fatal): {exc}")

    # ── Step 8: Groq LLM ranking + cross-validation ──────────────────
    ranked = await rank_with_groq(
        events=top_events, profile=profile,
        pre_scores=pre_scores, pre_tiers=pre_tiers, pre_details=pre_details,
        company_ctx=company_ctx, enrichments=enrichments,
        deal_size_category=deal_size,
    )
    ranked.sort(key=lambda r: -r.relevance_score)

    # ── Step 9: Enforce 4 GO + 3 CONSIDER ────────────────────────────
    ranked = _apply_result_mix(ranked)
    _last_results[profile_id] = ranked

    go_n  = sum(1 for r in ranked if r.fit_verdict == "GO")
    con_n = sum(1 for r in ranked if r.fit_verdict == "CONSIDER")
    srcs  = {getattr(r, "source_platform", "?") for r in ranked}
    logger.info(f"RESULT: {len(ranked)} events | GO={go_n} CONSIDER={con_n} | sources={srcs}")

    return SearchResponse(
        profile_id=profile_id, company_name=profile.company_name,
        total_found=len(ranked), events=[r.model_dump() for r in ranked],
        generated_at=datetime.utcnow().isoformat() + "Z",
    )


# ══════════════════════════════════════════════════════════════════════
# GET /api/stats  —  includes real-time API key status
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

    phq_key = getattr(settings, "predicthq_key", "")
    return {
        "total_events_in_db": total,
        "events_by_source":   by_source,
        "faiss_vectors":      index_size,
        "groq_enabled":       bool(settings.groq_api_key),
        "serpapi_enabled":    bool(settings.serpapi_key),
        "resend_enabled":     bool(settings.resend_api_key),
        # Real-time API key status (shown in frontend status bar)
        "realtime_apis": {
            "serpapi_google_events": bool(settings.serpapi_key),
            "ticketmaster":          bool(settings.ticketmaster_key),
            "eventbrite":            bool(settings.eventbrite_token),
            "predicthq":             bool(phq_key),
        },
        "apis_configured": {
            "ticketmaster": bool(settings.ticketmaster_key),
            "eventbrite":   bool(settings.eventbrite_token),
            "meetup":       True,
            "luma":         bool(settings.luma_api_key),
        },
    }


# ══════════════════════════════════════════════════════════════════════
# Remaining endpoints (CSV upload, events list, refresh, seeding)
# ══════════════════════════════════════════════════════════════════════

@router.post("/events/upload-csv")
async def upload_events_csv(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file")
    raw = await file.read()
    if not raw: raise HTTPException(status_code=400, detail="Empty file")
    try: text = raw.decode("utf-8-sig")
    except UnicodeDecodeError: text = raw.decode("latin-1")
    reader = csv.DictReader(io.StringIO(text))
    nh = {_norm(h).lower() for h in (reader.fieldnames or []) if h}
    if "name" not in nh: raise HTTPException(status_code=400, detail="Missing column: name")
    parsed, errors = [], []
    for idx, row in enumerate(reader, 2):
        try: parsed.append(_parse_csv_row(row, idx))
        except ValueError as exc: errors.append(str(exc))
    if not parsed: raise HTTPException(status_code=400, detail={"message": "No valid rows", "errors": errors[:20]})
    inserted, skipped = await batch_upsert_events(db, parsed, skip_past=False)
    total = await count_events(db)
    return {"message": "CSV processed.", "filename": file.filename,
            "rows_read": len(parsed)+len(errors), "valid_rows": len(parsed),
            "inserted": inserted, "duplicates": max(0, len(parsed)-inserted)+skipped,
            "invalid_rows": len(errors), "errors_preview": errors[:20],
            "total_events_in_db": total}


@router.get("/events")
async def list_events(page: int = Query(1, ge=1), limit: int = Query(50, ge=1, le=200),
                      db: AsyncSession = Depends(get_db)):
    all_evs = await get_all_events(db, limit=limit*page)
    start   = (page-1)*limit
    total   = await count_events(db)
    return {"total": total, "page": page, "limit": limit, "events": [
        {"id": e.id, "name": e.name, "start_date": e.start_date,
         "city": getattr(e,"event_cities","") or e.city or "",
         "country": e.country, "est_attendees": e.est_attendees,
         "category": e.category, "source_platform": e.source_platform,
         "registration_url": getattr(e,"website","") or e.registration_url or e.source_url or ""}
        for e in all_evs[start:start+limit]
    ]}


@router.get("/events/{event_id}")
async def get_event(event_id: str, db: AsyncSession = Depends(get_db)):
    ev = await get_event_by_id(db, event_id)
    if not ev: raise HTTPException(status_code=404, detail="Not found")
    return {"id": ev.id, "name": ev.name, "description": ev.description,
            "start_date": ev.start_date, "end_date": ev.end_date,
            "venue": getattr(ev,"event_venues","") or ev.venue_name or "",
            "city": getattr(ev,"event_cities","") or ev.city or "",
            "country": ev.country, "est_attendees": ev.est_attendees,
            "industry": getattr(ev,"related_industries","") or ev.industry_tags or "",
            "audience_personas": ev.audience_personas, "price_description": ev.price_description,
            "website": getattr(ev,"website","") or ev.registration_url or ev.source_url or "",
            "source_platform": ev.source_platform, "source_url": ev.source_url}


@router.post("/refresh")
async def refresh_events(background_tasks: BackgroundTasks):
    background_tasks.add_task(_do_refresh)
    return {"message": "Refresh started."}

async def _do_refresh():
    try:
        stats = await run_ingestion()
        logger.info(f"Refresh done — inserted={stats['total_inserted']} total={stats['total_in_db']}")
    except Exception as exc:
        logger.error(f"Refresh error: {exc}")


def _require_token(x):
    if not settings.seed_admin_token: raise HTTPException(503, "SEED_ADMIN_TOKEN not set.")
    if x != settings.seed_admin_token: raise HTTPException(401, "Invalid token.")


@router.post("/seed-eventseye")
async def seed_eventseye(x_seed_token: str | None = Header(default=None)):
    _require_token(x_seed_token)
    return {"result": await run_eventseye_seed()}


@router.post("/seed-10times")
async def seed_10times(bg: BackgroundTasks, limit_events: int = Query(1000), dry_run: bool = Query(False),
                       x_seed_token: str | None = Header(default=None)):
    _require_token(x_seed_token)
    if _seed_10times_status["running"]: raise HTTPException(409, "Already running.")
    config = CrawlConfig(max_pages_per_listing=10, limit_events=limit_events, concurrency=1,
                         delay_seconds=3.0, timeout_seconds=25.0, dry_run=dry_run)
    _seed_10times_status.update({"running": True, "started_at": datetime.utcnow().isoformat()+"Z"})
    bg.add_task(_do_seed_10times, config)
    return {"message": "10times seed started."}

@router.get("/seed-10times/status")
async def seed_10times_status(x_seed_token: str | None = Header(default=None)):
    _require_token(x_seed_token); return _seed_10times_status

async def _do_seed_10times(cfg):
    try:
        r = await run_10times_seed(cfg)
        _seed_10times_status.update({"running": False, "last_result": r, "last_error": None, "finished_at": datetime.utcnow().isoformat()+"Z"})
    except Exception as exc:
        _seed_10times_status.update({"running": False, "last_error": str(exc), "finished_at": datetime.utcnow().isoformat()+"Z"})


@router.post("/seed-conferencealerts")
async def seed_ca(bg: BackgroundTasks, limit_events: int = Query(1000), dry_run: bool = Query(False),
                  x_seed_token: str | None = Header(default=None)):
    _require_token(x_seed_token)
    if _seed_conferencealerts_status["running"]: raise HTTPException(409, "Already running.")
    cfg = ConferenceAlertsSeedConfig(limit_events=limit_events, dry_run=dry_run)
    _seed_conferencealerts_status.update({"running": True, "started_at": datetime.utcnow().isoformat()+"Z"})
    bg.add_task(_do_seed_ca, cfg)
    return {"message": "ConferenceAlerts seed started."}

@router.get("/seed-conferencealerts/status")
async def seed_ca_status(x_seed_token: str | None = Header(default=None)):
    _require_token(x_seed_token); return _seed_conferencealerts_status

async def _do_seed_ca(cfg):
    try:
        r = await run_conferencealerts_seed(cfg)
        _seed_conferencealerts_status.update({"running": False, "last_result": r, "last_error": None, "finished_at": datetime.utcnow().isoformat()+"Z"})
    except Exception as exc:
        _seed_conferencealerts_status.update({"running": False, "last_error": str(exc), "finished_at": datetime.utcnow().isoformat()+"Z"})


@router.post("/seed-global")
async def seed_global(bg: BackgroundTasks,
                      limit_events_10times: int = Query(2000), max_pages: int = Query(15),
                      limit_events_conferencealerts: int = Query(5000), dry_run: bool = Query(False),
                      x_seed_token: str | None = Header(default=None)):
    _require_token(x_seed_token)
    if _seed_global_status["running"]: raise HTTPException(409, "Already running.")
    _seed_global_status.update({"running": True, "started_at": datetime.utcnow().isoformat()+"Z"})
    bg.add_task(_do_seed_global,
        CrawlConfig(max_pages_per_listing=max_pages, limit_events=limit_events_10times,
                    concurrency=2, delay_seconds=2.0, timeout_seconds=30.0, dry_run=dry_run),
        ConferenceAlertsSeedConfig(limit_events=limit_events_conferencealerts, dry_run=dry_run), dry_run)
    return {"message": "Global seed started."}

@router.get("/seed-global/status")
async def seed_global_status(x_seed_token: str | None = Header(default=None)):
    _require_token(x_seed_token); return _seed_global_status

async def _do_seed_global(tc, ca, dry_run):
    s = datetime.utcnow().isoformat()+"Z"
    try:
        t = await run_10times_seed(tc)
        c = await run_conferencealerts_seed(ca)
        e = await run_eventseye_seed(dry_run=dry_run)
        _seed_global_status.update({"running": False, "finished_at": datetime.utcnow().isoformat()+"Z",
                                     "last_error": None, "last_result": {"started_at": s, "10times": t, "conferencealerts": c, "eventseye": e}})
    except Exception as exc:
        _seed_global_status.update({"running": False, "finished_at": datetime.utcnow().isoformat()+"Z", "last_error": str(exc)})
