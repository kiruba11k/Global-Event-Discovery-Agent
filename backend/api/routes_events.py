"""
Event Routes
POST /api/search         — main search endpoint (ICP → ranked events)
GET  /api/events         — list all events (paginated)
GET  /api/events/{id}    — single event detail
GET  /api/export/csv     — download ranked results as CSV
GET  /api/stats          — database stats
POST /api/refresh        — trigger data refresh
"""
import io
import uuid
import json
import asyncio
from datetime import datetime
from typing import Optional, List

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.crud import get_candidate_events, get_all_events, get_event_by_id, count_events
from models.icp_profile import ICPProfile, SearchRequest, SearchResponse
from models.event import RankedEvent
from relevance.embedder import (
    build_profile_text, search_similar, add_events_to_index,
    load_index, get_index,
)
from relevance.scorer import score_candidates, assign_tier
from relevance.groq_ranker import rank_with_groq
from ingestion.ingestion_manager import run_ingestion, run_seed_only
from config import get_settings
from loguru import logger

router = APIRouter()
settings = get_settings()

# ─── In-memory cache for last search (per session, MVP simplicity) ─
_last_results: dict = {}


# ═══════════════════════════════════════════════════════════════════
# POST /api/search — main endpoint
# ═══════════════════════════════════════════════════════════════════
@router.post("/search", response_model=SearchResponse)
async def search_events(
    request: SearchRequest,
    db: AsyncSession = Depends(get_db),
):
    profile = request.profile
    profile_id = str(uuid.uuid4())
    logger.info(f"Search request for: {profile.company_name}")

    # ── Step 1: Filter candidates from DB ─────────────────────
    candidates = await get_candidate_events(
        db=db,
        geographies=profile.target_geographies,
        industries=profile.target_industries,
        date_from=profile.date_from,
        date_to=profile.date_to,
        min_attendees=profile.min_attendees or 0,
        limit=300,
    )

    # If DB is nearly empty, run seed immediately
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
        # If still empty, get all
        if not candidates:
            candidates = await get_all_events(db, limit=200)

    logger.info(f"Candidates after DB filter: {len(candidates)}")

    # ── Step 2: Semantic similarity ────────────────────────────
    profile_text = build_profile_text(profile)
    index = get_index()

    cosine_scores: dict = {}

    if index.ntotal > 0:
        similar = search_similar(profile_text, top_k=100)
        cosine_scores = {r["id"]: r["cosine_score"] for r in similar}
    else:
        # Build index from candidates on the fly
        logger.info("Building FAISS index from candidates...")
        add_events_to_index(candidates)
        similar = search_similar(profile_text, top_k=100)
        cosine_scores = {r["id"]: r["cosine_score"] for r in similar}

    # ── Step 3: Hybrid scoring ─────────────────────────────────
    scored = score_candidates(candidates, profile, cosine_scores)

    # Keep top N for LLM
    top_candidates = scored[: settings.top_k_for_llm]
    top_events = [e for e, _, _ in top_candidates]
    pre_scores = {e.id: s for e, s, _ in top_candidates}
    pre_tiers = {e.id: t for e, _, t in top_candidates}

    # ── Step 4: Groq LLM ranking + rationale ──────────────────
    ranked = await rank_with_groq(
        events=top_events,
        profile=profile,
        pre_scores=pre_scores,
        pre_tiers=pre_tiers,
    )

    # Sort final list: GO first, then CONSIDER, then SKIP
    tier_order = {"GO": 0, "CONSIDER": 1, "SKIP": 2}
    ranked.sort(key=lambda r: (tier_order.get(r.fit_verdict, 3), -r.relevance_score))

    # Limit to max_results
    ranked = ranked[: profile.max_results]

    # Cache for export
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


# ═══════════════════════════════════════════════════════════════════
# GET /api/events — paginated list
# ═══════════════════════════════════════════════════════════════════
@router.get("/events")
async def list_events(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    all_events = await get_all_events(db, limit=limit * page)
    start = (page - 1) * limit
    end = start + limit
    page_events = all_events[start:end]
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
            for e in page_events
        ],
    }


# ═══════════════════════════════════════════════════════════════════
# GET /api/events/{id}
# ═══════════════════════════════════════════════════════════════════
@router.get("/events/{event_id}")
async def get_event(event_id: str, db: AsyncSession = Depends(get_db)):
    event = await get_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
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
        "ingested_at": event.ingested_at.isoformat() if event.ingested_at else None,
    }


# ═══════════════════════════════════════════════════════════════════
# GET /api/export/csv?profile_id=...
# ═══════════════════════════════════════════════════════════════════
@router.get("/export/csv")
async def export_csv(profile_id: str = Query(...)):
    ranked = _last_results.get(profile_id)
    if not ranked:
        raise HTTPException(status_code=404, detail="No results for this profile_id. Run a search first.")

    rows = []
    for r in ranked:
        rows.append({
            "Event Name": r.event_name,
            "Date": r.date,
            "Place": r.place,
            "Event Link": r.event_link,
            "What It's About": r.what_its_about,
            "Key Numbers": r.key_numbers,
            "Industry": r.industry,
            "Buyer Persona": r.buyer_persona,
            "Pricing": r.pricing,
            "Pricing Link": r.pricing_link,
            "Fit Verdict": r.fit_verdict,
            "Verdict Notes": r.verdict_notes,
            "Sponsors": r.sponsors,
            "Speakers Link": r.speakers_link,
            "Agenda Link": r.agenda_link,
            "Relevance Score": f"{r.relevance_score:.2f}",
            "Source": r.source_platform,
        })

    df = pd.DataFrame(rows)
    stream = io.StringIO()
    df.to_csv(stream, index=False)
    stream.seek(0)

    return StreamingResponse(
        iter([stream.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="events_{profile_id[:8]}.csv"'},
    )


# ═══════════════════════════════════════════════════════════════════
# GET /api/stats
# ═══════════════════════════════════════════════════════════════════
@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    from relevance.embedder import get_index
    total = await count_events(db)
    index = get_index()
    return {
        "total_events_in_db": total,
        "faiss_vectors": index.ntotal,
        "groq_enabled": bool(settings.groq_api_key),
        "apis_configured": {
            "ticketmaster": bool(settings.ticketmaster_key),
            "eventbrite": bool(settings.eventbrite_token),
            "meetup": True,  # public Meetup GraphQL query currently does not require API key
            "luma": bool(settings.luma_api_key),
        },
    }


# ═══════════════════════════════════════════════════════════════════
# POST /api/refresh — trigger background ingestion
# ═══════════════════════════════════════════════════════════════════
@router.post("/refresh")
async def refresh_events(background_tasks: BackgroundTasks):
    background_tasks.add_task(_do_refresh)
    return {"message": "Data refresh started in background. Check /api/stats for progress."}


async def _do_refresh():
    logger.info("Background refresh started...")
    stats = await run_ingestion()
    logger.info(f"Background refresh done: {stats}")
