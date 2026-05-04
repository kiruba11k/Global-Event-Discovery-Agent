"""
Event Routes — updated with company profile support
POST /api/search             — main search endpoint (ICP + optional company context)
POST /api/company-profile    — save company profile (multipart: JSON + optional PDF)
GET  /api/company-profile/{id} — get saved company profile
GET  /api/events             — list all events (paginated)
GET  /api/events/{id}        — single event detail
GET  /api/stats              — database stats
POST /api/refresh            — trigger data refresh
"""
import io
import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.crud import (
    get_candidate_events, get_all_events, get_event_by_id, count_events,
    create_company_profile, get_company_profile,
)
from models.icp_profile import SearchRequest, SearchResponse, CompanyContext
from models.company_profile import CompanyProfileCreate
from relevance.scorer import score_candidates
from relevance.groq_ranker import rank_with_groq
from ingestion.ingestion_manager import run_ingestion, run_seed_only
from config import get_settings
from loguru import logger

router = APIRouter()
settings = get_settings()

# In-memory cache for last search results
_last_results: dict = {}


# ═══════════════════════════════════════════════════════════
# PDF text extraction helper
# ═══════════════════════════════════════════════════════════

def _extract_pdf_text(file_bytes: bytes) -> str:
    """Extract text from PDF bytes. Returns empty string on failure."""
    try:
        import pypdf
        import io as _io
        reader = pypdf.PdfReader(_io.BytesIO(file_bytes))
        texts = []
        for page in reader.pages[:20]:   # cap at 20 pages
            try:
                texts.append(page.extract_text() or "")
            except Exception:
                pass
        return "\n".join(texts)[:8000]
    except Exception as e:
        logger.warning(f"PDF extraction failed: {e} — storing without deck text")
        return ""


# ═══════════════════════════════════════════════════════════
# POST /api/company-profile
# ═══════════════════════════════════════════════════════════

@router.post("/company-profile")
async def save_company_profile(
    company_data: str = Form(...),
    deck: UploadFile = File(None),
    db: AsyncSession = Depends(get_db),
):
    try:
        data_dict = json.loads(company_data)
        profile_data = CompanyProfileCreate(**data_dict)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid company_data JSON: {e}")

    deck_text = ""
    deck_filename = ""
    if deck and deck.filename:
        deck_filename = deck.filename
        file_bytes = await deck.read()
        if deck.filename.lower().endswith(".pdf"):
            deck_text = _extract_pdf_text(file_bytes)
            logger.info(f"Extracted {len(deck_text)} chars from deck: {deck_filename}")
        else:
            logger.warning(f"Non-PDF deck uploaded: {deck_filename} — skipping extraction")

    company = await create_company_profile(db, profile_data, deck_text, deck_filename)
    return {
        "id": company.id,
        "message": "Company profile saved.",
        "deck_extracted": len(deck_text) > 0,
        "deck_chars": len(deck_text),
    }


# ═══════════════════════════════════════════════════════════
# GET /api/company-profile/{id}
# ═══════════════════════════════════════════════════════════

@router.get("/company-profile/{profile_id}")
async def fetch_company_profile(profile_id: str, db: AsyncSession = Depends(get_db)):
    profile = await get_company_profile(db, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Company profile not found.")
    return {
        "id": profile.id,
        "company_name": profile.company_name,
        "founded_year": profile.founded_year,
        "location": profile.location,
        "what_we_do": profile.what_we_do,
        "what_we_need": profile.what_we_need,
        "deck_filename": profile.deck_filename,
        "has_deck": bool(profile.deck_text),
    }


# ═══════════════════════════════════════════════════════════
# POST /api/search — main endpoint
# ═══════════════════════════════════════════════════════════

@router.post("/search", response_model=SearchResponse)
async def search_events(
    request: SearchRequest,
    db: AsyncSession = Depends(get_db),
):
    profile = request.profile
    profile_id = str(uuid.uuid4())
    logger.info(f"Search request for: {profile.company_name}")

    # ── Resolve company context ────────────────────────────
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
            logger.info(f"Loaded company context: {cp.company_name} (deck: {len(cp.deck_text)} chars)")

    # ── Step 1: Filter candidates from DB ─────────────────
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
        logger.warning("DB has few events — running seed ingestion...")
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
        if not candidates:
            candidates = await get_all_events(db, limit=200)

    logger.info(f"Candidates after DB filter: {len(candidates)}")

    # ── Step 2: Semantic similarity ────────────────────────
    cosine_scores: dict = {}
    if settings.enable_semantic_search:
        from relevance.embedder import build_profile_text, search_similar, add_events_to_index, get_index
        profile_text = build_profile_text(profile)
        index = get_index()
        if index.ntotal > 0:
            similar = search_similar(profile_text, top_k=100)
            cosine_scores = {r["id"]: r["cosine_score"] for r in similar}
        else:
            add_events_to_index(candidates)
            similar = search_similar(profile_text, top_k=100)
            cosine_scores = {r["id"]: r["cosine_score"] for r in similar}
    else:
        logger.info("Semantic search disabled — using rules + LLM ranking only.")

    # ── Step 3: Hybrid scoring ─────────────────────────────
    scored = score_candidates(candidates, profile, cosine_scores)
    top_candidates = scored[:settings.top_k_for_llm]
    top_events = [e for e, _, _ in top_candidates]
    pre_scores = {e.id: s for e, s, _ in top_candidates}
    pre_tiers = {e.id: t for e, _, t in top_candidates}

    # ── Step 4: Groq LLM ranking + rationale ──────────────
    ranked = await rank_with_groq(
        events=top_events,
        profile=profile,
        pre_scores=pre_scores,
        pre_tiers=pre_tiers,
        company_ctx=company_ctx,
    )

    # Sort: GO → CONSIDER → SKIP, then by score
    tier_order = {"GO": 0, "CONSIDER": 1, "SKIP": 2}
    ranked.sort(key=lambda r: (tier_order.get(r.fit_verdict, 3), -r.relevance_score))
    ranked = ranked[:profile.max_results]

    _last_results[profile_id] = ranked

    logger.info(
        f"Search complete: {len(ranked)} results "
        f"GO={sum(1 for r in ranked if r.fit_verdict=='GO')} "
        f"CONSIDER={sum(1 for r in ranked if r.fit_verdict=='CONSIDER')} "
        f"SKIP={sum(1 for r in ranked if r.fit_verdict=='SKIP')}"
    )

    return SearchResponse(
        profile_id=profile_id,
        company_name=profile.company_name,
        total_found=len(ranked),
        events=[r.model_dump() for r in ranked],
        generated_at=datetime.utcnow().isoformat() + "Z",
    )


# ═══════════════════════════════════════════════════════════
# GET /api/events
# ═══════════════════════════════════════════════════════════

@router.get("/events")
async def list_events(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    all_events = await get_all_events(db, limit=limit * page)
    start = (page - 1) * limit
    page_events = all_events[start:start + limit]
    total = await count_events(db)
    return {
        "total": total, "page": page, "limit": limit,
        "events": [
            {
                "id": e.id, "name": e.name, "start_date": e.start_date,
                "city": e.city, "country": e.country, "est_attendees": e.est_attendees,
                "category": e.category, "source_platform": e.source_platform,
                "registration_url": e.registration_url,
            }
            for e in page_events
        ],
    }


# ═══════════════════════════════════════════════════════════
# GET /api/events/{id}
# ═══════════════════════════════════════════════════════════

@router.get("/events/{event_id}")
async def get_event(event_id: str, db: AsyncSession = Depends(get_db)):
    event = await get_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return {
        "id": event.id, "name": event.name, "description": event.description,
        "start_date": event.start_date, "end_date": event.end_date,
        "venue_name": event.venue_name, "address": event.address,
        "city": event.city, "country": event.country,
        "est_attendees": event.est_attendees, "vip_count": getattr(event, "vip_count", 0),
        "category": event.category, "industry_tags": event.industry_tags,
        "audience_personas": event.audience_personas,
        "price_description": event.price_description,
        "registration_url": event.registration_url,
        "sponsors": event.sponsors, "speakers_url": event.speakers_url,
        "agenda_url": event.agenda_url, "source_platform": event.source_platform,
        "source_url": event.source_url,
        "ingested_at": event.ingested_at.isoformat() if event.ingested_at else None,
    }


# ═══════════════════════════════════════════════════════════
# GET /api/stats
# ═══════════════════════════════════════════════════════════

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
        "apis_configured": {
            "ticketmaster": bool(settings.ticketmaster_key),
            "eventbrite": bool(settings.eventbrite_token),
            "meetup": True,
            "luma": bool(settings.luma_api_key),
        },
    }


# ═══════════════════════════════════════════════════════════
# POST /api/refresh
# ═══════════════════════════════════════════════════════════

@router.post("/refresh")
async def refresh_events(background_tasks: BackgroundTasks):
    background_tasks.add_task(_do_refresh)
    return {"message": "Data refresh started in background. Check /api/stats for progress."}


async def _do_refresh():
    logger.info("Background refresh started...")
    stats = await run_ingestion()
    logger.info(f"Background refresh done: {stats}")
