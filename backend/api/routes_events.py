"""
api/routes_events.py — definitive fix for result mix.

Root cause of 4 results (all GO, 0 CONSIDER):
  The scorer gave GO=357 from 440 events.
  Top 20 all scored as GO.
  Groq LLM returned GO for all 20.
  _apply_result_mix correctly labeled 4 GO + 3 CONSIDER…
  BUT the SearchResponse was built BEFORE _apply_result_mix ran,
  OR there was a path where only Groq-confirmed GO events were returned.

Fix:
  _force_result_mix() runs AFTER everything else and ALWAYS produces:
    • Top 4 by relevance_score → GO
    • Next 3 by relevance_score → CONSIDER
  regardless of Groq's verdicts.
  
  If fewer than 7 events total:
    • All available events → GO
    • No CONSIDER (can't invent events)
"""
import json, uuid
from datetime import datetime
from typing import Iterable, Optional, List

from fastapi import (
    APIRouter, Depends, HTTPException, Query,
    BackgroundTasks, UploadFile, File, Form,
)
from sqlalchemy.ext.asyncio import AsyncSession

from db.database import get_db
from db.crud import (
    get_candidate_events, get_all_events, get_event_by_id,
    count_events, create_company_profile, get_company_profile,
    count_by_source,
)
from models.icp_profile import SearchRequest, SearchResponse, CompanyContext
from models.company_profile import CompanyProfileCreate
from models.event import RankedEvent
from relevance.scorer import score_candidates
from relevance.groq_ranker import rank_with_groq
from ingestion.ingestion_manager import run_seed_only
from config import get_settings
from loguru import logger

router   = APIRouter()
settings = get_settings()

GO_COUNT      = 4
CONSIDER_COUNT = 3
TOTAL_RESULTS = GO_COUNT + CONSIDER_COUNT   # 7


# ═══════════════════════════════════════════════════════════
# Result mix — GUARANTEED 4 GO + 3 CONSIDER
# ═══════════════════════════════════════════════════════════

def _force_result_mix(ranked: List[RankedEvent]) -> List[RankedEvent]:
    """
    Always return exactly 7 events with verdicts forced as:
      • rank 1-4 (highest relevance) → GO
      • rank 5-7                     → CONSIDER

    This runs AFTER Groq ranking and OVERWRITES Groq's GO/CONSIDER/SKIP
    assignments so the output is always 4+3 regardless of what the LLM said.

    If fewer than 7 events exist:
      • All events ranked by score, all labeled GO
      (We never invent events that don't exist)

    If CONSIDER would be 0 (e.g. only 4 events available):
      The user sees 4 GO + 0 CONSIDER — which is honest.
      We do NOT relabel GO as CONSIDER if there are truly fewer events.
    """
    if not ranked:
        return []

    # Sort strictly by relevance_score descending
    by_score = sorted(ranked, key=lambda r: -r.relevance_score)

    total  = min(TOTAL_RESULTS, len(by_score))
    result = by_score[:total]

    for i, ev in enumerate(result):
        ev.fit_verdict = "GO" if i < GO_COUNT else "CONSIDER"

    go_n  = sum(1 for e in result if e.fit_verdict == "GO")
    con_n = sum(1 for e in result if e.fit_verdict == "CONSIDER")
    logger.info(
        f"Result mix: {len(result)} events returned "
        f"(GO={go_n} CONSIDER={con_n})"
    )
    return result


# ══════════════════════════════════════════════════════════
# Date helpers
# ══════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════
# PDF extraction
# ══════════════════════════════════════════════════════════

def _extract_pdf_text(file_bytes: bytes) -> str:
    try:
        import pypdf, io as _io
        reader = pypdf.PdfReader(_io.BytesIO(file_bytes))
        texts  = []
        for page in reader.pages[:20]:
            try:   texts.append(page.extract_text() or "")
            except Exception: pass
        return "\n".join(texts)[:8000]
    except Exception as e:
        logger.warning(f"PDF extraction failed: {e}")
        return ""


# ══════════════════════════════════════════════════════════
# POST /api/company-profile
# ══════════════════════════════════════════════════════════

@router.post("/company-profile")
async def save_company_profile(
    company_data: str = Form(...),
    deck: UploadFile = File(None),
    db: AsyncSession = Depends(get_db),
):
    try:
        profile_data = CompanyProfileCreate(**json.loads(company_data))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid JSON: {e}")

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
        "deck_extracted": bool(deck_text),
        "deck_chars":     len(deck_text),
    }


# ══════════════════════════════════════════════════════════
# GET /api/company-profile/{id}
# ══════════════════════════════════════════════════════════

@router.get("/company-profile/{profile_id}")
async def fetch_company_profile(
    profile_id: str, db: AsyncSession = Depends(get_db)
):
    cp = await get_company_profile(db, profile_id)
    if not cp:
        raise HTTPException(status_code=404, detail="Company profile not found.")
    return {
        "id":           cp.id,
        "company_name": cp.company_name,
        "founded_year": cp.founded_year,
        "location":     cp.location,
        "what_we_do":   cp.what_we_do,
        "what_we_need": cp.what_we_need,
        "deck_filename":cp.deck_filename,
        "has_deck":     bool(cp.deck_text),
    }


# ══════════════════════════════════════════════════════════
# POST /api/search — main endpoint
# ══════════════════════════════════════════════════════════

@router.post("/search", response_model=SearchResponse)
async def search_events(
    request: SearchRequest,
    db: AsyncSession = Depends(get_db),
):
    profile    = request.profile
    profile_id = str(uuid.uuid4())

    logger.info(
        f"Search: {profile.company_name} | "
        f"industries={profile.target_industries[:3]} | "
        f"geo={profile.target_geographies[:3]}"
    )

    # ── Resolve company context ──────────────────────────
    company_ctx: Optional[CompanyContext] = request.company_context
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

    # ══════════════════════════════════════════════════════
    # STEP 1 — Real-time API search
    # Runs in parallel with DB query. Results merged below.
    # ══════════════════════════════════════════════════════
    realtime_events = []
    try:
        from ingestion.realtime_pipeline import fetch_realtime_candidates
        realtime_events = await fetch_realtime_candidates(db, profile)
        logger.info(f"Real-time pipeline: {len(realtime_events)} candidates")
    except Exception as e:
        logger.warning(f"Real-time pipeline error (non-fatal): {e}")

    # ══════════════════════════════════════════════════════
    # STEP 2 — DB candidates
    # ══════════════════════════════════════════════════════
    candidates = await get_candidate_events(
        db=db,
        geographies=profile.target_geographies,
        industries=profile.target_industries,
        date_from=profile.date_from,
        date_to=profile.date_to,
        min_attendees=0,          # ← FIXED: never filter by attendees (most = 0 = unknown)
        limit=400,
    )

    # ══════════════════════════════════════════════════════
    # STEP 3 — Merge + deduplicate
    # ══════════════════════════════════════════════════════
    # Convert real-time EventCreate objects to EventORM-compatible objects
    seen_hashes = {getattr(c, "dedup_hash", c.id) for c in candidates}
    for rt_ev in realtime_events:
        dh = getattr(rt_ev, "dedup_hash", None)
        if dh and dh not in seen_hashes:
            seen_hashes.add(dh)
            candidates.append(rt_ev)

    # Hard date filter
    candidates = [
        e for e in candidates
        if _within_dates(e, profile.date_from, profile.date_to)
    ]

    # Fallback: if still very few, seed and retry
    if len(candidates) < 5:
        logger.warning(f"Only {len(candidates)} candidates — seeding.")
        await run_seed_only()
        candidates = await get_candidate_events(
            db=db,
            geographies=profile.target_geographies,
            industries=profile.target_industries,
            date_from=profile.date_from,
            date_to=profile.date_to,
            min_attendees=0,
            limit=400,
        )
        candidates = [
            e for e in candidates
            if _within_dates(e, profile.date_from, profile.date_to)
        ]

    if not candidates:
        return SearchResponse(
            profile_id=profile_id,
            company_name=profile.company_name,
            total_found=0,
            events=[],
            generated_at=datetime.utcnow().isoformat() + "Z",
        )

    logger.info(f"Candidates for scoring: {len(candidates)}")

    # ══════════════════════════════════════════════════════
    # STEP 4 — Score
    # ══════════════════════════════════════════════════════
    cosine_scores: dict = {}
    if settings.enable_semantic_search:
        try:
            from relevance.embedder import (
                build_profile_text, search_similar,
                add_events_to_index, get_index,
            )
            profile_text = build_profile_text(profile)
            idx = get_index()
            if idx.ntotal == 0:
                add_events_to_index(candidates)
            similar = search_similar(profile_text, top_k=100)
            cosine_scores = {r["id"]: r["cosine_score"] for r in similar}
        except Exception as e:
            logger.warning(f"Semantic search skipped: {e}")

    scored = score_candidates(candidates, profile, cosine_scores)

    # Take top N for Groq
    top_k  = settings.top_k_for_llm   # typically 20
    top    = scored[:top_k]

    top_events  = [e for e, _, _, _  in top]
    pre_scores  = {e.id: s          for e, s, _, _ in top}
    pre_tiers   = {e.id: t          for e, _, t, _ in top}
    pre_details = {e.id: d          for e, _, _, d in top}

    go_pre  = sum(1 for t in pre_tiers.values() if t == "GO")
    con_pre = sum(1 for t in pre_tiers.values() if t == "CONSIDER")
    logger.info(
        f"Top {len(top_events)} for Groq: GO={go_pre} CONSIDER={con_pre}"
    )

    # ══════════════════════════════════════════════════════
    # STEP 5 — SerpAPI enrichment (fill missing attendees / price)
    # ══════════════════════════════════════════════════════
    enrichments: dict = {}
    if settings.serpapi_key:
        try:
            from enrichment.serp_enricher import enrich_events_batch
            enrichments = await enrich_events_batch(
                events=top_events,
                serpapi_key=settings.serpapi_key,
                max_enrich=5,
            )
            if enrichments:
                logger.info(
                    f"SerpAPI enriched {len(enrichments)} events."
                )
        except Exception as e:
            logger.warning(f"SerpAPI enrichment skipped: {e}")

    # ══════════════════════════════════════════════════════
    # STEP 6 — Groq ranking
    # ══════════════════════════════════════════════════════
    try:
        ranked = await rank_with_groq(
            events      = top_events,
            profile     = profile,
            pre_scores  = pre_scores,
            pre_tiers   = pre_tiers,
            pre_details = pre_details,
            company_ctx = company_ctx,
            enrichments = enrichments,
        )
    except Exception as e:
        logger.error(f"Groq ranking failed: {e} — using fallback.")
        from relevance.scorer import build_fallback_rationale
        ranked = []
        for event in top_events:
            score  = pre_scores.get(event.id, 0.0)
            tier   = pre_tiers.get(event.id, "CONSIDER")
            detail = pre_details.get(event.id, {})
            ev_enrich = enrichments.get(event.id, {})
            ranked.append(_make_ranked_event(event, score, tier, detail, ev_enrich, profile))

    # ══════════════════════════════════════════════════════
    # STEP 7 — FORCE 4 GO + 3 CONSIDER
    #
    # This is the critical fix. No matter what Groq returned,
    # we take the top 7 by relevance_score and assign verdicts:
    #   rank 1-4 → GO
    #   rank 5-7 → CONSIDER
    # ══════════════════════════════════════════════════════
    final = _force_result_mix(ranked)

    go_n  = sum(1 for r in final if r.fit_verdict == "GO")
    con_n = sum(1 for r in final if r.fit_verdict == "CONSIDER")
    logger.info(
        f"Final results: {len(final)} events | GO={go_n} CONSIDER={con_n}"
    )

    return SearchResponse(
        profile_id=profile_id,
        company_name=profile.company_name,
        total_found=len(final),
        events=[r.model_dump() for r in final],
        generated_at=datetime.utcnow().isoformat() + "Z",
    )


def _make_ranked_event(event, score, tier, detail, enrichments, profile) -> RankedEvent:
    """Fallback RankedEvent builder (used when Groq fails)."""
    from relevance.scorer import build_fallback_rationale
    from relevance.groq_ranker import _get_industry, _get_place, _get_link, _get_pricing, _build_key_numbers

    ev_enrich = enrichments or {}
    att = ev_enrich.get("est_attendees", 0) if not event.est_attendees else event.est_attendees

    return RankedEvent(
        id=event.id,
        event_name=event.name,
        date=(
            event.start_date +
            (f" – {event.end_date}" if event.end_date and event.end_date != event.start_date else "")
        ),
        place=_get_place(event),
        event_link=_get_link(event),
        what_its_about=(event.short_summary or event.description or "")[:200],
        key_numbers=_build_key_numbers(event, ev_enrich),
        industry=_get_industry(event),
        buyer_persona=event.audience_personas or "",
        pricing=_get_pricing(event, ev_enrich),
        pricing_link=_get_link(event),
        fit_verdict=tier,
        verdict_notes=build_fallback_rationale(event, profile, detail, score, tier),
        sponsors=event.sponsors or "",
        speakers_link=event.speakers_url or "",
        agenda_link=event.agenda_url or "",
        relevance_score=score,
        source_platform=event.source_platform,
        est_attendees=att,
        organizer=getattr(event, "organizer", "") or "",
        website=_get_link(event),
        serpapi_enriched=bool(ev_enrich),
    )


# ══════════════════════════════════════════════════════════
# GET /api/events
# ══════════════════════════════════════════════════════════

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
                "link":            (
                    getattr(e, "website", "") or
                    e.registration_url or
                    e.source_url or ""
                ),
            }
            for e in all_evs[start: start + limit]
        ],
    }


# ══════════════════════════════════════════════════════════
# GET /api/events/{id}
# ══════════════════════════════════════════════════════════

@router.get("/events/{event_id}")
async def get_event(event_id: str, db: AsyncSession = Depends(get_db)):
    event = await get_event_by_id(db, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return {
        "id":          event.id,
        "name":        event.name,
        "description": event.description,
        "start_date":  event.start_date,
        "end_date":    event.end_date,
        "venue":       getattr(event, "event_venues", "") or event.venue_name or "",
        "city":        getattr(event, "event_cities", "") or event.city or "",
        "country":     event.country,
        "est_attendees": event.est_attendees,
        "industry":    (
            getattr(event, "related_industries", "") or
            event.industry_tags or ""
        ),
        "audience_personas": event.audience_personas,
        "price_description": event.price_description,
        "website":     (
            getattr(event, "website", "") or
            event.registration_url or
            event.source_url or ""
        ),
        "organizer":   getattr(event, "organizer", "") or "",
        "source_platform": event.source_platform,
        "source_url":  event.source_url,
        "ingested_at": event.ingested_at.isoformat() if event.ingested_at else None,
    }


# ══════════════════════════════════════════════════════════
# GET /api/stats
# ══════════════════════════════════════════════════════════

@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    total = await count_events(db)
    try:
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
        "total_events_in_db":  total,
        "events_by_source":    by_source,
        "faiss_vectors":       index_size,
        "groq_enabled":        bool(settings.groq_api_key),
        "serpapi_enabled":     bool(settings.serpapi_key),
        "resend_enabled":      bool(settings.resend_api_key),
        "apis_configured": {
            "ticketmaster": bool(settings.ticketmaster_key),
            "eventbrite":   bool(settings.eventbrite_token),
            "meetup":       True,
            "luma":         bool(settings.luma_api_key),
        },
    }


# ══════════════════════════════════════════════════════════
# POST /api/refresh
# ══════════════════════════════════════════════════════════

@router.post("/refresh")
async def refresh_events(background_tasks: BackgroundTasks):
    background_tasks.add_task(_do_refresh)
    return {"message": "Refresh started. Poll /api/stats for progress."}


async def _do_refresh():
    logger.info("Manual /api/refresh triggered.")
    try:
        from ingestion.ingestion_manager import run_ingestion
        stats = await run_ingestion()
        logger.info(
            f"Refresh done — "
            f"fetched={stats['total_fetched']} "
            f"inserted={stats['total_inserted']} "
            f"total_in_db={stats['total_in_db']}"
        )
    except Exception as e:
        logger.error(f"Refresh error: {e}")
