"""
EventsEye global event seeder.

Scrapes eventseye.com across all industries and all regions.
Only stores upcoming events (start_date >= today).
Deduplicates by name+date+city hash.
Works with both SQLite (local) and PostgreSQL (Neon/Render production).

API endpoint: POST /api/seed-eventseye
Protected by X-Seed-Token header.

Usage (CLI):
    python backend/scripts/seed_eventseye_global.py --dry-run
    python backend/scripts/seed_eventseye_global.py --max-pages 5
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import random
import re
import sys
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, UTC
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse, urlencode, parse_qsl, urlunparse

import httpx
from bs4 import BeautifulSoup
from loguru import logger

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from db.crud import batch_upsert_events, count_events          # noqa: E402
from db.database import AsyncSessionLocal, init_db             # noqa: E402
from models.event import EventCreate                           # noqa: E402

SOURCE = "EventsEye"
BASE   = "https://www.eventseye.com"

# ── Rotate user-agents to reduce 403s ──────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
]

# ── Seed entry-point URLs across ALL regions and ALL industries ──────
SEED_URLS: list[str] = [
    # Root / discovery
    f"{BASE}/fairs/",
    f"{BASE}/",
    # Regions
    f"{BASE}/fairs/zt1_trade-shows_america.html",
    f"{BASE}/fairs/zt2_trade-shows_europe.html",
    f"{BASE}/fairs/zt3_trade-shows_asia-pacific.html",
    f"{BASE}/fairs/zt4_trade-shows_africa-middle-east.html",
    # Major country pages (actual EventsEye URL pattern)
    f"{BASE}/fairs/ct1_trade-shows_usa-united-states-of-america.html",
    f"{BASE}/fairs/ct2_trade-shows_germany.html",
    f"{BASE}/fairs/ct3_trade-shows_united-kingdom.html",
    f"{BASE}/fairs/ct4_trade-shows_france.html",
    f"{BASE}/fairs/ct5_trade-shows_italy.html",
    f"{BASE}/fairs/ct6_trade-shows_spain.html",
    f"{BASE}/fairs/ct7_trade-shows_china.html",
    f"{BASE}/fairs/ct8_trade-shows_japan.html",
    f"{BASE}/fairs/ct9_trade-shows_india.html",
    f"{BASE}/fairs/ct10_trade-shows_uae.html",
    f"{BASE}/fairs/ct11_trade-shows_singapore.html",
    f"{BASE}/fairs/ct12_trade-shows_australia.html",
    f"{BASE}/fairs/ct13_trade-shows_canada.html",
    f"{BASE}/fairs/ct14_trade-shows_netherlands.html",
    f"{BASE}/fairs/ct15_trade-shows_brazil.html",
    f"{BASE}/fairs/ct16_trade-shows_south-africa.html",
    f"{BASE}/fairs/ct17_trade-shows_south-korea.html",
    # Industry pages
    f"{BASE}/fairs/ci1_trade-shows_technology-it.html",
    f"{BASE}/fairs/ci2_trade-shows_finance-banking.html",
    f"{BASE}/fairs/ci3_trade-shows_healthcare-medical.html",
    f"{BASE}/fairs/ci4_trade-shows_energy-environment.html",
    f"{BASE}/fairs/ci5_trade-shows_food-beverage.html",
    f"{BASE}/fairs/ci6_trade-shows_retail-ecommerce.html",
    f"{BASE}/fairs/ci7_trade-shows_manufacturing-engineering.html",
    f"{BASE}/fairs/ci8_trade-shows_transport-logistics.html",
    f"{BASE}/fairs/ci9_trade-shows_construction-real-estate.html",
    f"{BASE}/fairs/ci10_trade-shows_agriculture.html",
    f"{BASE}/fairs/ci11_trade-shows_aerospace-defence.html",
    f"{BASE}/fairs/ci12_trade-shows_fashion-textile.html",
    f"{BASE}/fairs/ci13_trade-shows_tourism-hospitality.html",
    f"{BASE}/fairs/ci14_trade-shows_chemicals-plastics.html",
    f"{BASE}/fairs/ci15_trade-shows_mining-metals.html",
    f"{BASE}/fairs/ci16_trade-shows_education-training.html",
    f"{BASE}/fairs/ci17_trade-shows_media-publishing.html",
    f"{BASE}/fairs/ci18_trade-shows_sports-recreation.html",
    f"{BASE}/fairs/ci19_trade-shows_beauty-cosmetics.html",
    f"{BASE}/fairs/ci20_trade-shows_automotive.html",
    f"{BASE}/fairs/ci21_trade-shows_electronics.html",
    f"{BASE}/fairs/ci22_trade-shows_security.html",
    # Direct fair listing
    f"{BASE}/fairs/index.html",
]

MONTHS = {
    "jan":"01","january":"01","feb":"02","february":"02",
    "mar":"03","march":"03","apr":"04","april":"04","may":"05",
    "jun":"06","june":"06","jul":"07","july":"07","aug":"08","august":"08",
    "sep":"09","sept":"09","september":"09","oct":"10","october":"10",
    "nov":"11","november":"11","dec":"12","december":"12",
}

CARD_SELECTORS = (
    "div.event-item","div.event-card","li.event",
    "article.event","tr[class*='fair']","tr[data-id]",
    "div[class*='fair']","div[class*='event']",
    "td.fair-name","table.fair-list tr",
)
TITLE_SELECTORS = (
    "h1","h2","h3",".event-title",".fair-name","a.event-title",
    "td.fair-name a","a[href*='/f']",".name",
)
DATE_SELECTORS  = ("time",".date",".event-date",".dates","td.date","[class*='date']",)
LOC_SELECTORS   = (".location",".venue",".city","td.location","[class*='venue']","[class*='city']",)


@dataclass
class CrawlConfig:
    max_pages:      int   = 60
    delay_seconds:  float = 2.0
    timeout:        float = 20.0
    dry_run:        bool  = False
    concurrency:    int   = 2
    extra_urls:     list  = field(default_factory=list)


def _clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _parse_date(text: str) -> tuple[str, str, int]:
    """Returns (start_date, end_date, duration_days) as ISO strings."""
    t = _clean(text).lower()
    if not t:
        return "", "", 1
    # ISO dates
    isos = re.findall(r"\d{4}-\d{2}-\d{2}", t)
    if isos:
        return isos[0], isos[-1], max(1, len(set(isos)))
    # Month DD[-DD], YYYY
    m = re.search(
        r"(jan\w*|feb\w*|mar\w*|apr\w*|may|jun\w*|jul\w*|aug\w*|sep\w*|oct\w*|nov\w*|dec\w*)"
        r"\.?\s+(\d{1,2})(?:\s*[-–]\s*(\d{1,2}))?,?\s+(20\d{2})", t
    )
    if m:
        mon = MONTHS.get(m.group(1)[:3], "01")
        sd  = m.group(2).zfill(2)
        ed  = (m.group(3) or m.group(2)).zfill(2)
        yr  = m.group(4)
        dur = max(1, int(ed) - int(sd) + 1) if ed >= sd else 1
        return f"{yr}-{mon}-{sd}", f"{yr}-{mon}-{ed}", dur
    # DD[-DD] Month YYYY
    m2 = re.search(
        r"(\d{1,2})(?:\s*[-–]\s*(\d{1,2}))?\s+"
        r"(jan\w*|feb\w*|mar\w*|apr\w*|may|jun\w*|jul\w*|aug\w*|sep\w*|oct\w*|nov\w*|dec\w*)"
        r"\.?\s+(20\d{2})", t
    )
    if m2:
        mon = MONTHS.get(m2.group(3)[:3], "01")
        sd  = m2.group(1).zfill(2)
        ed  = (m2.group(2) or m2.group(1)).zfill(2)
        yr  = m2.group(4)
        dur = max(1, int(ed) - int(sd) + 1) if ed >= sd else 1
        return f"{yr}-{mon}-{sd}", f"{yr}-{mon}-{ed}", dur
    return "", "", 1


def _parse_loc(text: str) -> tuple[str, str]:
    t     = _clean(text)
    parts = [p.strip() for p in re.split(r",|·|\|", t) if p.strip()]
    return (parts[0], parts[-1]) if len(parts) > 1 else (parts[0] if parts else "", "")


def _make_hash(name: str, start_date: str, city: str) -> str:
    raw = f"{name.lower().strip()}|{start_date}|{city.lower().strip()}"
    return hashlib.md5(raw.encode()).hexdigest()


def _abs(href: str, base: str = BASE) -> str:
    return urljoin(base, href)


def _first_text(soup, selectors: Iterable[str]) -> str:
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            t = _clean(el.get_text(" ", strip=True))
            if t:
                return t
    return ""


def _infer_industry(url: str, name: str) -> str:
    mapping = {
        "technology": "tech,IT,software", "finance": "finance,banking,fintech",
        "healthcare": "healthcare,medtech,pharma", "energy": "energy,cleantech,oil",
        "food": "food,FMCG,beverage", "retail": "retail,ecommerce,consumer goods",
        "manufacturing": "manufacturing,industrial,automation",
        "transport": "logistics,transport,supply chain",
        "construction": "construction,real estate", "agriculture": "agriculture,agritech",
        "aerospace": "aerospace,defence", "fashion": "fashion,textile,apparel",
        "tourism": "travel,tourism,hospitality", "automotive": "automotive,EV",
        "electronics": "electronics,semiconductors", "security": "cybersecurity,security",
        "education": "education,HR,training", "media": "media,publishing",
    }
    combined = (url + " " + name).lower()
    for key, tags in mapping.items():
        if key in combined:
            return tags
    return "trade show,business events"


def _parse_json_ld(soup: BeautifulSoup, page_url: str) -> list[EventCreate]:
    """Extract events from JSON-LD structured data — most reliable method."""
    events: list[EventCreate] = []
    today  = date.today().isoformat()
    for script in soup.select("script[type='application/ld+json']"):
        raw = (script.string or script.get_text(strip=True)).strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        nodes = payload if isinstance(payload, list) else [payload]
        for node in nodes:
            graph = node.get("@graph") if isinstance(node, dict) else None
            for item in (graph if isinstance(graph, list) else [node]):
                if not isinstance(item, dict):
                    continue
                t = item.get("@type", "")
                if "Event" not in (t if isinstance(t, str) else " ".join(t)):
                    continue
                name  = _clean(item.get("name"))
                start, end, dur = _parse_date(str(item.get("startDate", "")))
                if not name or not start or start < today:
                    continue
                loc   = item.get("location") or {}
                addr  = loc.get("address", {}) if isinstance(loc, dict) else {}
                city  = _clean(addr.get("addressLocality", "")) if isinstance(addr, dict) else ""
                ctry  = _clean(addr.get("addressCountry", "")) if isinstance(addr, dict) else ""
                venue = _clean(loc.get("name", "")) if isinstance(loc, dict) else ""
                link  = _clean(str(item.get("url", page_url)))
                events.append(EventCreate(
                    id=str(uuid.uuid4()), source_platform=SOURCE,
                    source_url=link, dedup_hash=_make_hash(name, start, city),
                    name=name,
                    description=_clean(item.get("description", ""))[:500] or f"Trade show / expo sourced from EventsEye.",
                    short_summary="", edition_number="",
                    start_date=start, end_date=end or start, duration_days=dur,
                    venue_name=venue, address="", city=city, country=ctry,
                    is_virtual=False, is_hybrid=False, est_attendees=2000,
                    category="trade show", industry_tags=_infer_industry(link, name),
                    audience_personas="executives,trade buyers,industry professionals",
                    ticket_price_usd=0.0, price_description="See website",
                    registration_url=link, sponsors="", speakers_url="", agenda_url="",
                ))
    return events


def _parse_html_cards(soup: BeautifulSoup, page_url: str) -> list[EventCreate]:
    """Fallback: parse visible HTML event cards / table rows."""
    events: list[EventCreate] = []
    today  = date.today().isoformat()
    seen:  set[str] = set()

    cards: list = []
    for sel in CARD_SELECTORS:
        found = soup.select(sel)
        if found:
            cards.extend(found)
    if not cards:
        cards = soup.select("tr, article, li, div")

    for card in cards[:80]:
        txt = _clean(card.get_text(" ", strip=True))
        if len(txt) < 15:
            continue
        name = _first_text(card, TITLE_SELECTORS)
        if not name or len(name) < 4:
            continue
        date_txt = _first_text(card, DATE_SELECTORS) or txt
        start, end, dur = _parse_date(date_txt)
        if not start or start < today:
            continue
        loc_txt   = _first_text(card, LOC_SELECTORS)
        city, ctry = _parse_loc(loc_txt)
        # Event link
        a = card.select_one("a[href]")
        link = _abs(a["href"]) if a and a.get("href") else page_url
        dh = _make_hash(name, start, city)
        if dh in seen:
            continue
        seen.add(dh)
        events.append(EventCreate(
            id=str(uuid.uuid4()), source_platform=SOURCE,
            source_url=link, dedup_hash=dh, name=name[:250],
            description=f"Trade show / expo sourced from EventsEye.",
            short_summary="", edition_number="",
            start_date=start, end_date=end or start, duration_days=dur,
            venue_name="", address="", city=city, country=ctry,
            is_virtual=False, is_hybrid=False, est_attendees=2000,
            category="trade show", industry_tags=_infer_industry(link, name),
            audience_personas="executives,trade buyers,industry professionals",
            ticket_price_usd=0.0, price_description="See website",
            registration_url=link, sponsors="", speakers_url="", agenda_url="",
        ))
    return events


def _discover_listing_urls(soup: BeautifulSoup, page_url: str) -> list[str]:
    """Find more fair-listing pages from navigation links on this page."""
    found: list[str] = []
    domain = urlparse(BASE).netloc
    for a in soup.select("a[href]"):
        href = _abs(a.get("href", ""), page_url)
        p    = urlparse(href)
        if p.netloc != domain:
            continue
        path = p.path.lower()
        if any(k in path for k in ("/fairs/", "/trade-shows/", "/exhibitions/", "/conferences/")):
            # Remove tracking params
            clean = urlunparse((p.scheme, p.netloc, p.path, "", "", ""))
            found.append(clean)
    return list(dict.fromkeys(found))[:20]


async def _fetch(client: httpx.AsyncClient, url: str, cfg: CrawlConfig) -> str:
    ua = random.choice(USER_AGENTS)
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": BASE + "/",
    }
    for attempt in range(3):
        await asyncio.sleep(cfg.delay_seconds + random.uniform(0, 0.8))
        try:
            r = await client.get(url, headers=headers, timeout=cfg.timeout, follow_redirects=True)
            if r.status_code == 200:
                return r.text
            if r.status_code == 403:
                logger.debug(f"EventsEye 403 on {url} (attempt {attempt+1})")
                await asyncio.sleep(cfg.delay_seconds * 2)
        except Exception as e:
            logger.debug(f"EventsEye fetch error {url}: {e}")
    return ""


async def crawl(cfg: CrawlConfig) -> list[EventCreate]:
    all_urls   = list(dict.fromkeys(SEED_URLS + cfg.extra_urls))
    visited:   set[str] = set()
    queue:     list[str] = all_urls[:]
    by_hash:   dict[str, EventCreate] = {}
    today      = date.today().isoformat()

    limits = httpx.Limits(
        max_connections=cfg.concurrency,
        max_keepalive_connections=cfg.concurrency,
    )
    async with httpx.AsyncClient(limits=limits) as client:
        while queue and len(visited) < cfg.max_pages:
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)

            html = await _fetch(client, url, cfg)
            if not html:
                continue

            soup   = BeautifulSoup(html, "html.parser")
            parsed = _parse_json_ld(soup, url)
            if not parsed:
                parsed = _parse_html_cards(soup, url)

            for ev in parsed:
                if ev.start_date >= today:
                    by_hash.setdefault(ev.dedup_hash, ev)

            # Discover more listing pages
            for new_url in _discover_listing_urls(soup, url):
                if new_url not in visited and new_url not in queue:
                    queue.append(new_url)

            logger.info(
                f"EventsEye crawled {len(visited)}/{cfg.max_pages} pages "
                f"→ {len(by_hash)} unique upcoming events so far"
            )

            if len(by_hash) >= 2000:   # safety cap
                break

    return list(by_hash.values())


async def run_eventseye_seed(
    cfg: CrawlConfig | None = None,
    *,
    dry_run: bool | None = None,
) -> dict:
    if cfg is None:
        cfg = CrawlConfig()
    if dry_run is not None:
        cfg.dry_run = dry_run

    started = datetime.now(UTC)
    logger.info(f"EventsEye seed started (max_pages={cfg.max_pages}, dry_run={cfg.dry_run})")

    events  = await crawl(cfg)
    today   = date.today().isoformat()
    upcoming = [e for e in events if e.start_date >= today]

    logger.info(f"EventsEye: {len(events)} total, {len(upcoming)} upcoming events parsed.")

    inserted = 0
    already_in_db = 0

    if not cfg.dry_run and upcoming:
        await init_db()
        async with AsyncSessionLocal() as db:
            before = await count_events(db)

        async with AsyncSessionLocal() as db:
            inserted, _skipped = await batch_upsert_events(db, upcoming, skip_past=True)

        async with AsyncSessionLocal() as db:
            after = await count_events(db)

        already_in_db = len(upcoming) - inserted
        logger.info(
            f"EventsEye seed done — inserted={inserted} already_in_db={already_in_db} "
            f"total_in_db={after}"
        )
    elif cfg.dry_run:
        for ev in upcoming[:10]:
            logger.info(f"DRY RUN: {ev.start_date} | {ev.name} | {ev.city}, {ev.country}")

    return {
        "source": SOURCE,
        "fetched": len(events),
        "upcoming_events": len(upcoming),
        "inserted": inserted,
        "already_in_db": already_in_db,
        "dry_run": cfg.dry_run,
        "duration_seconds": round((datetime.now(UTC) - started).total_seconds(), 2),
        "pages_crawled": cfg.max_pages,
    }


# ── CLI entry-point ─────────────────────────────────────────────────
async def main() -> int:
    p = argparse.ArgumentParser(description="EventsEye global event seeder.")
    p.add_argument("--max-pages",     type=int,   default=60)
    p.add_argument("--delay-seconds", type=float, default=2.0)
    p.add_argument("--concurrency",   type=int,   default=2)
    p.add_argument("--dry-run",       action="store_true")
    args = p.parse_args()

    cfg = CrawlConfig(
        max_pages=max(1, args.max_pages),
        delay_seconds=max(0.5, args.delay_seconds),
        concurrency=max(1, args.concurrency),
        dry_run=args.dry_run,
    )
    result = await run_eventseye_seed(cfg)
    logger.info(f"Result: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
