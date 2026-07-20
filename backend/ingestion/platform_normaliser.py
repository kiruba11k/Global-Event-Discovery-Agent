"""
ingestion/platform_normaliser.py
─────────────────────────────────
Single normalisation layer called by every ingestion connector.
Maps raw API/scraper output → clean EventORM-compatible dict.

Each platform returns different field names and URL patterns.
This module resolves them all to the 28-column clean schema so
groq_ranker, serp_enricher, and the scorer always receive
consistent data — no platform-specific branching needed upstream.

Usage:
    from ingestion.platform_normaliser import normalise
    clean = normalise(raw_dict, platform="EventsEye")
    # → ready to pass to crud.upsert_event()

Supported platforms:
    EventsEye   — CSV_UPLOAD + europe/america/asia pacific eventseye batches
    Ticketmaster
    PredictHQ
    Eventbrite
    Seed        — hand-curated seed CSV
    TechCrunch
    Wikipedia   — scraped event list
"""
from __future__ import annotations

import re
import hashlib
from datetime import datetime
from urllib.parse import urlparse
from typing import Any

# ── Venue / social domains that are never event-specific pages ─────
_BAD_DOMAINS: frozenset[str] = frozenset({
    "singaporeexpo.com.sg", "excel.london", "expoforum-center.ru",
    "fierapordenone.it", "twtc.org.tw", "thecharlottecountyfair.com",
    "fair.ee", "biec.in", "necc.co.in", "cticc.co.za",
    "sunteccity.com.sg", "bitec.com", "thelalit.com",
    "marriott.com", "hilton.com", "hyatt.com", "sheratonhotels.com",
    "ihg.com", "accor.com",
    "facebook.com", "m.facebook.com", "fb.com",
    "twitter.com", "x.com", "linkedin.com",
    "instagram.com", "youtube.com", "meetup.com", "wikipedia.org",
    "jiexpo.com", "bigsight.jp", "messe-berlin.de", "gouda.nl",
    "uzexpocentre.uz", "visitumea.se", "stazione-leopolda.com",
    "messe-muenchen.de", "messefrankfurt.com", "koelnmesse.de",
    "bielefeld-messe.de",
})

# ── Known event-platform source domains ───────────────────────────
_PLATFORM_DOMAINS: frozenset[str] = frozenset({
    "eventseye.com",
    "ticketmaster.com", "ticketmaster.co.uk", "ticketmaster.com.au",
    "eventbrite.com",
    "luma.com", "lu.ma",
    "konfhub.com", "townscript.com",
    "techcrunch.com",
})


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def _is_bad_url(url: str) -> bool:
    """True = venue / social / Google-search URL. Don't store as event link."""
    if not url or not isinstance(url, str): return True
    if url.startswith("https://www.google.com/search"): return True
    try:
        host = urlparse(url).netloc.lower().lstrip("www.").lstrip("m.")
        if host in _BAD_DOMAINS: return True
        return any(host.endswith("." + d) for d in _BAD_DOMAINS)
    except Exception:
        return False


def _is_platform_url(url: str) -> bool:
    """True = URL is from a known event platform with a non-root path."""
    if not url: return False
    try:
        parsed = urlparse(url)
        host   = parsed.netloc.lower().lstrip("www.")
        path   = parsed.path.strip("/")
        return any(host == p or host.endswith("." + p)
                   for p in _PLATFORM_DOMAINS) and bool(path)
    except Exception:
        return False


def _clean_description(name: str, desc: str) -> str:
    """Strip 'EVENT NAME - ' or 'EVENT NAME 2026 - ' EventsEye prefix."""
    if not desc: return ""
    prefix_pattern = re.escape(name.strip()) + r"\s*[\-–]\s*"
    cleaned = re.sub("^" + prefix_pattern, "", desc, flags=re.IGNORECASE).strip()
    return cleaned or desc


def _dedup_hash(name: str, start_date: str, city: str) -> str:
    key = f"{name.lower().strip()}|{start_date}|{city.lower().strip()}"
    return hashlib.sha1(key.encode()).hexdigest()


def _normalise_platform_label(raw: str) -> str:
    pl = (raw or "").lower()
    if "eventseye" in pl or pl == "csv_upload": return "EventsEye"
    if "ticketmaster"  in pl: return "Ticketmaster"
    if "predicthq"     in pl: return "PredictHQ"
    if pl == "ita" or "ita trade" in pl or "trade.gov" in pl: return "ITA"
    if "eventbrite"    in pl: return "Eventbrite"
    if "seed"          in pl: return "Seed"
    if "techcrunch"    in pl: return "TechCrunch"
    if "wikipedia"     in pl: return "Wikipedia"
    return raw or "Unknown"


def _iso_date(val: Any) -> str:
    if not val: return ""
    s = str(val).strip()
    # Already ISO
    if re.match(r"\d{4}-\d{2}-\d{2}", s): return s[:10]
    # Try common formats
    for fmt in ("%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%B %d %Y", "%b %d %Y"):
        try: return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except: pass
    return s


# ─────────────────────────────────────────────────────────────────
# Per-platform field maps
# ─────────────────────────────────────────────────────────────────

def _from_eventseye(raw: dict) -> dict:
    """
    EventsEye CSV / batch ingestion.
    source_url = https://www.eventseye.com/fairs/f-{slug}-{id}-1.html
    registration_url = often a venue site → cleared if bad
    """
    name     = str(raw.get("name", "") or "")
    desc     = str(raw.get("description", "") or "")
    src_url  = str(raw.get("source_url", "") or "")
    reg_url  = str(raw.get("registration_url", "") or "")

    # EventsEye source_url IS the event page — always use it
    # registration_url is often a venue — clear it if bad
    clean_reg = reg_url if not _is_bad_url(reg_url) else ""

    return {
        "source_platform":    "EventsEye",
        "source_url":         src_url,
        "name":               name,
        "description":        _clean_description(name, desc),
        "category":           str(raw.get("category", "") or ""),
        "start_date":         _iso_date(raw.get("start_date", "")),
        "end_date":           _iso_date(raw.get("end_date", "")),
        "venue_name":         str(raw.get("venue_name", "") or ""),
        "city":               str(raw.get("city", "") or ""),
        "country":            str(raw.get("country", "") or ""),
        "industry_tags":      str(raw.get("industry_tags", "") or ""),
        "audience_personas":  str(raw.get("audience_personas", "") or ""),
        "est_attendees":      int(raw.get("est_attendees", 0) or 0),
        "price_description":  str(raw.get("price_description", "") or ""),
        "registration_url":   clean_reg,
        "website":            "",        # filled by SerpAPI enrichment
        "sponsors":           str(raw.get("sponsors", "") or ""),
        "speakers_url":       str(raw.get("speakers_url", "") or ""),
        "agenda_url":         str(raw.get("agenda_url", "") or ""),
        "confidence_score":   float(raw.get("confidence_score", 0.8) or 0.8),
    }


def _from_ticketmaster(raw: dict) -> dict:
    """
    Ticketmaster API.
    source_url = https://www.ticketmaster.com/.../event/{id}  — always event-specific
    registration_url = same as source_url
    No est_attendees (API doesn't provide capacity); no industry_tags (use category).
    """
    src_url = str(raw.get("url", "") or raw.get("source_url", "") or "")
    name    = str(raw.get("name", "") or "")

    # Map Ticketmaster classifications to industry_tags
    classifications = raw.get("classifications", [{}])
    segment  = (classifications[0].get("segment", {}) or {}).get("name", "") if classifications else ""
    genre    = (classifications[0].get("genre", {}) or {}).get("name", "") if classifications else ""
    industry = ", ".join(filter(None, [segment, genre])) or str(raw.get("industry_tags", "") or "")

    dates    = raw.get("dates", {}) or {}
    start_dt = dates.get("start", {}) or {}

    venue_info = {}
    embedded   = raw.get("_embedded", {}) or {}
    venues     = embedded.get("venues", [{}])
    if venues:
        venue_info = venues[0] or {}

    city    = (venue_info.get("city", {}) or {}).get("name", "")  or str(raw.get("city", "") or "")
    country = (venue_info.get("country", {}) or {}).get("name", "") or str(raw.get("country", "") or "")

    priceRanges = raw.get("priceRanges", [])
    if priceRanges:
        lo = priceRanges[0].get("min", "")
        hi = priceRanges[0].get("max", "")
        currency = priceRanges[0].get("currency", "USD")
        price_desc = f"From {currency} {lo}" if lo else "See website"
    else:
        price_desc = str(raw.get("price_description", "See website") or "See website")

    return {
        "source_platform":    "Ticketmaster",
        "source_url":         src_url,
        "name":               name,
        "description":        str(raw.get("description", "") or raw.get("info", "") or ""),
        "category":           str(raw.get("type", "conference") or "conference"),
        "start_date":         _iso_date(start_dt.get("localDate", "") or raw.get("start_date", "")),
        "end_date":           _iso_date(raw.get("end_date", "") or start_dt.get("localDate", "")),
        "venue_name":         str(venue_info.get("name", "") or raw.get("venue_name", "") or ""),
        "city":               city,
        "country":            country,
        "industry_tags":      industry,
        "audience_personas":  str(raw.get("audience_personas", "") or ""),
        "est_attendees":      int(raw.get("est_attendees", 0) or 0),
        "price_description":  price_desc,
        "registration_url":   src_url,   # TM source_url IS the ticket/event page
        "website":            "",
        "sponsors":           "",
        "speakers_url":       "",
        "agenda_url":         "",
        "confidence_score":   0.9,
    }


def _from_predicthq(raw: dict) -> dict:
    """
    PredictHQ API.
    source_url: NOT a real event page — PredictHQ has no public event URLs.
                Store the PredictHQ API URL for dedup only; cleared for display.
    registration_url: always empty (PredictHQ doesn't provide them).
    est_attendees: PredictHQ's phq_attendance — the most reliable attendee source.
    city: comes from geo.address.locality or location[1]
    country: geo.country_alpha2
    """
    name      = str(raw.get("title", "") or raw.get("name", "") or "")
    start_str = str(raw.get("start", "") or raw.get("start_date", "") or "")
    end_str   = str(raw.get("end", "") or raw.get("end_date", "") or start_str)

    # PredictHQ geo
    geo = raw.get("geo", {}) or {}
    addr = geo.get("address", {}) or {}
    city    = (addr.get("locality", "") or
               addr.get("region", "") or
               str(raw.get("city", "") or ""))
    country = (geo.get("country_alpha2", "") or
               str(raw.get("country", "") or ""))

    venue  = addr.get("formatted_address", "") or str(raw.get("venue_name", "") or "")
    est_att = int(
        raw.get("phq_attendance") or
        raw.get("est_attendees") or
        raw.get("predicted_attendance") or
        0
    )

    # Category from PredictHQ labels
    labels = raw.get("labels", []) or []
    cat    = labels[0] if labels else str(raw.get("category", "expo") or "expo")

    # Industry from labels
    industry = ", ".join(str(l) for l in labels) if labels else str(raw.get("industry_tags", "Business Events") or "Business Events")

    # PredictHQ has no event URL — source_url is their API ref, not a page
    # We store it for dedup but clear it from link display
    api_url  = str(raw.get("source_url", "") or "")
    # Don't carry Google search URLs through from the original bad ingestion
    clean_src = api_url if not _is_bad_url(api_url) and not api_url.startswith("https://www.google.com/search") else ""

    return {
        "source_platform":    "PredictHQ",
        "source_url":         clean_src,
        "name":               name,
        "description":        str(raw.get("description", "") or f"{name} — {cat} in {city}, {country}. Category: {cat}."),
        "category":           cat,
        "start_date":         _iso_date(start_str),
        "end_date":           _iso_date(end_str),
        "venue_name":         venue,
        "city":               city,
        "country":            country,
        "industry_tags":      industry,
        "audience_personas":  "",       # PredictHQ doesn't provide personas
        "est_attendees":      est_att,  # most reliable — PredictHQ specialty
        "price_description":  "",       # not available
        "registration_url":   "",       # PredictHQ provides no URLs — SerpAPI enriches
        "website":            "",
        "sponsors":           "",
        "speakers_url":       "",
        "agenda_url":         "",
        "confidence_score":   0.75,     # attendance is reliable, rest less so
    }


def _from_eventbrite(raw: dict) -> dict:
    """
    Eventbrite API.
    source_url = https://www.eventbrite.com/e/{slug}-{id}/  — event-specific
    registration_url = same
    """
    src_url = str(raw.get("url", "") or raw.get("source_url", "") or "")
    name    = str((raw.get("name", {}) or {}).get("text", "") or raw.get("name", "") or "")
    desc    = str((raw.get("description", {}) or {}).get("text", "") or raw.get("description", "") or "")

    start = raw.get("start", {}) or {}
    end   = raw.get("end", {}) or {}

    venue = raw.get("venue", {}) or {}
    addr  = venue.get("address", {}) or {}
    city    = addr.get("city", "") or str(raw.get("city", "") or "")
    country = addr.get("country", "") or str(raw.get("country", "") or "")

    # Ticket class for price
    ticket_classes = raw.get("ticket_classes", [])
    if ticket_classes:
        cost = (ticket_classes[0].get("cost", {}) or {}).get("display", "")
        price_desc = cost or "See website"
    else:
        price_desc = str(raw.get("price_description", "") or "")

    return {
        "source_platform":    "Eventbrite",
        "source_url":         src_url,
        "name":               name,
        "description":        desc,
        "category":           str(raw.get("format", {}).get("name", "event") if isinstance(raw.get("format"), dict) else raw.get("category", "event")),
        "start_date":         _iso_date(start.get("local", "") or start.get("utc", "")),
        "end_date":           _iso_date(end.get("local", "") or end.get("utc", "")),
        "venue_name":         str(venue.get("name", "") or raw.get("venue_name", "") or ""),
        "city":               city,
        "country":            country,
        "industry_tags":      str(raw.get("industry_tags", "") or ""),
        "audience_personas":  str(raw.get("audience_personas", "") or ""),
        "est_attendees":      int(raw.get("capacity", 0) or raw.get("est_attendees", 0) or 0),
        "price_description":  price_desc,
        "registration_url":   src_url,   # Eventbrite URL IS the ticket page
        "website":            "",
        "sponsors":           "",
        "speakers_url":       "",
        "agenda_url":         "",
        "confidence_score":   0.85,
    }


def _from_seed(raw: dict) -> dict:
    """
    Hand-curated Seed CSV / internal list.
    Has best audience_personas and est_attendees.
    source_url / registration_url may be organiser homepage — clear if bad.
    """
    name    = str(raw.get("name", "") or "")
    src_url = str(raw.get("source_url", "") or "")
    reg_url = str(raw.get("registration_url", "") or "")

    # For seed events, prefer registration_url over source_url if it's deeper
    clean_reg = reg_url if not _is_bad_url(reg_url) and reg_url != src_url else ""
    clean_src = src_url if not _is_bad_url(src_url) else ""

    return {
        "source_platform":    "Seed",
        "source_url":         clean_src,
        "name":               name,
        "description":        str(raw.get("description", "") or ""),
        "category":           str(raw.get("category", "summit") or "summit"),
        "start_date":         _iso_date(raw.get("start_date", "")),
        "end_date":           _iso_date(raw.get("end_date", "") or raw.get("start_date", "")),
        "venue_name":         str(raw.get("venue_name", "") or ""),
        "city":               str(raw.get("city", "") or ""),
        "country":            str(raw.get("country", "") or ""),
        "industry_tags":      str(raw.get("industry_tags", "") or ""),
        "audience_personas":  str(raw.get("audience_personas", "") or ""),
        "est_attendees":      int(raw.get("est_attendees", 0) or 0),
        "price_description":  str(raw.get("price_description", "") or ""),
        "registration_url":   clean_reg,
        "website":            "",
        "sponsors":           str(raw.get("sponsors", "") or ""),
        "speakers_url":       str(raw.get("speakers_url", "") or ""),
        "agenda_url":         str(raw.get("agenda_url", "") or ""),
        "confidence_score":   float(raw.get("confidence_score", 0.95) or 0.95),
    }


def _from_ita(raw: dict) -> dict:
    """
    ITA Trade Events API (data.trade.gov).
    ita_trade_events.py's _parse_event() already produces the flattened
    28-column shape, so this mostly passes fields through with cleanup.
    """
    name    = str(raw.get("name", "") or "")
    src_url = str(raw.get("source_url", "") or "")
    reg_url = str(raw.get("registration_url", "") or "")
    clean_src = src_url if not _is_bad_url(src_url) else ""
    clean_reg = reg_url if not _is_bad_url(reg_url) else ""

    return {
        "source_platform":    "ITA",
        "source_url":         clean_src,
        "name":               name,
        "description":        str(raw.get("description", "") or ""),
        "category":           str(raw.get("category", "") or "conference"),
        "start_date":         _iso_date(raw.get("start_date", "")),
        "end_date":           _iso_date(raw.get("end_date", "") or raw.get("start_date", "")),
        "venue_name":         str(raw.get("venue_name", "") or ""),
        "city":               str(raw.get("city", "") or ""),
        "country":            str(raw.get("country", "") or ""),
        "industry_tags":      str(raw.get("industry_tags", "") or ""),
        "audience_personas":  "",       # ITA doesn't provide buyer personas
        "est_attendees":      int(raw.get("est_attendees", 0) or 0),
        "price_description":  str(raw.get("price_description", "") or ""),
        "registration_url":   clean_reg,
        "website":            str(raw.get("website", "") or clean_src),
        "sponsors":           "",
        "speakers_url":       "",
        "agenda_url":         "",
        "confidence_score":   float(raw.get("confidence_score", 0.7) or 0.7),
    }


def _from_generic(raw: dict, platform: str) -> dict:
    """Fallback for TechCrunch, Wikipedia, and any future source."""
    name    = str(raw.get("name", "") or "")
    src_url = str(raw.get("source_url", "") or "")
    reg_url = str(raw.get("registration_url", "") or "")
    clean_reg = reg_url if not _is_bad_url(reg_url) else ""

    return {
        "source_platform":    _normalise_platform_label(platform),
        "source_url":         src_url,
        "name":               name,
        "description":        str(raw.get("description", "") or ""),
        "category":           str(raw.get("category", "") or ""),
        "start_date":         _iso_date(raw.get("start_date", "")),
        "end_date":           _iso_date(raw.get("end_date", "") or raw.get("start_date", "")),
        "venue_name":         str(raw.get("venue_name", "") or ""),
        "city":               str(raw.get("city", "") or ""),
        "country":            str(raw.get("country", "") or ""),
        "industry_tags":      str(raw.get("industry_tags", "") or ""),
        "audience_personas":  str(raw.get("audience_personas", "") or ""),
        "est_attendees":      int(raw.get("est_attendees", 0) or 0),
        "price_description":  str(raw.get("price_description", "") or ""),
        "registration_url":   clean_reg,
        "website":            "",
        "sponsors":           str(raw.get("sponsors", "") or ""),
        "speakers_url":       str(raw.get("speakers_url", "") or ""),
        "agenda_url":         str(raw.get("agenda_url", "") or ""),
        "confidence_score":   float(raw.get("confidence_score", 0.8) or 0.8),
    }


# ─────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────

def normalise(raw: dict, platform: str = "") -> dict:
    """
    Convert raw API / scraper output to clean 28-column EventORM dict.

    Args:
        raw:      Raw dict from any scraper/API connector.
        platform: Source platform string (case-insensitive).
                  If absent, inferred from raw['source_platform'] or raw['source_url'].

    Returns:
        dict ready to pass to crud.upsert_event() — all 28 columns present,
        no None values (empty string / 0 / False for missing fields).
    """
    # Infer platform if not given
    if not platform:
        platform = str(
            raw.get("source_platform", "") or
            raw.get("platform", "") or ""
        )
    platform_norm = _normalise_platform_label(platform)

    # Dispatch to platform-specific normaliser
    if platform_norm == "EventsEye":
        data = _from_eventseye(raw)
    elif platform_norm == "Ticketmaster":
        data = _from_ticketmaster(raw)
    elif platform_norm == "PredictHQ":
        data = _from_predicthq(raw)
    elif platform_norm == "Eventbrite":
        data = _from_eventbrite(raw)
    elif platform_norm == "Seed":
        data = _from_seed(raw)
    elif platform_norm == "ITA":
        data = _from_ita(raw)
    else:
        data = _from_generic(raw, platform)

    # Generate dedup_hash if not provided
    if not raw.get("dedup_hash"):
        data["dedup_hash"] = _dedup_hash(
            data.get("name", ""),
            data.get("start_date", ""),
            data.get("city", ""),
        )
    else:
        data["dedup_hash"] = str(raw["dedup_hash"])

    # Preserve existing id if provided
    if raw.get("id"):
        data["id"] = str(raw["id"])

    # Scoring fields: preserve existing values, don't overwrite
    for field, default in [
        ("relevance_score", 0.0),
        ("relevance_tier", ""),
        ("rationale", ""),
        ("serpapi_enriched", False),
    ]:
        if field not in data:
            data[field] = raw.get(field, default)

    # Timestamps
    now = datetime.utcnow().isoformat()
    data["ingested_at"]      = raw.get("ingested_at", now)
    data["last_verified_at"] = raw.get("last_verified_at", now)

    return data
