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
from relevance.fit_scorer import calculate_fit_score, estimate_icp_count, calculate_universe_stats, count_competitors
from relevance.profile_store import (
    get_recall_boosts, record_search_results,
    profile_core_hash, profile_window_hash,
)
from relevance.meeting_calculator import calculate_meeting_potential
from scripts.seed_10times_global import CrawlConfig, run_10times_seed
from scripts.seed_conferencealerts_global import ConferenceAlertsSeedConfig, run_conferencealerts_seed
from scripts.seed_eventseye_global import run_eventseye_seed

router   = APIRouter()
settings = get_settings()

_last_results: dict  = {}
RESULT_LIMIT          = 6
GO_RESULT_COUNT       = 3
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
    """
    Always return exactly RESULT_LIMIT (6) events.
    Priority: GO events first, then CONSIDER, then best SKIP (by relevance_score).
    """
    all_ranked      = list(ranked)
    go_events       = [r for r in all_ranked if r.fit_verdict == "GO"]
    consider_events = [r for r in all_ranked if r.fit_verdict == "CONSIDER"]
    skip_events     = [r for r in all_ranked if r.fit_verdict == "SKIP"]

    selected_go  = go_events[:GO_RESULT_COUNT]
    remaining    = RESULT_LIMIT - len(selected_go)
    selected_con = consider_events[:remaining]
    remaining    = RESULT_LIMIT - len(selected_go) - len(selected_con)

    # Fill remaining slots with best-scored SKIP events so we always return 6
    selected_skip = skip_events[:remaining] if remaining > 0 else []

    result = selected_go + selected_con + selected_skip
    # Final safety: if still short, append any remaining events
    if len(result) < RESULT_LIMIT:
        used_ids = {r.id for r in result}
        extras   = [r for r in all_ranked if r.id not in used_ids]
        result  += extras[:RESULT_LIMIT - len(result)]
    return result[:RESULT_LIMIT]



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

    # ── Regional fallback: if specific geo yields < 3 candidates, broaden ──
    # Maps specific countries → broader region so users always get results.
    _GEO_REGION_MAP: dict[str, list[str]] = {
        # Southeast Asia
        "indonesia": ["southeast asia", "asia", "singapore", "malaysia", "thailand", "vietnam", "philippines"],
        "vietnam":   ["southeast asia", "asia", "singapore", "thailand", "malaysia"],
        "philippines": ["southeast asia", "asia", "singapore", "malaysia"],
        "myanmar":   ["southeast asia", "asia", "singapore", "thailand"],
        "cambodia":  ["southeast asia", "asia", "singapore", "thailand"],
        "laos":      ["southeast asia", "asia", "thailand", "singapore"],
        # South Asia
        "bangladesh": ["south asia", "asia", "india", "singapore"],
        "sri lanka":  ["south asia", "asia", "india", "singapore"],
        "nepal":      ["south asia", "asia", "india"],
        "pakistan":   ["south asia", "asia", "india", "uae"],
        # Middle East
        "bahrain":   ["middle east", "uae", "saudi arabia"],
        "kuwait":    ["middle east", "uae", "saudi arabia"],
        "oman":      ["middle east", "uae", "saudi arabia"],
        "qatar":     ["middle east", "uae", "saudi arabia"],
        # Africa
        "nigeria":   ["africa", "south africa"],
        "kenya":     ["africa", "south africa"],
        "ghana":     ["africa", "south africa"],
        "egypt":     ["africa", "middle east", "uae"],
        # Europe
        "austria":   ["europe", "germany"],
        "switzerland": ["europe", "germany"],
        "belgium":   ["europe", "netherlands", "germany"],
        "denmark":   ["europe", "germany", "netherlands"],
        "sweden":    ["europe", "germany"],
        "norway":    ["europe", "germany"],
        "finland":   ["europe", "germany"],
        "poland":    ["europe", "germany"],
        "czech":     ["europe", "germany"],
        "hungary":   ["europe", "germany"],
        "portugal":  ["europe", "spain"],
        "romania":   ["europe", "germany"],
        # Americas
        "mexico":    ["latin america", "usa"],
        "colombia":  ["latin america", "usa"],
        "argentina":  ["latin america", "usa"],
        "chile":     ["latin america", "usa"],
        "peru":      ["latin america", "usa"],
    }

    region_fallback_note: Optional[str] = None
    original_geos = list(profile.target_geographies or [])

    if candidates and len(candidates) < 3 and original_geos:
        # Check if specific non-global geos were requested
        non_global = [g for g in original_geos if g.lower() not in ("global", "worldwide", "international")]
        if non_global:
            # Try broadening to regional equivalents
            broader_geos: list[str] = []
            for geo in non_global:
                geo_l = geo.lower().strip()
                for key, regions in _GEO_REGION_MAP.items():
                    if key in geo_l or geo_l in key:
                        broader_geos.extend(regions)
                        break
                else:
                    # Generic: just try the continent/region implicitly
                    broader_geos.append(geo)
            broader_geos = list(dict.fromkeys(broader_geos))  # deduplicate

            if broader_geos:
                # Re-fetch with broader geo set
                from db.crud import get_candidate_events as _gce
                broader_candidates = await _gce(
                    db,
                    geographies  = broader_geos,
                    industries   = profile.target_industries or [],
                    date_from    = profile.date_from,
                    date_to      = profile.date_to,
                    limit        = 400,
                )
                if profile.date_from or profile.date_to:
                    broader_candidates = [e for e in broader_candidates if _within_dates(e, profile.date_from, profile.date_to)]

                if len(broader_candidates) > len(candidates):
                    region_fallback_note = (
                        f"No events found in {', '.join(non_global)}. "
                        f"Showing events from the broader region ({', '.join(broader_geos[:3])}) instead."
                    )
                    candidates = broader_candidates
                    logger.info(f"Regional fallback: {', '.join(non_global)} → {', '.join(broader_geos[:3])} ({len(candidates)} candidates)")

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
    # ── Profile recall: pre-boost known high-converting events ─────────
    # Checks profile_feedback table for events that performed well for this
    # ICP (or similar ICPs). Boost multiplier applied to cosine_scores dict
    # so high-recall events get a head-start in scoring.
    # Handles expiry: past events ignored, stale windows get smaller boost.
    recall_boosts: dict[str, float] = {}
    try:
        recall_boosts = await get_recall_boosts(db, profile)
        if recall_boosts:
            # Merge recall boosts into cosine_scores (additive boost)
            for eid, mult in recall_boosts.items():
                existing = cosine_scores.get(eid, 0.0)
                cosine_scores[eid] = min(existing * mult + (mult - 1.0) * 0.3, 1.0)
    except Exception as _e:
        logger.debug(f"Recall boost error: {_e}")

    scored = score_candidates(candidates, profile, cosine_scores)

    # ── Determine relevance threshold dynamically ─────────────────
    # Events with score >= threshold are "worth considering".
    # Threshold = 10% of the max score (so at least 10% ICP match).
    # Always guarantee at least RESULT_LIMIT events pass the cut.
    if scored:
        max_score = max(s for _, s, _, _ in scored)
        threshold = max(0.10, max_score * 0.10)
    else:
        threshold = 0.10

    all_relevant = [(e, s, t, d) for e, s, t, d in scored if s >= threshold]
    # Safety: always include at least RESULT_LIMIT events
    if len(all_relevant) < RESULT_LIMIT:
        all_relevant = scored[:max(RESULT_LIMIT, len(all_relevant))]

    shows_worth_considering_count = len(all_relevant)

    top        = all_relevant[:settings.top_k_for_llm]
    top_events = [e for e, _, _, _ in top]
    pre_scores = {e.id: s for e, s, _, _ in top}
    pre_tiers  = {e.id: t for e, _, t, _ in top}
    pre_details= {e.id: d for e, _, _, d in top}

    logger.info(
        f"Scored top {len(top_events)} (of {shows_worth_considering_count} relevant): "
        f"GO={sum(1 for _,_,t,_ in top if t=='GO')}  "
        f"CONSIDER={sum(1 for _,_,t,_ in top if t=='CONSIDER')}  "
        f"SKIP={sum(1 for _,_,t,_ in top if t=='SKIP')}"
    )


    # Build shared Groq async client (reused for both enrichment and ranking)
    _groq_client_async = None
    try:
        from groq import AsyncGroq as _AsyncGroq
        import os as _os
        _groq_key = getattr(settings, "groq_api_key", "") or _os.environ.get("GROQ_API_KEY", "")
        if _groq_key:
            _groq_client_async = _AsyncGroq(api_key=_groq_key)
    except Exception:
        pass

    # ── Step 7: Groq LLM ranking + cross-validation (no enrichment yet) ─
    # Run ranking first on raw DB data to select the 6 final events,
    # then enrich only those 6 — avoids wasting SerpAPI quota on events
    # that won't be shown.
    ranked = await rank_with_groq(
        events=top_events, profile=profile,
        pre_scores=pre_scores, pre_tiers=pre_tiers, pre_details=pre_details,
        company_ctx=company_ctx, enrichments={},
        deal_size_category=deal_size,
    )
    ranked.sort(key=lambda r: -r.relevance_score)

    # ── Step 8: Enforce 6 results (3 GO + 3 CONSIDER, fill with SKIP) ─
    ranked = _apply_result_mix(ranked)
    _last_results[profile_id] = ranked

    # ── Step 9: SerpAPI enrichment — only for the 6 final events ──────
    # Cost optimisation: skip events already enriched in DB (serpapi_enriched=True
    # with valid attendees/date). Enrich at most 6 events = 6 SerpAPI calls.
    final_event_ids = {r.id for r in ranked}
    final_top_events = [e for e in top_events if e.id in final_event_ids]

    enrichments: dict = {}
    if settings.serpapi_key and final_top_events:
        try:
            from enrichment.serp_enricher import enrich_events_batch
            from db.crud import update_event_enrichment
            enrichments = await enrich_events_batch(
                events      = final_top_events,
                serpapi_key = settings.serpapi_key,
                groq_client = _groq_client_async,
                max_enrich  = len(final_top_events),  # exactly the 6 shown events
            )
            if enrichments:
                logger.info(
                    f"Enriched {len(enrichments)} events — "
                    f"att={sum(1 for d in enrichments.values() if d.get('est_attendees'))} "
                    f"date={sum(1 for d in enrichments.values() if d.get('start_date'))} "
                    f"price={sum(1 for d in enrichments.values() if d.get('price_description'))} "
                    f"link={sum(1 for d in enrichments.values() if d.get('event_link'))}"
                )
                                # Persist enriched data back to DB using a fresh session
                # (cannot reuse request db — it closes when the response is sent)
                import asyncio as _aio
                from db.database import AsyncSessionLocal as _SessionLocal
                _snapshot = dict(enrichments)
                async def _persist_enrichments():
                    async with _SessionLocal() as _db:
                        for eid, edata in _snapshot.items():
                            db_updates: dict = {}
                            if edata.get("est_attendees"):
                                db_updates["est_attendees"] = edata["est_attendees"]
                            if edata.get("start_date"):
                                db_updates["start_date"] = edata["start_date"]
                            if edata.get("end_date"):
                                db_updates["end_date"] = edata["end_date"]
                            if edata.get("registration_url") or edata.get("website"):
                                url = edata.get("registration_url") or edata.get("website", "")
                                db_updates["registration_url"] = url
                                db_updates["website"]          = url
                            if edata.get("price_description"):
                                db_updates["price_description"] = edata["price_description"]
                            if edata.get("audience_personas"):
                                db_updates["audience_personas"] = edata["audience_personas"]
                            if db_updates:
                                await update_event_enrichment(_db, eid, db_updates)
                _aio.ensure_future(_persist_enrichments())
        except Exception as exc:
            logger.warning(f"SerpAPI enrichment (non-fatal): {exc}")

    # Re-rank the final 6 with enrichment data now available
    if enrichments:
        ranked = await rank_with_groq(
            events=final_top_events, profile=profile,
            pre_scores=pre_scores, pre_tiers=pre_tiers, pre_details=pre_details,
            company_ctx=company_ctx, enrichments=enrichments,
            deal_size_category=deal_size,
        )
        ranked.sort(key=lambda r: -r.relevance_score)
        ranked = ranked[:RESULT_LIMIT]
        _last_results[profile_id] = ranked


    # ── Step 10: Calculate 5-factor fit scores + ICP counts ──────────
    # Attach fit_grade (A+/A/B+/B/C), icp_count, and universe_stats
    # These replace the GO/CONSIDER labels in the frontend.
    serialised_events = []
    for r in ranked:
        ev_dict = r.model_dump()
        # Look up the pre-scoring rule_score for this event (0..1 range)
        rule_s = pre_scores.get(r.event_id or r.id, 0.0) if hasattr(r, "event_id") else pre_scores.get(r.id, 0.0)
        # Find the original EventORM for factor scoring
        event_orm = next((e for e in top_events if e.id == (r.event_id if hasattr(r, "event_id") else r.id)), None)
        if event_orm:
            fit = calculate_fit_score(event_orm, profile, rule_s)
            icp = estimate_icp_count(event_orm, profile, rule_s)
            comp_cnt = count_competitors(event_orm, profile)
            ev_dict["fit_grade"]          = fit["fit_grade"]
            ev_dict["fit_score"]          = fit["fit_score"]
            ev_dict["fit_label"]          = fit["fit_label"]
            ev_dict["fit_factor_scores"]  = fit["factor_scores"]
            ev_dict["icp_count"]          = icp
            ev_dict["competitor_count"]   = comp_cnt
        else:
            # Fallback: derive grade from relevance_score
            rs = int(r.relevance_score or 0)
            if   rs >= 80: grade = "A+"
            elif rs >= 65: grade = "A"
            elif rs >= 50: grade = "B+"
            elif rs >= 35: grade = "B"
            else:          grade = "C"
            ev_dict["fit_grade"]         = grade
            ev_dict["fit_score"]         = rs
            ev_dict["fit_label"]         = "Fit score"
            ev_dict["fit_factor_scores"] = {}
            ev_dict["icp_count"]         = None
            ev_dict["competitor_count"]  = 0
        # ── Meeting potential + ROI calculator ─────────────────────
        diff_score  = getattr(profile, "differentiator_score",  5) or 5
        client_rng  = getattr(profile, "client_count_range", "11-50") or "11-50"
        meeting_pot = None
        if event_orm:
            meeting_pot = calculate_meeting_potential(
                event_dict           = ev_dict,
                profile              = profile,
                fit_result           = fit if event_orm else {"fit_grade":"C","fit_score":0,"confidence":"low","data_gaps":[]},
                differentiator_score = diff_score,
                client_count_range   = client_rng,
            )
        ev_dict["meeting_potential"] = meeting_pot
        serialised_events.append(ev_dict)

    # Universe stats banner — pass real relevant count so "shows worth considering"
    # reflects ALL ICP-matched events, not just the 6 displayed.
    universe = calculate_universe_stats(serialised_events, total_indexed=await count_events(db))
    universe["shows_worth_considering"] = shows_worth_considering_count

    # ── Build lightweight rows for relevant events not in top 6 ───
    # These populate the Event Table without SerpAPI cost.
    top6_ids = {r.id for r in ranked}
    all_relevant_events: list[dict] = []
    for ev, score, tier, detail in all_relevant:
        if ev.id in top6_ids:
            continue
        all_relevant_events.append({
            "event_id":        ev.id,
            "event_name":      ev.name or "",
            "date":            ev.start_date or "",
            "place":           getattr(ev, "event_cities", "") or f"{ev.city or ''}, {ev.country or ''}".strip(", "),
            "industry":        getattr(ev, "related_industries", "") or ev.industry_tags or "",
            "audience_personas": ev.audience_personas or "",
            "est_attendees":   ev.est_attendees or 0,
            "relevance_score": round(score * 100),
            "fit_verdict":     tier,
            "source_platform": ev.source_platform or "",
            "source_url":      ev.source_url or "",
            "registration_url": getattr(ev, "registration_url", "") or getattr(ev, "website", "") or ev.source_url or "",
            "website":          getattr(ev, "website", "") or getattr(ev, "registration_url", "") or ev.source_url or "",
            "description":     (ev.description or "")[:300],
            "price_description": ev.price_description or "",
        })


    go_n  = sum(1 for r in ranked if r.fit_verdict == "GO")
    con_n = sum(1 for r in ranked if r.fit_verdict == "CONSIDER")
    srcs  = {getattr(r, "source_platform", "?") for r in ranked}
    logger.info(f"RESULT: {len(ranked)} events | GO={go_n} CONSIDER={con_n} | sources={srcs}")

    # ── Post-ranking geo coverage check ──────────────────────────────
    # If NONE of the final events match the user's requested geographies,
    # always surface a fallback note explaining the mismatch — even when
    # the early candidate pool was large enough to skip the regional fallback.
    if not region_fallback_note and original_geos:
        non_global_geos = [g for g in original_geos if g.lower() not in ("global", "worldwide", "international")]
        if non_global_geos:
            def _event_matches_geo(ev_dict: dict, geos: list[str]) -> bool:
                loc = " ".join(filter(None, [
                    ev_dict.get("place", ""),
                    ev_dict.get("location", ""),
                ])).lower()
                return any(g.lower()[:6] in loc or loc.find(g.lower()[:5]) >= 0 for g in geos)

            matched = sum(1 for ev in serialised_events if _event_matches_geo(ev, non_global_geos))
            if matched == 0:
                # Zero of the final events are in the requested geos — explain why
                # and surface the neighbour suggestions from the geo-hint map
                neighbours: list[str] = []
                for geo in non_global_geos:
                    geo_l = geo.lower().strip()
                    for key, nbrs in _GEO_NEIGHBOURS.items():
                        if key in geo_l or geo_l in key or geo_l.startswith(key[:6]):
                            neighbours.extend(nbrs[:3])
                            break
                neighbours = list(dict.fromkeys(neighbours))[:4]
                neighbour_str = ", ".join(t.title() for t in neighbours) if neighbours else "nearby hubs"
                region_fallback_note = (
                    f"No events found yet in {', '.join(non_global_geos)}. "
                    f"Showing the most relevant global events for your ICP instead. "
                    f"Try nearby regions with more coverage: {neighbour_str}."
                )
            elif matched < len(serialised_events) // 2:
                # Fewer than half the results match — soft warning
                region_fallback_note = (
                    f"Limited events in {', '.join(non_global_geos)} — "
                    f"showing the best global matches for your ICP to complete the ranking."
                )


    resp = SearchResponse(
        profile_id=profile_id, company_name=profile.company_name,
        total_found=len(ranked), events=serialised_events,
        generated_at=datetime.utcnow().isoformat() + "Z",
    )
    # Attach universe_stats as extra field (SearchResponse is a BaseModel)
    resp_dict = resp.model_dump()
    resp_dict["universe_stats"]        = universe
    resp_dict["profile_hash"]          = profile_core_hash(profile)
    resp_dict["region_fallback_note"]  = region_fallback_note
    resp_dict["all_relevant_events"]   = all_relevant_events



    # ── Record search results for future recall (async, non-blocking) ─
    # Stores top events so future similar searches benefit from this data.
    try:
        import asyncio as _asyncio
        from db.database import AsyncSessionLocal as _SL
        _prof_snap = profile
        _evts_snap = serialised_events[:20]
        async def _record():
            async with _SL() as _db2:
                await record_search_results(_db2, _prof_snap, _evts_snap)
        _asyncio.ensure_future(_record())
    except Exception as _e:
        logger.debug(f"Record search results error: {_e}")


    return resp_dict

# ══════════════════════════════════════════════════════════════════════
# GET /api/geo-hint  —  live event counts per geo + neighbour suggestions
# ══════════════════════════════════════════════════════════════════════

@router.get("/geo-hint")
async def geo_hint(
    geos:       str = Query(""),
    industries: str = Query(""),
    db: AsyncSession = Depends(get_db),
):
    """
    For each requested geography, return:
    - count: how many future events exist in DB for that geo
    - status: 'good' (>=10), 'sparse' (1-9), 'none' (0)
    - suggestions: top neighbour geos with their live counts (when status != 'good')

    Counts are live DB queries — not hardcoded.
    """
    from sqlalchemy import select as _sel, func as _func, or_ as _or
    from models.event import EventORM as _ORM

    geo_list = [g.strip() for g in geos.split(",") if g.strip()]
    ind_list = [i.strip() for i in industries.split(",") if i.strip()]
    if not geo_list:
        return {"coverage": []}

    today = date.today().isoformat()

    async def _count_geo(geo: str) -> int:
        """Live count of future events matching a geo string."""
        geo_l = geo.strip().lower()
        geo_parts = [geo_l]
        if " - " in geo_l:
            geo_parts.extend(p.strip() for p in geo_l.split(" - "))
        filters = []
        for part in geo_parts:
            if len(part) > 1:
                filters.append(_ORM.country.ilike(f"%{part}%"))
                filters.append(_ORM.city.ilike(f"%{part}%"))
                filters.append(_ORM.event_cities.ilike(f"%{part}%"))
        if not filters:
            return 0
        stmt = _sel(_func.count(_ORM.id)).where(
            _ORM.start_date >= today,
            _or(*filters),
        )
        result = await db.execute(stmt)
        return result.scalar() or 0

    coverage = []
    for geo in geo_list:
        count = await _count_geo(geo)
        status = "good" if count >= 10 else ("sparse" if count > 0 else "none")

        suggestions = []
        if status != "good":
            geo_l = geo.strip().lower()
            # Find neighbours from the static proximity map
            neighbours: list[str] = []
            for key, nbrs in _GEO_NEIGHBOURS.items():
                if key in geo_l or geo_l in key or geo_l.startswith(key[:6]):
                    neighbours = nbrs
                    break
            if not neighbours:
                # Generic fallback: global hubs always have events
                neighbours = ["singapore", "germany", "usa", "uk", "uae"]

            for nbr in neighbours[:6]:
                nbr_count = await _count_geo(nbr)
                if nbr_count > 0:
                    suggestions.append({"geo": nbr.title(), "count": nbr_count})
            # Sort by count descending
            suggestions.sort(key=lambda x: -x["count"])
            suggestions = suggestions[:4]

        coverage.append({
            "geo":         geo,
            "count":       count,
            "status":      status,
            "suggestions": suggestions,
        })

    return {"coverage": coverage}


# ══════════════════════════════════════════════════════════════════════
# GET /api/stats  —  includes real-time API key status
# ══════════════════════════════════════════════════════════════════════

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
