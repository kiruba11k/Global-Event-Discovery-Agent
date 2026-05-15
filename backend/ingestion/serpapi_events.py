"""
ingestion/serpapi_events.py  —  SerpAPI google_events real-time discovery

_infer_tags() is now replaced by groq_tagger.infer_event_tags_batch()
which uses the Groq LLM to classify events into the standard taxonomy.

The LLM:
  - Picks tags ONLY from the fixed INDUSTRY_TAXONOMY list
  - Must cite evidence from the event text (anti-hallucination)
  - Falls back to text matching if Groq unavailable
"""
from __future__ import annotations

import asyncio
import hashlib
import re
import uuid
from datetime import date, datetime
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from loguru import logger

try:
    import serpapi as _serpapi
    _SERPAPI_OK = True
except ImportError:
    _SERPAPI_OK = False

from ingestion.icp_query_builder import SerpAPIQuery
from models.event import EventCreate

_MONTHS = {
    "jan": "01", "january": "01", "feb": "02", "february": "02",
    "mar": "03", "march": "03",   "apr": "04", "april": "04",
    "may": "05", "jun": "06",     "june": "06", "jul": "07", "july": "07",
    "aug": "08", "august": "08",  "sep": "09", "sept": "09", "september": "09",
    "oct": "10", "october": "10", "nov": "11", "november": "11",
    "dec": "12", "december": "12",
}

_COUNTRY_TO_GL = {
    "australia": "au",
    "brazil": "br",
    "canada": "ca",
    "france": "fr",
    "germany": "de",
    "india": "in",
    "indonesia": "id",
    "japan": "jp",
    "malaysia": "my",
    "netherlands": "nl",
    "nigeria": "ng",
    "philippines": "ph",
    "saudi arabia": "sa",
    "singapore": "sg",
    "south africa": "za",
    "south korea": "kr",
    "thailand": "th",
    "uae": "ae",
    "uk": "uk",
    "united kingdom": "uk",
    "usa": "us",
    "united states": "us",
    "vietnam": "vn",
}


def _location_token(location: str) -> str:
    """Return a human search-location token for the google_events query."""
    return " ".join((location or "").replace(",", " ").split())


def _query_includes_location(query: str, location: str) -> bool:
    loc = _location_token(location).lower()
    if not loc:
        return True
    normalized_q = " ".join((query or "").replace(",", " ").split()).lower()
    return loc in normalized_q


def _country_gl(location: str) -> str:
    loc = _location_token(location).lower()
    for country, gl in sorted(_COUNTRY_TO_GL.items(), key=lambda item: len(item[0]), reverse=True):
        if country in loc.split() or country in loc:
            return gl
    return "us"


def _build_google_events_params(qobj: SerpAPIQuery) -> dict[str, str]:
    """Build SerpAPI google_events params using the API's event-location format.

    SerpAPI's Google Events API expects the event city/region to be part of `q`
    (for example, "Events in Austin, TX").  Its `location` parameter is only
    the Google-search origin and must match SerpAPI's canonical locations; our
    short labels such as "New York USA" can produce HTTP 400.  Therefore we
    put the event location in `q` and intentionally omit `location`.
    """
    query = (qobj.q or "").strip()
    location = _location_token(qobj.location)
    if location and not _query_includes_location(query, location):
        query = f"{query} in {location}" if query else f"Events in {location}"

    params = {
        "engine": "google_events",
        "q": query,
        "hl": "en",
        "gl": _country_gl(location),
    }
    return params


def _redact_api_key_from_error(exc: Exception) -> str:
    """Prevent SerpAPI keys from being printed in exception URLs."""
    msg = str(exc)
    match = re.search(r"https?://\S+", msg)
    if not match:
        return msg

    url = match.group(0)
    try:
        split = urlsplit(url)
        query = urlencode(
            (key, "***" if key.lower() == "api_key" else value)
            for key, value in parse_qsl(split.query, keep_blank_values=True)
        )
        redacted = urlunsplit((split.scheme, split.netloc, split.path, query, split.fragment))
        return msg.replace(url, redacted)
    except Exception:
        return re.sub(r"([?&]api_key=)[^&\s]+", r"\1***", msg)


def _parse_when(when: str) -> tuple[str, str]:
    w = (when or "").strip().lower()
    if not w:
        return "", ""

    yr_m = re.search(r"\b(202\d|203\d)\b", w)
    year = yr_m.group(1) if yr_m else str(date.today().year + 1)

    m = re.match(r"([a-z]+)\s+(\d{1,2})\s*[–\-]\s*(\d{1,2}),?\s*(202\d|203\d)?", w)
    if m:
        mon = _MONTHS.get(m.group(1)[:3], "01")
        yr  = m.group(4) or year
        return f"{yr}-{mon}-{m.group(2).zfill(2)}", f"{yr}-{mon}-{m.group(3).zfill(2)}"

    m2 = re.match(r"([a-z]+)\s+(\d{1,2})\s*[–\-]\s*([a-z]+)\s+(\d{1,2}),?\s*(202\d|203\d)?", w)
    if m2:
        sm = _MONTHS.get(m2.group(1)[:3], "01")
        em = _MONTHS.get(m2.group(3)[:3], sm)
        yr = m2.group(5) or year
        return f"{yr}-{sm}-{m2.group(2).zfill(2)}", f"{yr}-{em}-{m2.group(4).zfill(2)}"

    m3 = re.match(r"([a-z]+)\s+(\d{1,2}),?\s*(202\d|203\d)?", w)
    if m3:
        mon = _MONTHS.get(m3.group(1)[:3], "01")
        yr  = m3.group(3) or year
        return f"{yr}-{mon}-{m3.group(2).zfill(2)}", f"{yr}-{mon}-{m3.group(2).zfill(2)}"

    iso = re.search(r"(202\d-\d{2}-\d{2})", w)
    if iso:
        return iso.group(1), iso.group(1)

    return "", ""


def _best_link(ev: dict) -> str:
    for ti in (ev.get("ticket_info") or []):
        lnk = (ti.get("link") or "").strip()
        if lnk and "google.com" not in lnk:
            return lnk
    return (ev.get("link") or "").strip()


def _infer_category(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ["trade show", "expo", "exhibition", "fair", "tradeshow"]): return "trade show"
    if any(w in t for w in ["summit"]):                return "summit"
    if any(w in t for w in ["workshop", "bootcamp"]):  return "workshop"
    if any(w in t for w in ["hackathon"]):             return "hackathon"
    if any(w in t for w in ["meetup", "networking"]):  return "meetup"
    return "conference"


def _to_event_create_raw(
    ev:       dict,
    query:    str,
    location: str,
    temp_id:  str,
) -> Optional[EventCreate]:
    """
    Convert google_events result to EventCreate.
    Tags are set to the search query temporarily;
    they'll be replaced by Groq batch tagging after all events are collected.
    """
    title = (ev.get("title") or "").strip()
    if not title or len(title) < 5:
        return None

    date_block = ev.get("date") or {}
    when       = date_block.get("when") or date_block.get("start_date") or ""
    start, end = _parse_when(when)

    if not start:
        yr_m = re.search(r"\b(202\d|203\d)\b", title + " " + (ev.get("description") or ""))
        if yr_m:
            start = f"{yr_m.group(1)}-01-01"; end = start
        else:
            return None

    today = date.today().isoformat()
    if start < today:
        return None

    addr_list  = ev.get("address") or []
    venue_name = addr_list[0].strip() if addr_list else ""
    city = country = ""
    if len(addr_list) >= 2:
        last   = addr_list[-1]
        parts  = [p.strip() for p in last.split(",") if p.strip()]
        if len(parts) >= 2:
            city, country = parts[-2], parts[-1]
        elif parts:
            city = parts[0]
    if not city:
        parts = [p.strip() for p in location.split(",") if p.strip()]
        city  = parts[0] if parts else location
        country = parts[-1] if len(parts) > 1 else ""

    desc     = (ev.get("description") or "").strip()[:800]
    link     = _best_link(ev)
    duration = 1
    if start and end and start != end:
        try:
            duration = max(1, (datetime.strptime(end, "%Y-%m-%d") - datetime.strptime(start, "%Y-%m-%d")).days + 1)
        except ValueError:
            pass

    dh = hashlib.sha1(f"{title.lower().strip()}|{start}|{city.lower().strip()}".encode()).hexdigest()

    return EventCreate(
        id              = temp_id,
        dedup_hash      = dh,
        source_platform = "SerpAPI_GoogleEvents",
        source_url      = link or f"https://www.google.com/search?q={title.replace(' ', '+')}",
        name            = title,
        description     = desc or f"Event from Google Events search: '{query}' in {location}.",
        short_summary   = desc[:200] if desc else "",
        edition_number  = "",
        start_date      = start,
        end_date        = end or start,
        duration_days   = duration,
        venue_name      = venue_name,
        event_venues    = venue_name,
        address         = ", ".join(addr_list),
        city            = city,
        country         = country,
        event_cities    = f"{city}, {country}".strip(", "),
        is_virtual      = any(v in (title + desc).lower() for v in ["virtual", "online", "webinar"]),
        is_hybrid       = "hybrid" in (title + desc).lower(),
        est_attendees   = 0,
        category        = _infer_category(title + " " + desc),
        # Temporary placeholder — replaced by Groq batch tagging below
        industry_tags   = query,
        related_industries = query,
        audience_personas = "",
        ticket_price_usd = 0.0,
        price_description = "",
        registration_url = link,
        website          = link,
        sponsors = "", speakers_url = "", agenda_url = "",
    )


async def run_serpapi_queries(
    queries:     list[SerpAPIQuery],
    serpapi_key: str,
    date_from:   str = "",
    date_to:     str = "",
) -> list[EventCreate]:
    """
    Execute SerpAPI google_events queries and return deduplicated EventCreate list.
    After fetching, calls Groq batch tagger to assign proper industry tags.
    """
    if not serpapi_key or not _SERPAPI_OK:
        logger.warning("SerpAPI: key missing or serpapi package not installed")
        return []

    today      = date.today().isoformat()
    raw_events: list[EventCreate] = []  # temp list before tagging
    seen:       set[str] = set()
    # id → (query, description) for batch tagging
    events_for_tagging: list[dict] = []

    ok = 0; fail = 0

    for qobj in queries:
        params = _build_google_events_params(qobj)
        try:
            client   = _serpapi.Client(api_key=serpapi_key)
            raw      = await asyncio.to_thread(client.search, params)
            ev_list  = raw.get("events_results", []) or []
            ok      += 1
        except Exception as exc:
            logger.debug(
                f"SerpAPI google_events '{qobj.q}' @ '{qobj.location}' "
                f"with params={params}: {_redact_api_key_from_error(exc)}"
            )
            fail += 1
            await asyncio.sleep(0.3)
            continue

        for ev in ev_list:
            try:
                temp_id = str(uuid.uuid4())
                ec = _to_event_create_raw(ev, qobj.q, qobj.location, temp_id)
                if ec is None:
                    continue
                if date_from and ec.start_date < date_from:
                    continue
                if date_to   and ec.start_date > date_to:
                    continue
                if ec.start_date < today:
                    continue
                if ec.dedup_hash not in seen:
                    seen.add(ec.dedup_hash)
                    raw_events.append(ec)
                    events_for_tagging.append({
                        "id":          ec.id,
                        "title":       ec.name,
                        "description": ec.description,
                        "query":       qobj.q,
                    })
            except Exception as exc2:
                logger.debug(f"SerpAPI parse error: {exc2}")

        await asyncio.sleep(0.4)

    logger.info(
        f"SerpAPI google_events: {len(raw_events)} raw events "
        f"({ok} ok / {fail} failed from {len(queries)} queries)"
    )

    if not raw_events:
        return []

    # ── Groq batch tag inference ────────────────────────────────────
    # Replace the placeholder query-based tags with proper taxonomy tags.
    tagged: dict[str, str] = {}
    try:
        from relevance.groq_tagger import infer_event_tags_batch
        tagged = await infer_event_tags_batch(events_for_tagging, batch_size=20)
        logger.info(f"SerpAPI: Groq tagged {len(tagged)}/{len(raw_events)} events")
    except Exception as exc:
        logger.warning(f"SerpAPI: Groq batch tagging failed ({exc}) — keeping query-based tags")

    # Apply tags to events — EventCreate is a Pydantic model, use model_copy
    final_events: list[EventCreate] = []
    for ec in raw_events:
        tag_str = tagged.get(ec.id, "")
        if tag_str:
            ec = ec.model_copy(update={"industry_tags": tag_str, "related_industries": tag_str})
        final_events.append(ec)
    return final_events
