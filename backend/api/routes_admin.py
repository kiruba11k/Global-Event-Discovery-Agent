"""
api/routes_admin.py  —  Admin-only backend routes

Routes:
  POST /admin/upload-csv              Upload events CSV → smart-upsert to Neon DB
  POST /admin/ingest/ticketmaster     Manually bulk-scrape Ticketmaster → store in DB
  POST /admin/ingest/predicthq        Manually bulk-scrape PredictHQ → store in DB
  GET  /admin/ingest/status           Last-run summary
  GET  /admin/db/count                Event counts by source

Security:
  All routes require  X-Admin-Key: {seed_admin_token}  header
  (reuses the existing seed_admin_token from Settings / .env)

Smart upsert:
  - New event            → INSERT
  - Existing event       → UPDATE only fields where incoming data is better:
      * Empty DB field + real API value           → replace
      * est_attendees: API > DB value             → replace
      * registration_url/website: bad URL in DB  → replace with real URL
      * description: placeholder in DB + real text from API  → replace
      * relevance_score, rationale, ingested_at  → NEVER overwritten
"""
from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import time
import uuid
from datetime import date, datetime
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile
from loguru import logger
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from db.database import get_db
from ingestion.platform_normaliser import normalise
from models.event import EventORM

router   = APIRouter()
settings = get_settings()

_run_log: list[dict] = []
_MAX_LOG = 20


# ─────────────────────────────────────────────────────────────────
# Auth  (reuses existing seed_admin_token from Settings)
# ─────────────────────────────────────────────────────────────────

def _check_admin(request: Request) -> None:
    """
    Reads X-Admin-Key from request headers.
    Tries multiple casings because Render/nginx may normalise header names.
    Token is settings.seed_admin_token from .env / Render env vars.
    """
    token = settings.seed_admin_token or ""
    if not token:
        raise HTTPException(503,
            detail="seed_admin_token not set. Add SEED_ADMIN_TOKEN=yourvalue in Render → Environment Variables.")

    # Try all common header name variants (proxies normalise differently)
    incoming = (
        request.headers.get("x-admin-key")
        or request.headers.get("X-Admin-Key")
        or request.headers.get("x_admin_key")
        or request.headers.get("X_Admin_Key")
        or ""
    ).strip()

    if not incoming:
        raise HTTPException(401,
            detail="Missing X-Admin-Key header. Add header: X-Admin-Key: <your seed_admin_token>")
    if incoming != token.strip():
        raise HTTPException(401,
            detail="Invalid X-Admin-Key. Check seed_admin_token value in Render env vars.")


# ─────────────────────────────────────────────────────────────────
# URL quality helpers
# ─────────────────────────────────────────────────────────────────

_BAD_DOMAINS = frozenset({
    "singaporeexpo.com.sg","excel.london","expoforum-center.ru","fierapordenone.it",
    "twtc.org.tw","thecharlottecountyfair.com","fair.ee","biec.in","necc.co.in",
    "jiexpo.com","bigsight.jp","messe-berlin.de","gouda.nl","uzexpocentre.uz",
    "facebook.com","m.facebook.com","twitter.com","linkedin.com","instagram.com",
    "wikipedia.org","visitumea.se","stazione-leopolda.com",
})

def _is_bad_url(url: str) -> bool:
    if not url: return True
    if url.startswith("https://www.google.com/search"): return True
    try:
        parsed = urlparse(url)
        host   = parsed.netloc.lower().lstrip("www.").lstrip("m.")
        if host in _BAD_DOMAINS: return True
        path = parsed.path.strip("/")
        if not path: return True   # root-domain homepage
    except Exception:
        pass
    return False


# ─────────────────────────────────────────────────────────────────
# Smart merge logic
# ─────────────────────────────────────────────────────────────────

_IMMUTABLE = frozenset({
    "relevance_score", "relevance_tier", "rationale",
    "ingested_at", "confidence_score",
})

_UPDATABLE = [
    "source_url", "name", "description", "category",
    "start_date", "end_date", "venue_name", "city", "country",
    "industry_tags", "audience_personas", "est_attendees",
    "price_description", "registration_url", "website",
    "sponsors", "speakers_url", "agenda_url", "serpapi_enriched",
]


def _should_replace(db_val: Any, api_val: Any, field: str) -> bool:
    if field in _IMMUTABLE:
        return False
    api_empty = api_val is None or api_val == "" or api_val == 0 or api_val is False
    db_empty  = db_val  is None or db_val  == "" or db_val  == 0 or db_val  is False
    if api_empty:
        return False
    if db_empty:
        return True
    if field == "est_attendees":
        try: return int(api_val) > int(db_val)
        except: return False
    if field in ("registration_url", "website", "source_url"):
        return _is_bad_url(str(db_val)) and not _is_bad_url(str(api_val))
    if field == "serpapi_enriched":
        return bool(api_val) is True and bool(db_val) is False
    if field == "description":
        db_s, api_s = str(db_val).strip(), str(api_val).strip()
        placeholder = len(db_s) < 60 or (" — " in db_s and len(db_s) < 100)
        return placeholder and len(api_s) > len(db_s)
    return False


async def _smart_upsert_batch(db: AsyncSession, events: list[dict]) -> dict:
    if not events:
        return {"inserted": 0, "updated": 0, "unchanged": 0, "skipped": 0}

    today = date.today().isoformat()
    inserted = updated = unchanged = skipped = 0

    for ev in events:
        dh = ev.get("dedup_hash", "")
        if not dh:
            skipped += 1
            continue
        start = ev.get("start_date", "")
        if start and start < today:
            skipped += 1
            continue

        result   = await db.execute(select(EventORM).where(EventORM.dedup_hash == dh))
        existing = result.scalar_one_or_none()

        if existing is None:
            try:
                db.add(EventORM(
                    id                = ev.get("id") or str(uuid.uuid4()),
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
                ))
                inserted += 1
            except Exception as exc:
                logger.debug(f"Insert error [{ev.get('name','?')[:40]}]: {exc}")
                skipped += 1
        else:
            patches = {
                f: ev.get(f)
                for f in _UPDATABLE
                if _should_replace(getattr(existing, f, None), ev.get(f), f)
            }
            if patches:
                patches["last_verified_at"] = datetime.utcnow()
                await db.execute(
                    update(EventORM).where(EventORM.dedup_hash == dh).values(**patches)
                )
                updated += 1
            else:
                await db.execute(
                    update(EventORM).where(EventORM.dedup_hash == dh)
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
    text   = content.decode("utf-8-sig", errors="replace")
    sample = text[:2000]
    dialect = "excel-semicolon" if sample.count(";") > sample.count(",") else "excel"
    reader  = csv.DictReader(io.StringIO(text), dialect=dialect)
    rows    = []
    for row in reader:
        row = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
        if not row.get("name", "").strip():
            continue
        rows.append(normalise(row, row.get("source_platform", "CSV_UPLOAD")))
    return rows


# ─────────────────────────────────────────────────────────────────
# Ticketmaster scraping logic (copied from ticketmaster_realtime.py)
# ─────────────────────────────────────────────────────────────────

_TM_BASE   = "https://app.ticketmaster.com/discovery/v2/events.json"
_TM_DETAIL = "https://app.ticketmaster.com/discovery/v2/events/{tm_id}"
_TM_B2B    = ["Conference", "Seminar", "Expo", "Trade Show"]
_TM_SKIP_SEGMENTS = frozenset({
    "Music","Sports","Arts & Theatre","Film","Miscellaneous","Undefined",
})
_TM_DETAIL_SEGMENTS = frozenset({
    "Conference","Business","Technology","Seminar","Expo","Trade Show","Education",
})


def _tm_venue(ev: dict) -> dict:
    return (((ev.get("_embedded") or {}).get("venues", []) or []) or [{}])[0]

def _tm_city(v: dict) -> str:
    return (v.get("city",{}) or {}).get("name","") or (v.get("state",{}) or {}).get("name","") or ""

def _tm_country(v: dict) -> str:
    return (v.get("country",{}) or {}).get("name","") or ""

def _tm_start(ev: dict) -> str:
    return ((ev.get("dates",{}) or {}).get("start",{}) or {}).get("localDate","") or ""

def _tm_end(ev: dict) -> str:
    return ((ev.get("dates",{}) or {}).get("end",{}) or {}).get("localDate","") or ""

def _tm_cancelled(ev: dict) -> bool:
    code = ((ev.get("dates",{}) or {}).get("status",{}) or {}).get("code","") or ""
    return code.lower() in ("cancelled","offsale","postponed")

def _tm_cls(ev: dict) -> tuple:
    cls = (ev.get("classifications",[]) or [{}])[0] or {}
    def _n(k): v=(cls.get(k,{}) or {}).get("name","") or ""; return v if v.lower() not in ("undefined","miscellaneous","") else ""
    return _n("segment"), _n("genre"), _n("subGenre")

def _tm_price(ev: dict) -> str:
    r = (ev.get("priceRanges",[]) or [{}])[0] or {}
    cur,lo,hi = r.get("currency","USD"),r.get("min"),r.get("max")
    if lo is None: return "See website"
    try:
        lo,hi = float(lo),(float(hi) if hi else float(lo))
        if lo==0 and hi==0: return "Free"
        return f"{cur} {lo:,.0f}" if lo==hi else f"From {cur} {lo:,.0f} – {hi:,.0f}"
    except: return "See website"

def _tm_b2b(seg: str, keyword: str) -> bool:
    if seg not in _TM_SKIP_SEGMENTS: return True
    kl = keyword.lower()
    if seg=="Sports" and any(t in kl for t in ("sports business","sports tech","esports")): return True
    if seg=="Music"  and any(t in kl for t in ("music business","music industry","music tech")): return True
    return False

def _tm_parse(ev: dict, detail: dict, keyword: str) -> Optional[dict]:
    name = (ev.get("name") or "").strip()
    if not name: return None
    start = _tm_start(ev)
    if not start or start < date.today().isoformat(): return None
    if _tm_cancelled(ev): return None

    merged  = {**ev, **{k:v for k,v in (detail or {}).items() if v and k not in ("_links","images","sales","promoter","promoters","outlets","seatmap","accessibility","ticketLimit","products","externalLinks","aliases","localizedAliases")}}
    end     = _tm_end(merged) or start
    vdata   = _tm_venue(detail) or _tm_venue(ev)
    city    = _tm_city(vdata)
    country = _tm_country(vdata)
    seg,genre,sub = _tm_cls(detail) if detail else ("","","")
    if not seg: seg,genre,sub = _tm_cls(ev)
    if not _tm_b2b(seg, keyword): return None

    tm_url  = merged.get("url","") or ev.get("url","") or ""
    parts   = [keyword] + [p for p in [seg,genre,sub] if p and p not in [keyword]]
    desc    = next((merged.get(f,"").strip() for f in ("description","info","additionalInfo") if merged.get(f,"").strip()), "") or f"{name} — {seg or 'conference'} in {city}, {country}"
    note    = (merged.get("pleaseNote") or "").strip()
    if note and not desc: desc = note
    desc    = desc[:600]
    cat     = seg.lower() if seg and seg.lower() != "undefined" else "conference"

    return {
        "source_platform":"Ticketmaster","source_url":tm_url,"name":name,
        "description":desc,"category":cat,"start_date":start,"end_date":end,
        "venue_name":(vdata.get("name","") or "").strip(),"city":city,"country":country,
        "industry_tags":", ".join(dict.fromkeys(parts)),
        "audience_personas":"","est_attendees":int(merged.get("capacity") or 0),
        "price_description":_tm_price(detail) or _tm_price(ev) or "See website",
        "registration_url":tm_url,"website":"","sponsors":"",
        "speakers_url":"","agenda_url":"","confidence_score":0.9,
    }


async def _tm_fetch_page(client, api_key, keyword, country_code, start_dt, end_dt, classification, page):
    params = {
        "apikey":api_key,"keyword":keyword,"countryCode":country_code,
        "startDateTime":start_dt,"endDateTime":end_dt,
        "classificationName":classification,"size":"50","page":str(page),
        "sort":"date,asc","locale":"en-us,en,*",
        "includeTest":"no","includeTBA":"no","includeTBD":"no",
    }
    try:
        resp = await client.get(_TM_BASE, params=params)
        if resp.status_code == 401: return [], False, True
        if resp.status_code == 403: return [], False, True
        if resp.status_code != 200: return [], False, False
        body = resp.json()
        evs  = (body.get("_embedded") or {}).get("events",[]) or []
        pi   = body.get("page",{}) or {}
        has_more = page < int(pi.get("totalPages",1)) - 1
        return evs, has_more, False
    except Exception as exc:
        logger.debug(f"TM page error: {exc}")
        return [], False, False


async def _tm_fetch_detail(client, api_key, tm_id):
    try:
        r = await client.get(_TM_DETAIL.format(tm_id=tm_id), params={"apikey":api_key,"locale":"en-us,en,*"})
        return r.json() if r.status_code == 200 else {}
    except: return {}


async def _run_tm_bulk(api_key, kw_list, cc_list, start_dt, end_dt, max_pages):
    today = date.today().isoformat()
    seen: set[str] = set()
    results = []
    abort   = False
    detail_count = 0
    MAX_DETAIL = 30

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(15.0,connect=5.0),
        headers={"User-Agent":"LeadStrategus-Admin/1.0","Accept":"application/json"},
        follow_redirects=True,
    ) as client:
        for q_idx, (kw, cc) in enumerate(
            [(kw, cc) for kw in kw_list for cc in cc_list]
        ):
            if abort or len(results) >= 500: break
            cls = _TM_B2B[q_idx % len(_TM_B2B)]

            for page in range(max_pages):
                if abort or len(results) >= 500: break
                evs, has_more, fatal = await _tm_fetch_page(
                    client, api_key, kw, cc, start_dt, end_dt, cls, page
                )
                if fatal: abort = True; break
                if not evs: break

                for ev in evs:
                    if len(results) >= 500: break
                    start = _tm_start(ev)
                    if not start or start < today: continue

                    seg,genre,_ = _tm_cls(ev)
                    if not _tm_b2b(seg, kw): continue

                    detail: dict = {}
                    has_desc = bool((ev.get("description") or "").strip() or (ev.get("info") or "").strip())
                    if not has_desc and detail_count < MAX_DETAIL and seg in _TM_DETAIL_SEGMENTS:
                        tm_id = ev.get("id","")
                        if tm_id:
                            detail = await _tm_fetch_detail(client, api_key, tm_id)
                            detail_count += 1
                            await asyncio.sleep(0.2)

                    try:
                        raw = _tm_parse(ev, detail, kw)
                        if not raw: continue
                        clean = normalise(raw, "Ticketmaster")
                        dh = clean["dedup_hash"]
                        if dh in seen: continue
                        seen.add(dh); results.append(clean)
                    except Exception as exc:
                        logger.debug(f"TM parse: {exc}")

                if not has_more: break
                await asyncio.sleep(0.25)
            await asyncio.sleep(0.25)

    logger.info(f"TM bulk: {len(results)} events | {detail_count} detail fetches")
    return results


# ─────────────────────────────────────────────────────────────────
# PredictHQ scraping logic (copied from predicthq_realtime.py)
# ─────────────────────────────────────────────────────────────────

_PHQ_BASE       = "https://api.predicthq.com/v1/events/"
_PHQ_B2B_CATS   = "conferences,expos,community"
_PHQ_MIN_ATT    = 100
_PHQ_SKIP_CATS  = frozenset({"concerts","sports","festivals","performing-arts","politics","school-holidays","daylight-savings","academic","airport-delays","disasters","severe-weather","terror","health-warnings"})
_PHQ_B2B_LABELS = frozenset({"business-services","technology","finance-and-investment","healthcare-and-medical","manufacturing","retail-and-consumer-goods","logistics-and-transportation","energy-and-utilities","science-and-research","education-and-training","marketing-and-advertising","real-estate","legal-and-compliance","human-resources","cybersecurity","artificial-intelligence","cloud-computing","data-and-analytics","software-and-saas","fintech","medtech","edtech","proptech","cleantech","ecommerce","supply-chain","procurement","food-and-beverage","trade-show","conference","summit","expo","seminar"})
_PHQ_SKIP_LBLS  = frozenset({"concert","music","sport","festival","holiday","performing-arts","politics","weather","terror"})
_PHQ_CAT_MAP    = {"conferences":"conference","expos":"expo","community":"meetup","performing-arts":"arts","sports":"sports","concerts":"concert","festivals":"festival"}


def _phq_local(ev, f_local, f_utc): return str(ev.get(f_local) or ev.get(f_utc) or "")[:10]

def _phq_city(ev):
    addr = (ev.get("geo",{}) or {}).get("address",{}) or {}
    city = addr.get("locality","") or addr.get("region","") or ""
    if city: return city
    for e in (ev.get("entities",[]) or []):
        if e.get("type") == "city": return e.get("name","")
    return ""

def _phq_country(ev):
    return ((ev.get("geo",{}) or {}).get("address",{}) or {}).get("country_code","") or ev.get("country","") or ""

def _phq_venue(ev):
    for e in (ev.get("entities",[]) or []):
        if e.get("type") == "venue": return (e.get("name","") or "").strip()
    return ""

def _phq_labels(ev):
    raw = ev.get("phq_labels",[]) or []
    return [x["label"] for x in sorted(raw,key=lambda x:x.get("weight",0),reverse=True) if x.get("label")]

def _phq_b2b(ev, keyword):
    state    = (ev.get("state","active") or "active").lower()
    if state in ("deleted","cancelled","postponed"): return False
    cat      = (ev.get("category","") or "").lower()
    plabels  = _phq_labels(ev)
    llabels  = [str(l).lower() for l in (ev.get("labels",[]) or [])]
    kl       = keyword.lower()
    if any(l in _PHQ_B2B_LABELS for l in plabels): return True
    if cat in _PHQ_SKIP_CATS:
        if cat=="sports" and any(t in kl for t in ("sports business","sports tech","esports")): return True
        if cat=="concerts" and any(t in kl for t in ("music business","music industry")): return True
        return False
    if all(l in _PHQ_SKIP_LBLS for l in llabels) and llabels: return False
    att = int(ev.get("phq_attendance") or 0)
    if att > 0 and att < _PHQ_MIN_ATT: return False
    return True

def _phq_parse(ev, keyword):
    title = (ev.get("title") or "").strip()
    if not title or len(title) < 3: return None
    start = _phq_local(ev,"start_local","start")
    end   = _phq_local(ev,"end_local","end") or start
    if not start or start < date.today().isoformat(): return None
    if not _phq_b2b(ev, keyword): return None

    city    = _phq_city(ev)
    country = _phq_country(ev)
    plabels = _phq_labels(ev)
    cat     = (ev.get("category","") or "").lower()
    parts   = ([keyword] if keyword else []) + [
        l.replace("-"," ").title() for l in plabels[:4] if l.replace("-"," ").title() not in ([keyword] if keyword else [])
    ]
    ind = ", ".join(parts) if parts else _PHQ_CAT_MAP.get(cat,"conference").title()
    desc = (ev.get("description") or "").strip()
    if not desc:
        desc = f"{title} — {_PHQ_CAT_MAP.get(cat,cat).title()} in {city}, {country}"
        if keyword: desc += f". Topics: {keyword}"
    desc = desc[:600]

    rank = int(ev.get("rank") or 50)
    conf = round(0.5 + (rank / 100) * 0.45, 2)
    phq_id = ev.get("id","")

    return {
        "source_platform":"PredictHQ","source_url":"","name":title,
        "description":desc,"category":_PHQ_CAT_MAP.get(cat,"conference"),
        "start_date":start,"end_date":end,"venue_name":_phq_venue(ev),
        "city":city,"country":country,"industry_tags":ind,
        "audience_personas":"","est_attendees":int(ev.get("phq_attendance") or 0),
        "price_description":"","registration_url":"","website":"",
        "sponsors":"","speakers_url":"","agenda_url":"","confidence_score":conf,
        "_phq_id": phq_id,
    }


async def _phq_fetch_page(client, api_key, q, country_code, start_gte, end_lte, offset):
    params = {
        "q":q,"category":_PHQ_B2B_CATS,"start.gte":start_gte,"start.lte":end_lte,
        "sort":"-phq_attendance","state":"active",
        "phq_attendance.gte":str(_PHQ_MIN_ATT),"limit":"50","offset":str(offset),
    }
    if country_code: params["country"] = country_code
    try:
        resp  = await client.get(_PHQ_BASE, params=params)
        if resp.status_code == 401: return [], 0, "", True
        if resp.status_code == 403: return [], 0, "", True
        if resp.status_code != 200: return [], 0, "", False
        body = resp.json()
        return body.get("results",[]) or [], int(body.get("count",0)), body.get("next","") or "", False
    except Exception as exc:
        logger.debug(f"PHQ page error: {exc}")
        return [], 0, "", False


async def _run_phq_bulk(api_key, kw_list, cc_list, start_gte, end_lte, max_pages):
    today = date.today().isoformat()
    seen: set[str] = set()
    results = []
    abort   = False

    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    async with httpx.AsyncClient(
        headers=headers, timeout=httpx.Timeout(20.0, connect=5.0), follow_redirects=True
    ) as client:
        for kw, cc in [(kw, cc) for kw in kw_list for cc in cc_list]:
            if abort or len(results) >= 500: break
            for page in range(max_pages):
                if abort or len(results) >= 500: break
                evs, total, next_url, fatal = await _phq_fetch_page(
                    client, api_key, kw, cc, start_gte, end_lte, page * 50
                )
                if fatal: abort = True; break
                if not evs: break

                for ev in evs:
                    if len(results) >= 500: break
                    start = str(ev.get("start_local") or ev.get("start") or "")[:10]
                    if not start or start < today: continue

                    try:
                        raw = _phq_parse(ev, kw)
                        if not raw: continue
                        phq_id = raw.pop("_phq_id", "")
                        if phq_id:
                            raw["dedup_hash"] = hashlib.sha1(f"phq:{phq_id}".encode()).hexdigest()
                        clean = normalise(raw, "PredictHQ")
                        dh = clean["dedup_hash"]
                        if dh in seen: continue
                        seen.add(dh); results.append(clean)
                    except Exception as exc:
                        logger.debug(f"PHQ parse: {exc}")

                if not next_url: break
                await asyncio.sleep(0.3)
            await asyncio.sleep(0.3)

    logger.info(f"PHQ bulk: {len(results)} events")
    return results


# ─────────────────────────────────────────────────────────────────
# Route 1: CSV Upload
# ─────────────────────────────────────────────────────────────────

@router.post("/upload-csv", summary="Upload events CSV to Neon DB")
async def upload_csv(
    file:    UploadFile      = File(...),
    dry_run: bool            = Form(default=False),
    db:      AsyncSession    = Depends(get_db),
    _auth:   None            = Depends(_check_admin),
):
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
        raise HTTPException(422, "No valid rows (all missing 'name')")

    if dry_run:
        return {"dry_run": True, "rows_parsed": len(events),
                "sample": [{"name":e.get("name"),"start_date":e.get("start_date")} for e in events[:5]]}

    t0 = time.perf_counter()
    result  = await _smart_upsert_batch(db, events)
    elapsed = round(time.perf_counter() - t0, 2)
    entry   = {"source":"csv_upload","file":file.filename,"timestamp":datetime.utcnow().isoformat(),"elapsed_s":elapsed,**result}
    _run_log.insert(0, entry); del _run_log[_MAX_LOG:]
    logger.info(f"CSV '{file.filename}': {result} in {elapsed}s")
    return {"file": file.filename, "elapsed_s": elapsed, **result}


# ─────────────────────────────────────────────────────────────────
# Route 2: Manual Ticketmaster bulk ingest
# ─────────────────────────────────────────────────────────────────

@router.post("/ingest/ticketmaster", summary="Manually bulk-scrape Ticketmaster → DB")
async def ingest_ticketmaster(
    keywords:  str  = Form(default="conference,summit,expo,trade show,B2B tech"),
    countries: str  = Form(default="US,GB,SG,IN,DE,AU,AE"),
    date_from: str  = Form(default=""),
    date_to:   str  = Form(default=""),
    max_pages: int  = Form(default=2, description="Pages per query (50 events/page, max 4)"),
    dry_run:   bool = Form(default=False),
    db: AsyncSession = Depends(get_db),
    _auth: None      = Depends(_check_admin),
):
    api_key = settings.ticketmaster_key or ""
    if not api_key:
        raise HTTPException(503, "ticketmaster_key not configured in .env / Render env vars")

    max_pages = min(max_pages, 4)
    today     = date.today().isoformat()
    df        = date_from or today
    dt        = date_to or f"{int(today[:4])+1}{today[4:]}"
    kw_list   = [k.strip() for k in keywords.split(",") if k.strip()]
    cc_list   = [c.strip().upper() for c in countries.split(",") if c.strip()]
    start_dt  = f"{df}T00:00:00Z"
    end_dt    = f"{dt}T23:59:59Z"

    logger.info(f"TM bulk: {len(kw_list)} keywords × {len(cc_list)} countries, max_pages={max_pages}")
    t0 = time.perf_counter()

    events = await _run_tm_bulk(api_key, kw_list, cc_list, start_dt, end_dt, max_pages)

    if dry_run:
        return {"dry_run": True, "events_found": len(events), "elapsed_s": round(time.perf_counter()-t0,2),
                "sample": [{"name":e.get("name"),"start_date":e.get("start_date"),"city":e.get("city"),"country":e.get("country")} for e in events[:5]]}

    result  = await _smart_upsert_batch(db, events)
    elapsed = round(time.perf_counter() - t0, 2)
    entry   = {"source":"ticketmaster","keywords":keywords,"countries":countries,"timestamp":datetime.utcnow().isoformat(),"elapsed_s":elapsed,"events_fetched":len(events),**result}
    _run_log.insert(0, entry); del _run_log[_MAX_LOG:]
    logger.info(f"TM bulk done: fetched={len(events)} {result} in {elapsed}s")
    return {"source":"ticketmaster","events_fetched":len(events),"elapsed_s":elapsed,**result}


# ─────────────────────────────────────────────────────────────────
# Route 3: Manual PredictHQ bulk ingest
# ─────────────────────────────────────────────────────────────────

@router.post("/ingest/predicthq", summary="Manually bulk-scrape PredictHQ → DB")
async def ingest_predicthq(
    keywords:  str  = Form(default="conference,summit,expo,trade show,B2B"),
    countries: str  = Form(default="US,GB,SG,IN,DE,AU,AE"),
    date_from: str  = Form(default=""),
    date_to:   str  = Form(default=""),
    max_pages: int  = Form(default=2, description="Pages per query (50 events/page, max 4)"),
    dry_run:   bool = Form(default=False),
    db: AsyncSession = Depends(get_db),
    _auth: None      = Depends(_check_admin),
):
    api_key = settings.predicthq_key or ""
    if not api_key:
        raise HTTPException(503, "predicthq_key not configured in .env / Render env vars")

    max_pages = min(max_pages, 4)
    today     = date.today().isoformat()
    df        = date_from or today
    dt        = date_to or f"{int(today[:4])+1}{today[4:]}"
    kw_list   = [k.strip() for k in keywords.split(",") if k.strip()]
    cc_list   = [c.strip().upper() for c in countries.split(",") if c.strip()]

    logger.info(f"PHQ bulk: {len(kw_list)} keywords × {len(cc_list)} countries, max_pages={max_pages}")
    t0 = time.perf_counter()

    events = await _run_phq_bulk(api_key, kw_list, cc_list, df, dt, max_pages)

    if dry_run:
        return {"dry_run": True, "events_found": len(events), "elapsed_s": round(time.perf_counter()-t0,2),
                "sample": [{"name":e.get("name"),"start_date":e.get("start_date"),"city":e.get("city"),"est_attendees":e.get("est_attendees"),"industry_tags":e.get("industry_tags")} for e in events[:5]]}

    result  = await _smart_upsert_batch(db, events)
    elapsed = round(time.perf_counter() - t0, 2)
    entry   = {"source":"predicthq","keywords":keywords,"countries":countries,"timestamp":datetime.utcnow().isoformat(),"elapsed_s":elapsed,"events_fetched":len(events),**result}
    _run_log.insert(0, entry); del _run_log[_MAX_LOG:]
    logger.info(f"PHQ bulk done: fetched={len(events)} {result} in {elapsed}s")
    return {"source":"predicthq","events_fetched":len(events),"elapsed_s":elapsed,**result}


# ─────────────────────────────────────────────────────────────────
# Route 4: Status
# ─────────────────────────────────────────────────────────────────

@router.get("/ingest/status", summary="Last ingestion runs summary")
async def ingest_status(_auth: None = Depends(_check_admin)):
    return {"runs": _run_log, "total_runs": len(_run_log)}


@router.get("/profile-store/stats", summary="Profile feedback store statistics")
async def profile_store_stats(
    db: AsyncSession = Depends(get_db),
    _auth: None      = Depends(_check_admin),
):
    """Total rows, unique profiles, top events by recall frequency."""
    try:
        from relevance.profile_store import ProfileFeedback
        total_r  = await db.execute(select(func.count()).select_from(ProfileFeedback))
        total    = total_r.scalar() or 0
        unique_p = await db.execute(
            select(func.count(ProfileFeedback.profile_hash.distinct()))
        )
        unique_profiles = unique_p.scalar() or 0
        # Top 10 events by how many distinct profiles have seen them
        top_r = await db.execute(
            select(ProfileFeedback.event_name, func.count().label("n"))
            .group_by(ProfileFeedback.event_id, ProfileFeedback.event_name)
            .order_by(func.count().desc())
            .limit(10)
        )
        top_events = [{"name": r.event_name, "count": r.n} for r in top_r]
        return {
            "total_feedback_rows": total,
            "unique_profiles":     unique_profiles,
            "top_events":          top_events,
        }
    except Exception as exc:
        return {"error": str(exc)}


@router.post("/profile-store/cleanup", summary="Delete expired profile feedback rows")
async def profile_store_cleanup(
    keep_days: int    = Form(default=365, description="Keep rows newer than this many days"),
    db: AsyncSession  = Depends(get_db),
    _auth: None       = Depends(_check_admin),
):
    """
    Deletes feedback rows where:
    - search_date is older than keep_days ago AND
    - event_start_date has already passed.

    Keeps: recent rows + future events regardless of age.
    """
    from relevance.profile_store import cleanup_expired_feedback
    deleted = await cleanup_expired_feedback(db, keep_days=keep_days)
    return {"deleted_rows": deleted, "keep_days": keep_days}


@router.get("/health/sources", summary="LLM gateway stats + ingestion source health")
async def health_sources(_auth: None = Depends(_check_admin)):
    from dataclasses import asdict

    from ingestion.source_health import source_health
    from relevance.llm_client import llm

    return {"llm": asdict(llm.stats), "sources": source_health.snapshot()}


@router.get("/db/count", summary="Event counts in DB")
async def db_count(db: AsyncSession = Depends(get_db), _auth: None = Depends(_check_admin)):
    total_r    = await db.execute(select(func.count()).select_from(EventORM))
    total      = total_r.scalar() or 0
    platform_r = await db.execute(
        select(EventORM.source_platform, func.count().label("n"))
        .group_by(EventORM.source_platform).order_by(func.count().desc())
    )
    future_r = await db.execute(
        select(func.count()).select_from(EventORM)
        .where(EventORM.start_date >= date.today().isoformat())
    )
    return {
        "total_events":       total,
        "future_events":      future_r.scalar() or 0,
        "events_by_platform": {row.source_platform: row.n for row in platform_r},
    }
