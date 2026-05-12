"""
Standalone 10times.com global event seeder.

This script powers both manual CLI runs and the protected FastAPI seed endpoint.
Use it when you want to pull a broad 10times.com snapshot, deduplicate it, and
seed the configured events database.

Usage from the repository root:
    python backend/scripts/seed_10times_global.py --max-pages-per-listing 3

Examples:
    # Preview without writing to the DB
    python backend/scripts/seed_10times_global.py --dry-run --limit-events 100

    # Broader crawl with polite throttling
    python backend/scripts/seed_10times_global.py \
        --max-pages-per-listing 5 \
        --concurrency 2 \
        --delay-seconds 2.5
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
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup
from loguru import logger

# Allow this standalone script to run from the repo root without changing the
# existing package/import layout used by the FastAPI app.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from db.crud import upsert_event  # noqa: E402
from db.database import AsyncSessionLocal, init_db  # noqa: E402
from models.event import EventCreate  # noqa: E402

BASE_URL = "https://10times.com"
SOURCE_PLATFORM = "10Times"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

INDEX_URLS = (
    "https://10times.com/events/by-country",
    "https://10times.com/tradeshows/by-country",
    "https://10times.com/conferences/by-country",
    "https://10times.com/events/by-industry",
    "https://10times.com/tradeshows/by-industry",
    "https://10times.com/conferences/by-industry",
)

# Safety-net listing URLs covering broad event types and high-volume industries.
# Discovery from INDEX_URLS is still the primary way this script expands across
# countries, regions, and industries.
SEED_LISTING_URLS = (
    "https://10times.com/events",
    "https://10times.com/tradeshows",
    "https://10times.com/conferences",
    "https://10times.com/education-training",
    "https://10times.com/medical-pharma",
    "https://10times.com/it-technology",
    "https://10times.com/banking-finance",
    "https://10times.com/business-consultancy",
    "https://10times.com/industrial-engineering",
    "https://10times.com/building-construction",
    "https://10times.com/food-beverage",
    "https://10times.com/logistics-transportation",
    "https://10times.com/power-energy",
    "https://10times.com/auto-automotive",
    "https://10times.com/fashion-beauty",
    "https://10times.com/travel-tourism",
)

MAJOR_COUNTRY_LISTINGS = (
    "https://10times.com/usa",
    "https://10times.com/uk",
    "https://10times.com/germany",
    "https://10times.com/india",
    "https://10times.com/canada",
    "https://10times.com/australia",
    "https://10times.com/china",
    "https://10times.com/france",
    "https://10times.com/italy",
    "https://10times.com/spain",
    "https://10times.com/netherlands",
    "https://10times.com/uae",
    "https://10times.com/japan",
    "https://10times.com/singapore",
    "https://10times.com/south-africa",
    "https://10times.com/brazil",
)

MONTHS = {
    "jan": "01",
    "feb": "02",
    "mar": "03",
    "apr": "04",
    "may": "05",
    "jun": "06",
    "jul": "07",
    "aug": "08",
    "sep": "09",
    "sept": "09",
    "oct": "10",
    "nov": "11",
    "dec": "12",
}

EVENT_CARD_SELECTORS = (
    "div.event-item",
    "div.event-card",
    "li.event-listing",
    "article.event",
    "tr.event-row",
    "tr[data-eventid]",
    "div[data-eventid]",
    "div[class*='event']",
)

TITLE_SELECTORS = (
    "h1",
    "h2",
    "h3",
    ".event-name",
    ".event-title",
    "a.event-title",
    "td.event-title",
    "a[href*='/e']",
    "[data-ga-label]",
    "[data-name]",
)

DATE_SELECTORS = (
    "time",
    ".event-date",
    ".dates",
    ".date-range",
    "td.date",
    "[class*='date']",
)

LOCATION_SELECTORS = (
    ".location",
    ".venue",
    ".city",
    "td.location",
    "[class*='venue']",
    "[class*='location']",
)

ATTENDEE_SELECTORS = (
    ".attendees",
    ".visitors",
    ".expected",
    "[class*='attendee']",
    "[class*='visitor']",
)


@dataclass(frozen=True)
class CrawlConfig:
    max_pages_per_listing: int
    limit_events: int | None
    concurrency: int
    delay_seconds: float
    timeout_seconds: float
    dry_run: bool


def normalize_space(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def absolute_10times_url(href: str) -> str:
    return urljoin(BASE_URL, href)


def canonical_url(url: str) -> str:
    parsed = urlparse(url)
    query = [(k, v) for k, v in parse_qsl(parsed.query) if not k.lower().startswith("utm_")]
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", urlencode(query), ""))


def make_page_url(url: str, page: int) -> str:
    if page <= 1:
        return url
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query))
    query["page"] = str(page)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlencode(query), parsed.fragment))


def make_hash(name: str, start_date: str, city: str) -> str:
    raw = f"{name.lower().strip()}|{start_date}|{city.lower().strip()}"
    return hashlib.md5(raw.encode()).hexdigest()


def safe_int(text: str | None, default: int = 0) -> int:
    numbers = re.findall(r"\d[\d,]*", text or "")
    if not numbers:
        return default
    try:
        return int(numbers[0].replace(",", ""))
    except ValueError:
        return default


def infer_category_from_url(url: str) -> str:
    path = urlparse(url).path.strip("/")
    if not path:
        return "event"
    parts = [p for p in path.split("/") if p]
    for token in reversed(parts):
        if token not in {"events", "tradeshows", "conferences", "by-country", "by-industry"}:
            return token.replace("-", " ")
    return parts[-1].replace("-", " ") if parts else "event"


def parse_date(text: str) -> tuple[str, str, int]:
    """Return (start_date, end_date, duration_days) as ISO strings when possible."""
    original = normalize_space(text)
    if not original:
        return "", "", 1
    lower = original.lower()

    iso_dates = re.findall(r"\d{4}-\d{2}-\d{2}", lower)
    if iso_dates:
        start = iso_dates[0]
        end = iso_dates[-1]
        return start, end, max(1, len(set(iso_dates)))

    # Examples: May 14 - 16, 2026; May 14, 2026; 14 - 16 May 2026
    month_names = "jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
    m = re.search(rf"({month_names})\s+(\d{{1,2}})(?:\s*[-–]\s*(\d{{1,2}}))?,?\s*(\d{{4}})", lower)
    if m:
        month = MONTHS.get(m.group(1)[:3], "01")
        start_day = m.group(2).zfill(2)
        end_day = (m.group(3) or m.group(2)).zfill(2)
        year = m.group(4)
        duration = max(1, int(end_day) - int(start_day) + 1) if end_day >= start_day else 1
        return f"{year}-{month}-{start_day}", f"{year}-{month}-{end_day}", duration

    m = re.search(rf"(\d{{1,2}})(?:\s*[-–]\s*(\d{{1,2}}))?\s+({month_names})\s+(\d{{4}})", lower)
    if m:
        month = MONTHS.get(m.group(3)[:3], "01")
        start_day = m.group(1).zfill(2)
        end_day = (m.group(2) or m.group(1)).zfill(2)
        year = m.group(4)
        duration = max(1, int(end_day) - int(start_day) + 1) if end_day >= start_day else 1
        return f"{year}-{month}-{start_day}", f"{year}-{month}-{end_day}", duration

    return "", "", 1


def parse_date_from_card(card: BeautifulSoup) -> tuple[str, str, int]:
    date_node = card.select_one("[data-start-date]")
    if date_node:
        start_raw = normalize_space(str(date_node.get("data-start-date") or "")).replace("/", "-")
        end_raw = normalize_space(str(date_node.get("data-end-date") or "")).replace("/", "-")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", start_raw):
            end = end_raw if re.fullmatch(r"\d{4}-\d{2}-\d{2}", end_raw) else start_raw
            try:
                duration = max(1, (datetime.fromisoformat(end) - datetime.fromisoformat(start_raw)).days + 1)
            except ValueError:
                duration = 1
            return start_raw, end, duration
    return parse_date(first_text(card, DATE_SELECTORS) or card.get_text(" ", strip=True))


def parse_location(text: str) -> tuple[str, str, str]:
    cleaned = normalize_space(text)
    if not cleaned:
        return "", "", ""
    cleaned = re.sub(r"\b(map|directions|venue)\b", "", cleaned, flags=re.I).strip(" ,")
    parts = [p.strip() for p in re.split(r",|·|\|", cleaned) if p.strip()]
    if not parts:
        return "", "", cleaned
    city = parts[0]
    country = parts[-1] if len(parts) > 1 else ""
    return city, country, cleaned


def first_text(card: BeautifulSoup, selectors: Iterable[str]) -> str:
    for selector in selectors:
        element = card.select_one(selector)
        text = normalize_space(element.get_text(" ", strip=True)) if element else ""
        if text:
            return text
    return ""


def event_link_from_card(card: BeautifulSoup) -> str:
    preferred = card.select_one("a.event-title[href], a[href*='/e'][href], h2 a[href], h3 a[href]")
    if preferred and preferred.get("href"):
        return canonical_url(absolute_10times_url(preferred["href"]))
    for anchor in card.select("a[href]"):
        href = anchor.get("href", "")
        if href and not href.startswith("#"):
            return canonical_url(absolute_10times_url(href))

    onclick = str(card.get("onclick") or "")
    match = re.search(r"window\.open\('([^']+)'", onclick)
    if match:
        return canonical_url(absolute_10times_url(match.group(1)))

    clickable = card.select_one("[onclick*='window.open']")
    if clickable:
        onclick = str(clickable.get("onclick") or "")
        match = re.search(r"window\.open\('([^']+)'", onclick)
        if match:
            return canonical_url(absolute_10times_url(match.group(1)))
    return BASE_URL


def parse_json_ld_events(soup: BeautifulSoup, listing_url: str) -> list[EventCreate]:
    events: list[EventCreate] = []
    category = infer_category_from_url(listing_url)
    for script in soup.select("script[type='application/ld+json']"):
        raw = script.string or script.get_text(strip=True)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        nodes = payload if isinstance(payload, list) else [payload]
        for node in nodes:
            graph = node.get("@graph") if isinstance(node, dict) else None
            candidates = graph if isinstance(graph, list) else [node]
            for item in candidates:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("@type")
                if isinstance(item_type, list):
                    is_event = "Event" in item_type
                else:
                    is_event = item_type == "Event"
                if not is_event:
                    continue
                name = normalize_space(item.get("name"))
                start, end, duration = parse_date(str(item.get("startDate") or ""))
                if not name or not start:
                    continue
                location = item.get("location") or {}
                address = location.get("address") if isinstance(location, dict) else {}
                venue = normalize_space(location.get("name")) if isinstance(location, dict) else ""
                if isinstance(address, dict):
                    city = normalize_space(address.get("addressLocality"))
                    country = normalize_space(address.get("addressCountry"))
                    address_text = normalize_space(", ".join(str(v) for v in address.values() if v))
                else:
                    city, country, address_text = parse_location(str(address or venue))
                link = canonical_url(str(item.get("url") or listing_url))
                events.append(build_event(name, link, start, end, duration, city, country, venue, address_text, category, 0))
    return events


def build_event(
    name: str,
    link: str,
    start_date: str,
    end_date: str,
    duration_days: int,
    city: str,
    country: str,
    venue_name: str,
    address: str,
    category: str,
    est_attendees: int,
) -> EventCreate:
    industry = category or "event"
    return EventCreate(
        id=str(uuid.uuid4()),
        source_platform=SOURCE_PLATFORM,
        source_url=link,
        dedup_hash=make_hash(name, start_date, city),
        name=name,
        description=f"Global {industry} event sourced from 10times.com.",
        short_summary="",
        edition_number="",
        start_date=start_date,
        end_date=end_date or start_date,
        duration_days=duration_days,
        venue_name=venue_name,
        address=address,
        city=city,
        country=country,
        is_virtual="virtual" in f"{city} {country} {venue_name}".lower(),
        is_hybrid="hybrid" in f"{city} {country} {venue_name}".lower(),
        est_attendees=est_attendees,
        category=category,
        industry_tags=industry,
        audience_personas="executives,industry professionals,trade buyers,conference attendees",
        ticket_price_usd=0.0,
        price_description="See 10times listing",
        registration_url=link,
        sponsors="",
        speakers_url="",
        agenda_url="",
    )


def parse_event_cards(html: str, listing_url: str) -> list[EventCreate]:
    soup = BeautifulSoup(html, "html.parser")
    events = parse_json_ld_events(soup, listing_url)
    seen_hashes = {event.dedup_hash for event in events}
    category = infer_category_from_url(listing_url)

    cards = []
    for selector in EVENT_CARD_SELECTORS:
        cards.extend(soup.select(selector))
    if not cards:
        cards = soup.select("tr, article, li, div")

    for card in cards:
        text = normalize_space(card.get_text(" ", strip=True))
        if len(text) < 20:
            continue
        name = first_text(card, TITLE_SELECTORS)
        if not name or len(name) < 3 or name.lower() in {"events", "trade shows", "conferences"}:
            continue
        start_date, end_date, duration_days = parse_date_from_card(card)
        if not start_date:
            continue
        location_text = first_text(card, LOCATION_SELECTORS)
        city, country, address = parse_location(location_text)
        attendee_text = first_text(card, ATTENDEE_SELECTORS)
        est_attendees = safe_int(attendee_text)
        link = event_link_from_card(card)
        event = build_event(name, link, start_date, end_date, duration_days, city, country, "", address, category, est_attendees)
        if event.dedup_hash in seen_hashes:
            continue
        seen_hashes.add(event.dedup_hash)
        events.append(event)

    return events


def discover_listing_urls(html: str) -> set[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: set[str] = set()
    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "")
        if not href or href.startswith("#"):
            continue
        url = canonical_url(absolute_10times_url(href))
        parsed = urlparse(url)
        if not parsed.netloc.endswith("10times.com"):
            continue
        path = parsed.path.strip("/")
        if not path or any(skip in path for skip in ("login", "signup", "pricing", "privacy", "contact")):
            continue
        if any(token in path for token in ("events", "tradeshows", "conferences", "expo", "trade-shows")) or len(path.split("/")) <= 2:
            urls.add(url)
    return urls


async def fetch_text(client: httpx.AsyncClient, url: str, config: CrawlConfig, semaphore: asyncio.Semaphore) -> tuple[str, int | None]:
    async with semaphore:
        await asyncio.sleep(config.delay_seconds + random.uniform(0, 0.6))
        try:
            response = await client.get(url, timeout=config.timeout_seconds)
            response.raise_for_status()
            return response.text, response.status_code
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else None
            logger.debug(f"Fetch failed for {url}: {exc}")
            return "", status
        except Exception as exc:
            logger.debug(f"Fetch failed for {url}: {exc}")
            return "", None


async def collect_listing_urls(client: httpx.AsyncClient, config: CrawlConfig) -> list[str]:
    semaphore = asyncio.Semaphore(config.concurrency)
    discovered = set(SEED_LISTING_URLS) | set(MAJOR_COUNTRY_LISTINGS)
    tasks = [fetch_text(client, url, config, semaphore) for url in INDEX_URLS]
    for html, _status in await asyncio.gather(*tasks):
        if html:
            discovered.update(discover_listing_urls(html))
    logger.info(f"Discovered {len(discovered)} candidate 10times listing URLs.")
    return sorted(discovered)


async def crawl_events(config: CrawlConfig) -> list[EventCreate]:
    events_by_hash: dict[str, EventCreate] = {}
    limits = httpx.Limits(max_connections=max(1, config.concurrency), max_keepalive_connections=max(1, config.concurrency))
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, limits=limits) as client:
        listing_urls = await collect_listing_urls(client, config)
        semaphore = asyncio.Semaphore(config.concurrency)
        page_urls = [make_page_url(url, page) for url in listing_urls for page in range(1, config.max_pages_per_listing + 1)]

        for index in range(0, len(page_urls), config.concurrency):
            batch = page_urls[index : index + config.concurrency]
            pages = await asyncio.gather(*(fetch_text(client, url, config, semaphore) for url in batch))
            forbidden_count = sum(1 for _html, status in pages if status == 403)
            if forbidden_count == len(batch):
                logger.warning("10Times crawl is fully blocked by 403 responses for this batch; stopping early to avoid useless retries.")
                break

            for url, (html, _status) in zip(batch, pages):
                if not html:
                    continue
                for event in parse_event_cards(html, url):
                    events_by_hash.setdefault(event.dedup_hash, event)
                    if config.limit_events and len(events_by_hash) >= config.limit_events:
                        logger.info(f"Reached --limit-events={config.limit_events}.")
                        return list(events_by_hash.values())
            logger.info(f"Parsed {len(events_by_hash)} unique events after {min(index + len(batch), len(page_urls))}/{len(page_urls)} pages.")

    return list(events_by_hash.values())


async def seed_database(events: list[EventCreate]) -> int:
    await init_db()
    saved = 0
    async with AsyncSessionLocal() as db:
        for event in events:
            if await upsert_event(db, event):
                saved += 1
    return saved


async def run_10times_seed(config: CrawlConfig) -> dict:
    started = datetime.now(UTC)
    logger.info(f"Starting standalone 10times global crawl at {started.isoformat()}")
    events = await crawl_events(config)
    parsed = len(events)
    logger.info(f"Parsed {parsed} unique 10times events after in-memory deduplication.")

    if config.dry_run:
        for event in events[:10]:
            logger.info(f"DRY RUN sample: {event.start_date} | {event.name} | {event.city}, {event.country} | {event.source_url}")
        logger.info("Dry run complete; database was not modified.")
        saved = 0
    else:
        saved = await seed_database(events)
        logger.info(f"Seeder complete. Upsert attempted for {saved}/{parsed} events; DB unique constraint ignores duplicate dedup_hash values.")

    finished = datetime.now(UTC)
    return {
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_seconds": round((finished - started).total_seconds(), 2),
        "parsed_events": parsed,
        "saved_events": saved,
        "dry_run": config.dry_run,
        "limit_events": config.limit_events,
        "max_pages_per_listing": config.max_pages_per_listing,
        "concurrency": config.concurrency,
        "delay_seconds": config.delay_seconds,
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description="Discover, deduplicate, and seed global 10times.com events.")
    parser.add_argument("--max-pages-per-listing", type=int, default=2, help="Number of paginated pages to crawl for each discovered listing URL.")
    parser.add_argument("--limit-events", type=int, default=None, help="Stop after this many unique events are parsed.")
    parser.add_argument("--concurrency", type=int, default=2, help="Maximum concurrent HTTP requests.")
    parser.add_argument("--delay-seconds", type=float, default=2.0, help="Polite delay before each HTTP request.")
    parser.add_argument("--timeout-seconds", type=float, default=20.0, help="HTTP timeout per request.")
    parser.add_argument("--dry-run", action="store_true", help="Parse and dedupe events without writing to the database.")
    args = parser.parse_args()

    config = CrawlConfig(
        max_pages_per_listing=max(1, args.max_pages_per_listing),
        limit_events=args.limit_events,
        concurrency=max(1, args.concurrency),
        delay_seconds=max(0.0, args.delay_seconds),
        timeout_seconds=max(1.0, args.timeout_seconds),
        dry_run=args.dry_run,
    )

    await run_10times_seed(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
