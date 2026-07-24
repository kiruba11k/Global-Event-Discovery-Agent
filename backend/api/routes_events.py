"""
api/routes_events.py — Search endpoint, DB-only mode.

POST /api/search:
  1. build_queries()             — ICP form → targeted keywords (still used
                                    for logging/query-shaping, not live APIs)
  2. fetch_realtime_candidates() — DB-only: SerpAPI/Ticketmaster/Eventbrite/
                                    PredictHQ fan-out is disabled (see
                                    ingestion/realtime_pipeline.py); this
                                    just runs the tiered DB query.
  3. score_candidates()          — rule-based + optional pgvector/FAISS scoring
  4. rank_with_groq()            — LLM ranking + anti-hallucination validator,
                                    runs ONCE (OpenAI now, see
                                    relevance/llm_client.py). Verdict/score/
                                    order are frozen after this call.
  5. _apply_result_mix()         — enforce 3 GO + 3 CONSIDER
  6. SerpAPI enrichment (Step 9) + _patch_ranked_with_enrichment() —
                                    display-only field patch (est_attendees,
                                    pricing, link, description), no second
                                    LLM ranking/validation pass

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
    Header, HTTPException, Query, Request, UploadFile,
)
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from db.crud import (
    batch_upsert_events, count_events,
    get_all_events, get_event_by_id, get_event_by_dedup_hash,
    update_event_enrichment,
)
from db.database import get_db
from ingestion.ingestion_manager import run_ingestion, run_seed_only
from ingestion.platform_normaliser import _iso_date
from ingestion.realtime_pipeline import fetch_realtime_candidates
from models.event import EventCreate
from models.icp_profile import CompanyContext, ICPProfile, SearchRequest, SearchResponse
from relevance.groq_ranker import rank_with_groq
from relevance.scorer import score_candidates
from relevance.fit_scorer import calculate_fit_score, estimate_icp_count, calculate_universe_stats, count_competitors
from relevance.profile_store import profile_core_hash
from relevance.meeting_calculator import calculate_meeting_potential
from scripts.seed_10times_global import CrawlConfig, run_10times_seed
from scripts.seed_conferencealerts_global import ConferenceAlertsSeedConfig, run_conferencealerts_seed
from scripts.seed_eventseye_global import run_eventseye_seed

router   = APIRouter()
settings = get_settings()

_last_results: dict  = {}
_LAST_RESULTS_MAX     = 500   # dead state otherwise grows unbounded — nothing currently reads
                               # this dict (the CSV-export route it was meant for was never
                               # built), but keep a cap so it can't leak memory under sustained load
RESULT_LIMIT          = 6
GO_RESULT_COUNT       = 3

# Job-title/designation words that have no business appearing as a
# "country" — guards against corrupted DB rows (e.g. a scrape/import bug
# that wrote a persona or description string into events.country) ever
# surfacing as a region in the ICP form's geography list or "Switch to:"
# suggestions. A real country/city name never contains these tokens.
_NON_GEO_WORDS = {
    "officer", "chief", "director", "president", "manager", "head",
    "vp", "vice", "ceo", "cfo", "coo", "cto", "cmo", "cio", "chro",
    "founder", "executive", "lead", "specialist", "engineer",
}


def _looks_like_geo(name: str) -> bool:
    import re as _re_mod
    n = (name or "").strip()
    if not n or len(n) > 40:
        return False
    words = [w for w in _re_mod.split(r"[\s,/\-]+", n.lower()) if w]
    if len(words) > 4:
        return False
    return not any(w in _NON_GEO_WORDS for w in words)
CONSIDER_RESULT_COUNT = 3

def _store_last_results(profile_id: str, value: list) -> None:
    if len(_last_results) >= _LAST_RESULTS_MAX:
        for old_id in list(_last_results.keys())[: len(_last_results) - _LAST_RESULTS_MAX + 1]:
            _last_results.pop(old_id, None)
    _last_results[profile_id] = value


_seed_10times_status: dict           = {"running": False, "last_result": None, "last_error": None}
_seed_conferencealerts_status: dict  = {"running": False, "last_result": None, "last_error": None}
_seed_global_status: dict            = {"running": False, "last_result": None, "last_error": None}

# ── Geographic neighbour map (proximity only — counts come from DB live) ──
# Maps every queryable geo to its geographic neighbours in order of proximity.
_GEO_NEIGHBOURS: dict[str, list[str]] = {
    # Southeast Asia
    "indonesia":     ["singapore", "malaysia", "thailand", "vietnam", "philippines", "southeast asia"],
    "vietnam":       ["thailand", "singapore", "malaysia", "philippines", "indonesia", "southeast asia"],
    "philippines":   ["singapore", "malaysia", "indonesia", "thailand", "southeast asia"],
    "myanmar":       ["thailand", "singapore", "malaysia", "southeast asia"],
    "cambodia":      ["thailand", "vietnam", "singapore", "southeast asia"],
    "laos":          ["thailand", "vietnam", "southeast asia"],
    "brunei":        ["singapore", "malaysia", "southeast asia"],
    "timor":         ["indonesia", "singapore", "southeast asia"],
    # South Asia
    "pakistan":      ["india", "uae", "singapore"],
    "bangladesh":    ["india", "singapore"],
    "sri lanka":     ["india", "singapore"],
    "nepal":         ["india"],
    "bhutan":        ["india"],
    "maldives":      ["india", "singapore"],
    # Middle East
    "bahrain":       ["uae", "saudi arabia", "qatar"],
    "kuwait":        ["uae", "saudi arabia"],
    "oman":          ["uae", "saudi arabia"],
    "qatar":         ["uae", "saudi arabia", "bahrain"],
    "jordan":        ["uae", "saudi arabia"],
    "iraq":          ["uae", "saudi arabia"],
    "lebanon":       ["uae"],
    "turkey":        ["germany", "uae", "netherlands"],
    # Africa — extended to global hubs so there's always a suggestion
    "nigeria":       ["south africa", "kenya", "ghana", "egypt", "uae", "uk", "usa"],
    "kenya":         ["south africa", "nigeria", "ethiopia", "egypt", "uae", "india"],
    "ghana":         ["south africa", "nigeria", "senegal", "uae", "uk"],
    "ethiopia":      ["south africa", "kenya", "egypt", "uae"],
    "egypt":         ["uae", "south africa", "kenya", "turkey", "uk"],
    "tanzania":      ["south africa", "kenya", "uae"],
    "rwanda":        ["south africa", "kenya", "uae"],
    "senegal":       ["south africa", "ghana", "uae", "france"],
    "morocco":       ["uae", "south africa", "france", "spain", "uk"],
    "south africa":  ["uae", "uk", "usa", "germany", "kenya"],
    "cameroon":      ["south africa", "nigeria", "uae"],
    "uganda":        ["south africa", "kenya", "uae"],
    "zambia":        ["south africa", "kenya"],
    "zimbabwe":      ["south africa", "kenya"],
    "mozambique":    ["south africa"],
    "angola":        ["south africa", "uae"],
    "ivory coast":   ["south africa", "ghana", "uae"],
    "cote d'ivoire": ["south africa", "ghana", "uae"],
    # Europe (suggest top hubs when smaller country is sparse)
    "austria":       ["germany", "netherlands"],
    "switzerland":   ["germany", "netherlands"],
    "belgium":       ["netherlands", "germany", "france", "uk"],
    "denmark":       ["germany", "netherlands"],
    "sweden":        ["germany", "netherlands"],
    "norway":        ["germany", "netherlands"],
    "finland":       ["germany", "netherlands"],
    "poland":        ["germany"],
    "czech":         ["germany"],
    "hungary":       ["germany"],
    "romania":       ["germany"],
    "portugal":      ["spain", "uk"],
    "ireland":       ["uk", "netherlands"],
    "greece":        ["germany", "netherlands"],
    "croatia":       ["germany"],
    "slovakia":      ["germany"],
    "bulgaria":      ["germany"],
    # Americas
    "mexico":        ["usa"],
    "colombia":      ["usa", "brazil"],
    "argentina":     ["brazil", "usa"],
    "chile":         ["brazil", "usa"],
    "peru":          ["brazil", "usa"],
    "venezuela":     ["usa", "brazil"],
    "ecuador":       ["brazil", "usa"],
    # APAC
    "new zealand":   ["australia"],
    "vietnam":       ["singapore", "thailand", "malaysia"],
    "taiwan":        ["singapore", "japan"],
    "hong kong":     ["singapore", "japan"],
    "sri lanka":     ["india", "singapore"],
}


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


_VERDICT_RANK = {"GO": 0, "CONSIDER": 1, "SKIP": 2}


def _sort_ranked(ranked: list) -> list:
    """
    Final display order: GO events always above CONSIDER, CONSIDER above
    SKIP, then by relevance score within each tier. Sorting by raw score
    alone let a CONSIDER event sit at #1 above a GO event.
    """
    return sorted(
        ranked,
        key=lambda r: (_VERDICT_RANK.get(r.fit_verdict, 3), -(r.relevance_score or 0)),
    )


def _apply_result_mix(ranked: Iterable) -> list:
    """
    Return the genuine GO/CONSIDER matches, verdict-then-score order,
    capped at RESULT_LIMIT (6) — never padded. If only 3 events truly
    match the ICP, show 3; if 40 match, show the top 6; SKIP events are
    never used to pad up to 6.
    """
    all_ranked      = list(ranked)
    go_events       = [r for r in all_ranked if r.fit_verdict == "GO"]
    consider_events = [r for r in all_ranked if r.fit_verdict == "CONSIDER"]
    return (go_events + consider_events)[:RESULT_LIMIT]


def _patch_ranked_with_enrichment(ranked: list, enrichments: dict) -> None:
    """
    Splice SerpAPI enrichment data into already-ranked events in place —
    no LLM call. fit_verdict/verdict_notes/relevance_score/order are
    untouched (frozen from the first ranking pass); only factual display
    fields are updated with the now-known values.
    """
    for r in ranked:
        eid = getattr(r, "event_id", None) or r.id
        data = enrichments.get(eid)
        if not data:
            continue

        att = data.get("est_attendees")
        if att:
            r.est_attendees = att
            if not r.key_numbers or r.key_numbers.strip() in ("", "See event website"):
                r.key_numbers = f"{att:,} attendees"

        price = data.get("price_description")
        if price:
            r.pricing = price

        link = data.get("website") or data.get("registration_url") or data.get("event_link")
        if link:
            r.website     = link
            r.pricing_link = r.pricing_link or link

        desc = data.get("description")
        if desc and (not r.what_its_about or len(r.what_its_about) < 20):
            r.what_its_about = desc[:400]

        r.serpapi_enriched = True


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
    start_date = _iso_date(_csv_value(nr, "start_date", "start", "from_date"))
    end_date   = _iso_date(_csv_value(nr, "end_date", "end", "to_date"))
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
    ind = _csv_value(
        nr, "related_industries", "industry_tags", "industries", "industry",
        "industry relevant for", "relevant_keywords", "relevant keywords",
    )
    src = _csv_value(nr, "source", "source_platform")
    return EventCreate(
        id=event_id, dedup_hash=_csv_dedup_hash(name, start_date, city, country),
        source_platform=src or "CSV_UPLOAD",
        source_url=source_url or f"https://example.com/event/{event_id}",
        name=name, description=_csv_value(nr, "description", "summary"),
        short_summary=_csv_value(
            nr, "short_summary", "two liner description of the event",
            "two-liner description", "short description",
        ),
        edition_number=_csv_value(nr, "edition_number"),
        industry_tags=ind, related_industries=ind,
        audience_personas=_csv_value(
            nr, "audience_personas", "buyer_persona",
            "designations attending", "designation", "designations",
        ),
        start_date=start_date, end_date=end_date or start_date,
        duration_days=_csv_int(nr, "duration_days", default=1),
        venue_name=_csv_value(nr, "venue", "venue_name"), event_venues=_csv_value(nr, "event_venues"),
        event_cities=ec or f"{city}, {country}".strip(", "),
        address=_csv_value(nr, "address"), city=city, country=country,
        is_virtual=_csv_bool(nr, "is_virtual"), is_hybrid=_csv_bool(nr, "is_hybrid"),
        est_attendees=_csv_int(nr, "est_attendees", "estimated_attendees", "attendees", "total attendees"),
        exhibitor_count=_csv_int(nr, "exhibitor_count", "total exhibitors", "exhibitors"),
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


# NOTE: POST /company-profile and GET /company-profile/{id} were removed —
# the company_profiles table stored mostly-empty rows (frontend never
# actually collects founded_year/location/what_we_do/what_we_need, and
# no frontend code ever called GET to reload a saved profile). Retired
# in favor of the analytics_icp_submissions table (models/analytics.py),
# which captures the real per-submission data that mattered.

# ══════════════════════════════════════════════════════════════════════
# POST /api/search  —  REAL-TIME PIPELINE
# ══════════════════════════════════════════════════════════════════════

async def _run_search_pipeline(
    profile: ICPProfile,
    company_context: CompanyContext | None,
    company_profile_id: str | None,
    db: AsyncSession,
) -> dict:
    """
    The actual search pipeline — DB query, scoring, LLM ranking. Runs
    inside a queue worker (see queueing/search_queue.py), NOT directly
    inside the /api/search request/response cycle anymore; see the thin
    POST /api/search below, which only enqueues a job and returns immediately.
    """
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
    # company_profile_id is accepted for backward API compatibility but
    # no longer resolved — the company_profiles table it pointed at was
    # retired (see note above the old /company-profile endpoints).
    company_ctx: CompanyContext | None = company_context

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

    # NOTE: geography is a strict, hard requirement from the ICP form.
    # We intentionally do NOT broaden to neighbouring/regional countries
    # here — if the requested geography has too few (or zero) matching
    # events, the result must stay scoped to that geography rather than
    # silently backfilling with events from other countries.
    region_fallback_note: Optional[str] = None
    original_geos = list(profile.target_geographies or [])

    if not candidates:
        logger.info("No candidates after date filter.")
        _store_last_results(profile_id, [])
        return SearchResponse(profile_id=profile_id, company_name=profile.company_name,
                               total_found=0, events=[], generated_at=datetime.utcnow().isoformat() + "Z")

    logger.info(f"Candidates for scoring: {len(candidates)}")

    # ── Step 5: Semantic scoring ─────────────────────────────────────
    # Preferred: pgvector on Postgres/Neon (persistent, whole-index).
    # Legacy: in-process FAISS (enable_semantic_search) as fallback.
    cosine_scores: dict = {}
    try:
        from relevance import pgvector_store
        if await pgvector_store.is_active_async():
            # Lazily embed this request's candidates (bounded batch),
            # then search the whole index semantically.
            await pgvector_store.embed_missing(db, candidates)
            cosine_scores = await pgvector_store.semantic_scores(
                db, profile,
                date_from=profile.date_from, date_to=profile.date_to,
            )
            # Semantic recall: pull in strong matches the SQL keyword
            # filters missed (bounded, date-window enforced by the query).
            cand_ids = {e.id for e in candidates}
            missing  = [eid for eid, cos in cosine_scores.items()
                        if eid not in cand_ids and cos >= 0.60][:40]
            if missing:
                from sqlalchemy import select as _sel2
                from models.event import EventORM as _ORM2
                extra = (await db.execute(
                    _sel2(_ORM2).where(_ORM2.id.in_(missing))
                )).scalars().all()
                candidates.extend(extra)
                logger.info(f"pgvector recall: +{len(extra)} semantic-only candidates")
    except Exception as exc:
        logger.warning(f"pgvector semantic search (non-fatal): {exc}")

    if not cosine_scores and settings.enable_semantic_search:
        try:
            from relevance.embedder import add_events_to_index, build_profile_text, get_index, search_similar
            idx = get_index()
            if idx.ntotal == 0:
                add_events_to_index(candidates)
            cosine_scores = {r["id"]: r["cosine_score"] for r in search_similar(build_profile_text(profile), top_k=100)}
        except Exception as exc:
            logger.warning(f"Semantic search: {exc}")

    # ── Step 6: Rule-based scoring ───────────────────────────────────
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

    # NOTE: used to build a shared Groq async client here for SerpAPI
    # enrichment (enrichment/serp_enricher.py's optional groq_client
    # param). Enrichment is disabled (DB-only mode) and the LLM gateway
    # moved to OpenAI (relevance/llm_client.py handles its own client),
    # so there's nothing to build.

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
    ranked = _sort_ranked(ranked)

    # ── Step 8: Enforce 6 results (3 GO + 3 CONSIDER, fill with SKIP) ─
    ranked = _apply_result_mix(ranked)
    _store_last_results(profile_id, ranked)

    # ── Step 9: SerpAPI enrichment — only for the 6 final events ──────
    # Cost optimisation: skip events already enriched in DB (serpapi_enriched=True
    # with valid attendees/date). Enrich at most 6 events = 6 SerpAPI calls.
    final_event_ids = {r.id for r in ranked}
    final_top_events = [e for e in top_events if e.id in final_event_ids]

    # SerpAPI enrichment — scoped to attendee-count only. Dates, price,
    # links and descriptions all come from the DB/other sources; SerpAPI
    # (google_ai_mode) is reserved purely for filling in est_attendees on
    # the handful of final shown events, to keep quota use predictable.
    enrichments: dict = {}
    if settings.serpapi_key and final_top_events:
        try:
            import asyncio as _aio_timeout
            from enrichment.serp_enricher import enrich_events_batch
            from db.crud import update_event_enrichment
            try:
                # Defensive bound: bounded concurrency already cuts this to
                # ~30-40s for 6 events, but a stuck SerpAPI/Groq call must
                # never hold the whole search open indefinitely — better to
                # show the 6 events un-enriched than to hang the request.
                enrichments = await _aio_timeout.wait_for(
                    enrich_events_batch(
                        events         = final_top_events,
                        serpapi_key    = settings.serpapi_key,
                        # `groq_client` is a legacy name — it's just a truthy
                        # gate for the LLM-based extraction path, which now
                        # routes through the shared OpenAI gateway
                        # (llm_client.py) internally, not a client object.
                        # Passing None here disables that path entirely and
                        # falls back to weak regex parsing — must stay truthy.
                        groq_client    = True,
                        max_enrich     = len(final_top_events),  # exactly the 6 shown events
                        attendees_only = True,
                    ),
                    # The prior-edition-attendance fallback (added when
                    # attendees are still missing after the first 3 query
                    # strategies) can push a single event's enrichment past
                    # 10-15s including LLM validation; at concurrency=6 for
                    # 6 events that's a single wave, but worst case still
                    # needs real headroom. On timeout wait_for() cancels the
                    # WHOLE batch coroutine, discarding any events that had
                    # already finished — so this budget must comfortably
                    # cover the realistic worst case, not just the typical one.
                    timeout=150,
                )
            except _aio_timeout.TimeoutError:
                logger.warning("SerpAPI enrichment exceeded 150s budget — showing un-enriched results")
                enrichments = {}
            if enrichments:
                logger.info(
                    f"Enriched {len(enrichments)} events — "
                    f"att={sum(1 for d in enrichments.values() if d.get('est_attendees'))}"
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
                            if db_updates:
                                await update_event_enrichment(_db, eid, db_updates)
                _aio.ensure_future(_persist_enrichments())
        except Exception as exc:
            logger.warning(f"SerpAPI enrichment (non-fatal): {exc}")

    # Apply enrichment as a display-only patch — verdict/score/order from
    # the first (and only) LLM ranking pass are frozen here. SerpAPI's own
    # LLM validator (_groq_validate_enrichment in serp_enricher.py) already
    # disambiguates attendee counts from other numbers (years, prices) before
    # they reach `enrichments`, so a plain field copy is safe — no second
    # full rank+validate round-trip needed just to refresh these values.
    if enrichments:
        _patch_ranked_with_enrichment(ranked, enrichments)
        _store_last_results(profile_id, ranked)

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

    # ── Never-empty guarantee ─────────────────────────────────────
    # The frontend hides SKIP verdicts. If every event ended up SKIP
    # (strict rule thresholds + LLM ranker unavailable), the user would
    # get a blank screen after a 60s wait. Promote the closest matches
    # to CONSIDER instead, honestly labelled.
    if ranked and not any(r.fit_verdict in ("GO", "CONSIDER") for r in ranked):
        logger.warning("All final events SKIP — promoting closest matches to CONSIDER")
        for r in sorted(ranked, key=lambda r: r.relevance_score or 0, reverse=True)[:6]:
            r.fit_verdict = "CONSIDER"
            note = (r.verdict_notes or "").strip()
            r.verdict_notes = (
                "Closest match by rule-based scoring - no strong ICP fit found "
                "in this geography/date window, so treat as a starting point. "
                + note
            ).strip()

    go_n  = sum(1 for r in ranked if r.fit_verdict == "GO")
    con_n = sum(1 for r in ranked if r.fit_verdict == "CONSIDER")
    srcs  = {getattr(r, "source_platform", "?") for r in ranked}
    logger.info(f"RESULT: {len(ranked)} events | GO={go_n} CONSIDER={con_n} | sources={srcs}")

    # ── Post-ranking geo coverage check ──────────────────────────────
    # If NONE of the final events match the user's requested geographies,
    # find neighbours that ACTUALLY have ICP-matching events in the DB,
    # return them with live counts so the user can one-click swap.
    suggested_geos: list[dict] = []   # [{geo, count, industries_matched}]
    try:
        from sqlalchemy import select as _sel, func as _sfunc, or_ as _sor
        from models.event import EventORM as _EORM

        _geo_neighbours_ref = globals().get("_GEO_NEIGHBOURS", {})
        _today = date.today().isoformat()

        async def _count_geo_icp(geo: str, industries: list[str]) -> int:
            """Count future events in geo, ICP-filtered then geo-only fallback."""
            geo_l = geo.strip().lower()
            geo_filters = [
                _EORM.country.ilike(f"%{geo_l}%"),
                _EORM.city.ilike(f"%{geo_l}%"),
                _EORM.event_cities.ilike(f"%{geo_l}%"),
            ]
            base_stmt = _sel(_sfunc.count(_EORM.id)).where(
                _EORM.start_date >= _today,
                _sor(*geo_filters),
            )
            if industries:
                ind_filters = []
                for ind in industries[:5]:
                    stem = ind.lower()[:8]
                    ind_filters += [
                        _EORM.industry_tags.ilike(f"%{stem}%"),
                        _EORM.related_industries.ilike(f"%{stem}%"),
                    ]
                result = await db.execute(base_stmt.where(_sor(*ind_filters)))
                cnt = result.scalar() or 0
                if cnt > 0:
                    return cnt
            result = await db.execute(base_stmt)
            return result.scalar() or 0

        async def _live_top_regions(industries: list[str], exclude: list[str], limit: int = 5) -> list[dict]:
            """
            Dynamically query DB for countries with the most future events.
            Works for any user input — no hardcoded list needed.
            Tries ICP industry filter first; falls back to all industries.
            """
            exclude_lower = {g.strip().lower() for g in exclude}

            async def _run(with_ind: bool):
                stmt = (
                    _sel(_EORM.country, _sfunc.count(_EORM.id).label("cnt"))
                    .where(
                        _EORM.start_date >= _today,
                        _EORM.country.isnot(None),
                        _EORM.country != "",
                    )
                    .group_by(_EORM.country)
                    .order_by(_sfunc.count(_EORM.id).desc())
                    .limit(40)
                )
                if with_ind and industries:
                    ind_f = []
                    for ind in industries[:5]:
                        stem = ind.lower()[:8]
                        ind_f += [
                            _EORM.industry_tags.ilike(f"%{stem}%"),
                            _EORM.related_industries.ilike(f"%{stem}%"),
                        ]
                    stmt = stmt.where(_sor(*ind_f))
                rows = (await db.execute(stmt)).fetchall()
                out = []
                for row in rows:
                    country = (row[0] or "").strip()
                    cnt     = row[1] or 0
                    if country and country.lower() not in exclude_lower and cnt > 0:
                        out.append({"geo": country, "count": int(cnt)})
                    if len(out) >= limit:
                        break
                return out

            results = await _run(with_ind=True)
            if not results:
                results = await _run(with_ind=False)
            return results

        async def _build_suggestions(non_global_geos: list[str], icp_industries: list[str]) -> list[dict]:
            """
            Build geo suggestions for any user-entered region:
            1. Check static proximity map (known neighbours)
            2. Fill remaining slots with live DB top-regions query
            """
            suggestions: list[dict] = []
            seen: set[str] = {g.lower() for g in non_global_geos}

            # Step 1: known neighbours from proximity map
            map_nbrs: list[str] = []
            for geo in non_global_geos:
                geo_l = geo.lower().strip()
                for key, nbrs in _geo_neighbours_ref.items():
                    if key in geo_l or geo_l in key or geo_l.startswith(key[:6]):
                        map_nbrs.extend(nbrs)
                        break
            for nbr in list(dict.fromkeys(map_nbrs))[:8]:
                if nbr.lower() not in seen:
                    cnt = await _count_geo_icp(nbr, icp_industries)
                    if cnt > 0:
                        suggestions.append({"geo": nbr.title(), "count": cnt})
                        seen.add(nbr.lower())

            # Step 2: fill with live DB query — handles any region, even unlisted ones
            if len(suggestions) < 5:
                live = await _live_top_regions(
                    industries=icp_industries,
                    exclude=list(seen),
                    limit=5 - len(suggestions),
                )
                suggestions.extend(live)

            suggestions.sort(key=lambda x: -x["count"])
            return suggestions[:5]

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

                if matched == 0 or matched < len(serialised_events) // 2:
                    icp_industries = list(profile.target_industries or [])
                    suggested_geos = await _build_suggestions(non_global_geos, icp_industries)

                    if matched == 0:
                        nbr_str = ", ".join(f"{s['geo']} ({s['count']})" for s in suggested_geos) or "nearby hubs"
                        region_fallback_note = (
                            f"No events found yet in {', '.join(non_global_geos)}. "
                            f"Showing the most relevant global events for your ICP instead. "
                            f"Regions with matching events: {nbr_str}."
                        )
                    else:
                        region_fallback_note = (
                            f"Limited events in {', '.join(non_global_geos)} - "
                            f"showing best global matches to complete your ranking."
                        )

        elif region_fallback_note and original_geos:
            # Early regional fallback already fired — compute live neighbour counts
            non_global_geos = [g for g in original_geos if g.lower() not in ("global", "worldwide", "international")]
            icp_industries   = list(profile.target_industries or [])
            suggested_geos   = await _build_suggestions(non_global_geos, icp_industries)

    except Exception as _geo_err:
        logger.debug(f"Post-ranking geo check: {_geo_err}")

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
    resp_dict["suggested_geos"]        = suggested_geos   # [{geo, count}] live neighbour suggestions
    resp_dict["all_relevant_events"]   = all_relevant_events

    return resp_dict


# ── Queue worker entry point ─────────────────────────────────────────
# Called from queueing/search_queue.worker_loop() (started at app
# startup, see main.py). Runs OUTSIDE any request — must open its own
# DB session, the one that enqueued this job is long gone by the time
# a worker picks it up.
async def _process_search_job(payload: dict) -> dict:
    from db.database import AsyncSessionLocal

    profile = ICPProfile(**payload["profile"])
    company_context = (
        CompanyContext(**payload["company_context"]) if payload.get("company_context") else None
    )
    company_profile_id = payload.get("company_profile_id") or None
    submission_id       = payload.get("submission_id")

    async with AsyncSessionLocal() as db:
        try:
            result = await _run_search_pipeline(profile, company_context, company_profile_id, db)
        except Exception:
            if submission_id:
                async with AsyncSessionLocal() as db_err:
                    await _analytics_track_complete(db_err, submission_id, "error", {}, error="pipeline failed")
            raise

    if submission_id:
        async with AsyncSessionLocal() as db2:
            await _analytics_track_complete(db2, submission_id, "done", result)
    return result


# ══════════════════════════════════════════════════════════════════════
# POST /api/search  —  thin endpoint: rate-limit → persist submission →
# enqueue → return immediately. The real work happens in a background
# worker (queueing/search_queue.worker_loop → _process_search_job above)
# so N simultaneous requests don't all race the same DB pool / OpenAI
# budget inside the request/response cycle at once.
#
# Falls back to running the pipeline inline (old synchronous behavior)
# if REDIS_URL isn't configured — see queueing/search_queue.enqueue().
# ══════════════════════════════════════════════════════════════════════

async def _analytics_track_start(db: AsyncSession, submission_id: str, session_id: str, ip: str, profile) -> None:
    """Best-effort — analytics is a monitoring concern, never allowed to
    fail or slow down a real search."""
    try:
        from db import analytics_crud as _ac
        await _ac.create_icp_submission(db, submission_id, session_id, ip, profile.model_dump())
    except Exception as exc:
        logger.debug(f"analytics submission-start skipped: {exc}")


async def _analytics_track_complete(db: AsyncSession, submission_id: str, status: str, result: dict, error: str = "") -> None:
    try:
        from db import analytics_crud as _ac
        events = (result or {}).get("events", [])
        go       = sum(1 for e in events if e.get("fit_verdict") == "GO")
        consider = sum(1 for e in events if e.get("fit_verdict") == "CONSIDER")
        await _ac.complete_icp_submission(
            db, submission_id, status, total_found=(result or {}).get("total_found", 0),
            go_count=go, consider_count=consider, error=error,
        )
        if events:
            await _ac.record_shown_results(db, submission_id, events)
    except Exception as exc:
        logger.debug(f"analytics submission-complete skipped: {exc}")


@router.post("/search", status_code=202)
async def search_events(
    request: SearchRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
):
    from api.rate_limit import enforce_daily_search_limit
    from queueing.search_queue import enqueue

    profile = request.profile
    ip = await enforce_daily_search_limit(http_request, email=profile.email or "")

    profile_dict = profile.model_dump()
    submission_id = str(uuid.uuid4())
    session_id = http_request.headers.get("x-session-id", "")
    await _analytics_track_start(db, submission_id, session_id, ip, profile)

    payload = {
        "profile":             profile_dict,
        "company_context":     request.company_context.model_dump() if request.company_context else None,
        "company_profile_id":  request.company_profile_id,
        "submission_id":       submission_id,
    }

    job_id = await enqueue(payload)

    if job_id is None:
        # Redis not configured — fall back to running inline, same as
        # before the queue existed. Still logged/persisted the same way.
        logger.warning("search_queue unavailable (no REDIS_URL) — running search inline")
        try:
            result = await _run_search_pipeline(
                profile, request.company_context, request.company_profile_id, db,
            )
        except Exception as exc:
            await _analytics_track_complete(db, submission_id, "error", {}, error=str(exc))
            raise
        await _analytics_track_complete(db, submission_id, "done", result)
        return {"status": "done", "job_id": None, "result": result}

    return {"status": "queued", "job_id": job_id}


@router.get("/search/status/{job_id}")
async def search_status(job_id: str):
    """Poll a queued search job. Returns {status, result, error} —
    status is one of queued|processing|done|error."""
    from queueing.search_queue import get_job

    job = await get_job(job_id)
    if job is None:
        raise HTTPException(404, "Job not found or expired (results are kept for 1 hour)")
    return {"status": job.get("status"), "result": job.get("result"), "error": job.get("error")}


# ══════════════════════════════════════════════════════════════════════
# POST /api/parse-icp  —  LLM-based universal buyer-text parsing
# ══════════════════════════════════════════════════════════════════════

@router.post("/parse-icp")
async def parse_icp(payload: dict):
    """
    Parse a free-text buyer description ("Head of Perioperative Services
    at ambulatory surgery centers") into canonical industries + personas
    via LLM, covering any designation instead of a hardcoded keyword map.

    Degrades gracefully: {"source": "rules"} tells the frontend to keep
    its local keyword-parse result. Never returns an error to the UI.
    """
    text = str(payload.get("text", "") or "").strip()
    if len(text) < 4:
        return {"source": "rules"}
    try:
        from relevance.icp_parser import parse_icp_text
        result = await parse_icp_text(text)
    except Exception as exc:
        logger.warning(f"parse-icp failed (non-fatal): {exc}")
        result = None
    if result is None:
        return {"source": "rules"}
    return {
        "source":         "llm",
        "industries":     result.industries,
        "personas":       result.personas,
        "extra_keywords": result.extra_keywords,
        "seniority":      result.seniority,
        "confidence":     result.confidence,
    }


# ══════════════════════════════════════════════════════════════════════
# GET /api/geo-hint  —  live event counts per geo + neighbour suggestions
# ══════════════════════════════════════════════════════════════════════

@router.get("/geo-hint")
async def geo_hint(
    geos:       str = Query(""),
    industries: str = Query(""),
    personas:   str = Query(""),
    db: AsyncSession = Depends(get_db),
):
    """
    For each requested geography, return:
    - count: how many future events exist in DB for that geo
    - status: 'good' (>=10), 'sparse' (1-9), 'none' (0)
    - suggestions: top neighbour geos with their live counts (when status != 'good')

    Counts are live DB queries — not hardcoded. When industries/personas are
    given, the count strictly requires geo + industry + persona together
    (no silent fallback to a looser number), UNIONed with pgvector semantic
    matches for the same query text (when pgvector is enabled) — the main
    search pipeline can surface an event via semantic similarity alone, so
    this hint counts it too, or it would under-report real coverage.
    `suggestions` applies the same strict-plus-semantic combination, so a
    suggested region always has at least one event that will actually show
    up if the user switches to it.
    """
    from sqlalchemy import select as _sel, or_ as _or
    from models.event import EventORM as _ORM
    import re as _re

    geo_list = [g.strip() for g in geos.split(",") if g.strip()]
    ind_list = [i.strip() for i in industries.split(",") if i.strip()]
    per_list = [p.strip() for p in personas.split(",") if p.strip()]
    if not geo_list:
        return {"coverage": []}

    today = date.today().isoformat()

    def _persona_filters():
        filters = []
        for per in per_list[:5]:
            stem = per.lower()[:8]
            filters += [
                _ORM.audience_personas.ilike(f"%{stem}%"),
                _ORM.description.ilike(f"%{stem}%"),
                _ORM.name.ilike(f"%{stem}%"),
            ]
        return filters

    # ── Semantic recall (pgvector) ──────────────────────────────────
    # The main search pipeline now blends in semantic similarity
    # (score_candidates → pgvector_store.semantic_scores), so an event
    # can clear GO/CONSIDER without ever containing the literal
    # industry/persona keywords the ILIKE filters below look for. If
    # this hint only counted ILIKE hits, it would under-report coverage
    # search will actually find — reintroducing the same
    # hint-vs-reality mismatch already fixed for the ILIKE-only path.
    # Fetched once and reused across every geo/neighbour in this request.
    semantic_rows: list[dict] = []
    if ind_list or per_list:
        try:
            from relevance import pgvector_store
            semantic_rows = await pgvector_store.semantic_matches(
                db, " ".join(ind_list + per_list), date_from=today,
            )
        except Exception as exc:
            logger.debug(f"geo-hint: semantic recall skipped ({exc})")

    def _geo_words(geo: str) -> list[str]:
        return [w for w in _re.split(r"[\s,/\-]+", geo.lower()) if len(w) > 2]

    def _semantic_ids_for_geo(geo: str) -> set[str]:
        words = _geo_words(geo)
        if not words or not semantic_rows:
            return set()
        ids: set[str] = set()
        for row in semantic_rows:
            loc = f"{row['country']} {row['city']} {row['event_cities']}".lower()
            if any(w in loc for w in words):
                ids.add(row["id"])
        return ids

    async def _count_geo(geo: str, with_industries: bool = True, with_personas: bool = True) -> int:
        """Live count of future events for a geo, run through the SAME
        rule-based scorer + GO/CONSIDER tiering the real search pipeline
        uses, then capped at RESULT_LIMIT — the results screen can never
        show more than RESULT_LIMIT events no matter how many "match" in
        a loose keyword sense, so a hint number bigger than that was
        always going to disagree with what's actually shown. Counting
        raw ILIKE/semantic hits (the old approach) let this number report
        candidates that would go on to score as SKIP and never appear.
        """
        geo_l = geo.strip().lower()
        geo_parts = [geo_l]
        if " - " in geo_l:
            geo_parts.extend(p.strip() for p in geo_l.split(" - "))
        geo_filters = []
        for part in geo_parts:
            if len(part) > 1:
                geo_filters.append(_ORM.country.ilike(f"%{part}%"))
                geo_filters.append(_ORM.city.ilike(f"%{part}%"))
                geo_filters.append(_ORM.event_cities.ilike(f"%{part}%"))
        if not geo_filters:
            candidate_ids = set(_semantic_ids_for_geo(geo)) if with_industries and with_personas else set()
        else:
            stmt = _sel(_ORM.id).where(
                _ORM.start_date >= today,
                _or(*geo_filters),
            )

            if with_industries and ind_list:
                ind_filters = []
                for ind in ind_list[:5]:
                    stem = ind.lower()[:8]
                    ind_filters += [
                        _ORM.industry_tags.ilike(f"%{stem}%"),
                        _ORM.related_industries.ilike(f"%{stem}%"),
                    ]
                stmt = stmt.where(_or(*ind_filters))

            per_filters = _persona_filters() if (with_personas and per_list) else []
            if per_filters:
                stmt = stmt.where(_or(*per_filters))

            result = await db.execute(stmt)
            candidate_ids = {row[0] for row in result.all()}

            if with_industries and with_personas:
                candidate_ids |= _semantic_ids_for_geo(geo)

        if not candidate_ids:
            return 0
        if not (with_industries or with_personas):
            # Loose "how many events exist here at all" callers (neighbour
            # suggestions without ind/per context) — raw count is fine,
            # nothing downstream claims these will all be shown.
            return len(candidate_ids)

        from models.event import EventORM as _EvtORM
        from models.icp_profile import ICPProfile as _ICP
        from relevance.scorer import score_candidates as _score_cands, TIER_GO as _GO, TIER_CONSIDER as _CONSIDER

        rows = (await db.execute(
            _sel(_EvtORM).where(_EvtORM.id.in_(list(candidate_ids)[:500]))
        )).scalars().all()
        if not rows:
            return 0

        mini_profile = _ICP(
            company_name="", company_description="",
            target_industries=ind_list if with_industries else [],
            target_personas=per_list if with_personas else [],
            target_geographies=[geo],
            preferred_event_types=[],
        )
        scored = _score_cands(rows, mini_profile, {})
        relevant = sum(1 for _, _, tier, _ in scored if tier in (_GO, _CONSIDER))
        return min(relevant, RESULT_LIMIT)

    async def _top_available_regions(exclude_geos: list[str], limit: int = 5) -> list[dict]:
        """
        Query DB for countries/regions that actually have the most future
        ICP-matching events — fully dynamic, works for any user input.
        Uses the SAME strict geo+industry+persona combination as
        _count_geo above — a looser industry-only or no-filter fallback
        here would show e.g. "India: 2" as a suggestion for a CIO/Fintech
        search, when those 2 events don't actually match the persona, so
        selecting India would then show 0 results. Consistency with what
        the user will actually see beats always having a non-empty list.
        """
        exclude_lower = {g.strip().lower() for g in exclude_geos}

        async def _query_top(with_ind: bool, with_per: bool = False):
            # Fetch id+country rows (not a grouped count) so semantic
            # matches can be unioned per-country without double-counting
            # an event that hits both the ILIKE filter and the vector
            # search — same reasoning as _count_geo above.
            stmt = (
                _sel(_ORM.id, _ORM.country)
                .where(
                    _ORM.start_date >= today,
                    _ORM.country.isnot(None),
                    _ORM.country != "",
                )
                .limit(2000)
            )
            if with_ind and ind_list:
                ind_filters = []
                for ind in ind_list[:5]:
                    stem = ind.lower()[:8]
                    ind_filters += [
                        _ORM.industry_tags.ilike(f"%{stem}%"),
                        _ORM.related_industries.ilike(f"%{stem}%"),
                    ]
                stmt = stmt.where(_or(*ind_filters))
            if with_per and per_list:
                stmt = stmt.where(_or(*_persona_filters()))
            result = await db.execute(stmt)

            ids_by_country: dict[str, set] = {}
            for row in result.all():
                country = (row[1] or "").strip()
                if country:
                    ids_by_country.setdefault(country, set()).add(row[0])

            if with_ind and with_per:
                for row in semantic_rows:
                    country = (row["country"] or "").strip()
                    if country:
                        ids_by_country.setdefault(country, set()).add(row["id"])

            out = [
                {"geo": country, "count": len(ids)}
                for country, ids in ids_by_country.items()
                if country.lower() not in exclude_lower and ids
                and _looks_like_geo(country)
            ]
            out.sort(key=lambda x: -x["count"])
            return out[:limit]

        if per_list:
            # Persona was specified — require geo+industry+persona together,
            # same as _count_geo, so a suggested region always has at least
            # one event that will actually appear if the user switches to it.
            return await _query_top(with_ind=True, with_per=True)
        # No persona given at all — industry(+geo) is the strictest filter
        # that applies, so that's the honest floor here.
        return await _query_top(with_ind=True, with_per=False)

    coverage = []
    for geo in geo_list:
        count = await _count_geo(geo)
        status = "good" if count >= 10 else ("sparse" if count > 0 else "none")

        suggestions = []
        if status != "good":
            geo_l = geo.strip().lower()

            # Step 1: check the static proximity map for known neighbours
            map_neighbours: list[str] = []
            for key, nbrs in _GEO_NEIGHBOURS.items():
                if key in geo_l or geo_l in key or geo_l.startswith(key[:6]):
                    map_neighbours = list(nbrs)
                    break

            # Step 2: count map neighbours that actually have events
            for nbr in map_neighbours[:8]:
                nbr_count = await _count_geo(nbr)
                if nbr_count > 0:
                    suggestions.append({"geo": nbr.title(), "count": nbr_count})

            # Step 3: if map neighbours didn't yield enough, fill with live DB top regions
            if len(suggestions) < 4:
                live_tops = await _top_available_regions(
                    exclude_geos=[geo] + [s["geo"] for s in suggestions],
                    limit=5 - len(suggestions),
                )
                suggestions.extend(live_tops)

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
# GET /api/geo-list  —  live distinct countries actually in the DB, for
# the ICP form's geography autocomplete (replaces/extends the hardcoded
# GEO_OPTIONS list on the frontend so newly-ingested countries show up
# without a frontend deploy, and corrupted country values can never
# appear as a selectable option).
# ══════════════════════════════════════════════════════════════════════

@router.get("/geo-list")
async def geo_list(db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select as _sel, func as _func
    from models.event import EventORM as _ORM

    today = date.today().isoformat()
    result = await db.execute(
        _sel(_ORM.country, _func.count(_ORM.id).label("cnt"))
        .where(
            _ORM.start_date >= today,
            _ORM.country.isnot(None),
            _ORM.country != "",
        )
        .group_by(_ORM.country)
        .order_by(_func.count(_ORM.id).desc())
        .limit(500)
    )
    countries = [
        {"country": (row[0] or "").strip(), "count": row[1] or 0}
        for row in result.all()
        if _looks_like_geo(row[0] or "")
    ]
    return {"countries": countries}


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

    # Live homepage figures — distinct countries and the biggest upcoming
    # shows by attendee count (feeds the landing ticker; nothing hardcoded).
    # Raw country values are scraper dialects (codes, aliases, "City, Country",
    # junk) — normalise before counting or the number is fiction.
    countries_covered = 0
    live_sources = 0
    top_event_names: list = []
    top_locations: list = []
    try:
        from sqlalchemy import select, distinct
        from db.models import EventORM
        from ingestion.geo_normaliser import count_countries, count_source_families
        raw_countries = (await db.execute(
            select(distinct(EventORM.country)).where(EventORM.country != "")
        )).scalars().all()
        countries_covered = count_countries(raw_countries)
        live_sources = count_source_families(by_source.keys())
        today = datetime.utcnow().strftime("%Y-%m-%d")
        loc_rows = (await db.execute(
            select(EventORM.name, EventORM.city, EventORM.country)
            .where(EventORM.start_date >= today, EventORM.name != "")
            .order_by(EventORM.est_attendees.desc())
            .limit(40)
        )).all()
        top_event_names = list(dict.fromkeys(n for n, _, _ in loc_rows))[:12]
        # biggest upcoming shows with a usable location — feeds the hero
        # globe labels (city + normalized country, straight from the DB)
        from ingestion.geo_normaliser import normalise_country
        seen_cities: set = set()
        for name, city, country in loc_rows:
            c_norm = normalise_country(country)
            city = (city or "").strip()
            if not city or not c_norm or city.lower() in seen_cities:
                continue
            seen_cities.add(city.lower())
            top_locations.append({"name": name, "city": city, "country": c_norm})
            if len(top_locations) >= 10:
                break
    except Exception as exc:
        logger.debug(f"stats extras failed: {exc}")

    phq_key = getattr(settings, "predicthq_key", "")
    return {
        "total_events_in_db": total,
        "countries_covered":  countries_covered,
        "live_sources":       live_sources,
        "top_event_names":    top_event_names,
        "top_locations":      top_locations,
        "events_by_source":   by_source,
        "faiss_vectors":      index_size,
        "openai_enabled":     bool(settings.openai_api_key),
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


@router.post("/events/update-from-csv")
async def update_events_from_csv(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    """
    Backfill NEW column data (e.g. designations/industry from a curated
    re-export) onto events that already exist in the DB, matched by
    dedup_hash — unlike /events/upload-csv, which only ever inserts new
    rows and silently skips a row whose dedup_hash already exists.

    For each CSV row:
      - matched by dedup_hash to an existing event → UPDATE only the
        fields this endpoint is meant for (audience_personas always
        overwritten when the CSV has a value — legacy rows have this
        empty; industry_tags/related_industries/short_summary/
        est_attendees/exhibitor_count filled in only where the existing
        value is empty/zero, so a better-curated CSV value never
        clobbers already-good scraped or SerpAPI-enriched data)
      - no match → inserted as a new event, same as /events/upload-csv
    """
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

    updated = 0
    to_insert = []
    for ev in parsed:
        existing = await get_event_by_dedup_hash(db, ev.dedup_hash)
        if existing is None:
            to_insert.append(ev)
            continue
        patch: dict = {}
        if ev.audience_personas:
            patch["audience_personas"] = ev.audience_personas
        if ev.industry_tags and not existing.industry_tags:
            patch["industry_tags"] = ev.industry_tags
        if ev.related_industries and not existing.related_industries:
            patch["related_industries"] = ev.related_industries
        if ev.short_summary and not existing.short_summary:
            patch["short_summary"] = ev.short_summary
        if ev.est_attendees and not existing.est_attendees:
            patch["est_attendees"] = ev.est_attendees
        if ev.exhibitor_count and not existing.exhibitor_count:
            patch["exhibitor_count"] = ev.exhibitor_count
        if patch and await update_event_enrichment(db, existing.id, patch, mark_serpapi_enriched=False):
            updated += 1

    inserted, skipped = (0, 0)
    if to_insert:
        inserted, skipped = await batch_upsert_events(db, to_insert, skip_past=False)

    total = await count_events(db)
    return {
        "message": "CSV backfill processed.", "filename": file.filename,
        "rows_read": len(parsed) + len(errors), "valid_rows": len(parsed),
        "matched_and_updated": updated,
        "new_rows_inserted": inserted,
        "invalid_rows": len(errors), "errors_preview": errors[:20],
        "total_events_in_db": total,
    }


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
