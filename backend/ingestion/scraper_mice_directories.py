"""
Scrapers for high-value global and Southeast Asia MICE directories.

Sources:
  - EventsEye.com: global trade show directory spanning industries/regions.
  - SACEOS: Singapore Association of Convention & Exhibition Organisers and
    Suppliers, including Singapore MICE event listings.
  - MyCEB: Malaysia Convention & Exhibition Bureau business event pages.

These connectors use conservative page caps, polite delays, and resilient HTML
selectors because directory markup can vary by source and by listing type.
"""
from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from typing import Iterable, List
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from config import get_settings
from ingestion.base_connector import BaseConnector
from models.event import EventCreate

settings = get_settings()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

MONTHS = {
    "jan": "01", "january": "01", "feb": "02", "february": "02",
    "mar": "03", "march": "03", "apr": "04", "april": "04", "may": "05",
    "jun": "06", "june": "06", "jul": "07", "july": "07", "aug": "08",
    "august": "08", "sep": "09", "sept": "09", "september": "09",
    "oct": "10", "october": "10", "nov": "11", "november": "11",
    "dec": "12", "december": "12",
}

EVENTSEYE_SEED_URLS = [
    "https://www.eventseye.com/",
    "https://www.eventseye.com/fairs/",  # directory root
    "https://www.eventseye.com/fairs/ct1_trade-shows_usa-united-states-of-america.html",
    "https://www.eventseye.com/fairs/zt1_trade-shows_america.html",
    "https://www.eventseye.com/fairs/zt2_trade-shows_europe.html",
    "https://www.eventseye.com/fairs/zt3_trade-shows_asia-pacific.html",
    "https://www.eventseye.com/fairs/zt4_trade-shows_africa-middle-east.html",
]

SACEOS_URLS = [
    "https://saceos.org.sg/events/",
]

MYCEB_URLS = [
    "https://www.myceb.com.my/mepg/home",
    "https://www.myceb.com.my/exhibitions",
]

CARD_SELECTORS = (
    "article", "div.event", "div.event-item", "div.event-card", "li.event",
    "div[class*='event']", "tr",
)
TITLE_SELECTORS = (
    "h1", "h2", "h3", "h4", ".title", ".event-title", ".entry-title",
    ".name", "a[href]", "td:nth-of-type(1)",
)
DATE_SELECTORS = (
    "time", ".date", ".event-date", ".dates", ".datetime", "[class*='date']",
    "td:nth-of-type(2)",
)
LOCATION_SELECTORS = (
    ".location", ".venue", ".city", ".place", "[class*='location']",
    "[class*='venue']", "td:nth-of-type(3)",
)


def _clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _parse_date(text: str) -> str:
    text = _clean(text).lower()
    if not text:
        return ""

    iso = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", text)
    if iso:
        return f"{iso.group(1)}-{iso.group(2).zfill(2)}-{iso.group(3).zfill(2)}"

    # 03/06/2026 or 28.03.2026. Ambiguous slash dates on directories are often
    # month/day in English pages, so keep the first number as month when <= 12.
    numeric = re.search(r"\b(\d{1,2})[/.](\d{1,2})[/.](20\d{2})\b", text)
    if numeric:
        first, second, year = numeric.groups()
        month, day = (first, second) if int(first) <= 12 else (second, first)
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

    month_day_year = re.search(r"(jan\w*|feb\w*|mar\w*|apr\w*|may|jun\w*|jul\w*|aug\w*|sep\w*|oct\w*|nov\w*|dec\w*)\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s*[-–]\s*\d{1,2})?,?\s+(20\d{2})", text)
    if month_day_year:
        month = MONTHS.get(month_day_year.group(1)[:3], "")
        return f"{month_day_year.group(3)}-{month}-{month_day_year.group(2).zfill(2)}" if month else ""

    day_month_year = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+(jan\w*|feb\w*|mar\w*|apr\w*|may|jun\w*|jul\w*|aug\w*|sep\w*|oct\w*|nov\w*|dec\w*)\.?\s+(20\d{2})", text)
    if day_month_year:
        month = MONTHS.get(day_month_year.group(2)[:3], "")
        return f"{day_month_year.group(3)}-{month}-{day_month_year.group(1).zfill(2)}" if month else ""

    return ""


def _first_text(card, selectors: Iterable[str]) -> str:
    for selector in selectors:
        el = card.select_one(selector)
        if el:
            text = _clean(el.get_text(" ", strip=True))
            if text:
                return text
    return ""


def _first_link(card, base_url: str) -> str:
    link_el = card.select_one("a[href]")
    if not link_el:
        return base_url
    return urljoin(base_url, link_el.get("href", ""))


def _split_location(text: str) -> tuple[str, str]:
    text = _clean(text)
    if not text:
        return "", ""
    parts = [p.strip() for p in re.split(r",|\|", text) if p.strip()]
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[-1]


def _infer_category(url: str, fallback: str = "mice") -> str:
    path = urlparse(url).path.lower()
    for token in ("technology", "health", "medical", "finance", "industrial", "construction", "food", "travel", "energy", "education", "automotive"):
        if token in path:
            return token
    return fallback


def _is_future_or_current(date_text: str) -> bool:
    try:
        return datetime.fromisoformat(date_text).date() >= datetime.now(UTC).date()
    except ValueError:
        return True


class _DirectoryScraper(BaseConnector):
    source_platform = "Directory"
    seed_urls: list[str] = []
    max_pages = 8
    default_country = ""
    default_category = "mice"
    default_tags = "mice,business events,trade shows,conferences,exhibitions"
    default_audience = "event planners,industry professionals,trade buyers,executives"
    default_attendees = 500

    async def _get(self, client: httpx.AsyncClient, url: str) -> str:
        await asyncio.sleep(settings.scrape_delay_seconds)
        response = await client.get(url, timeout=settings.scrape_timeout_seconds)
        response.raise_for_status()
        return response.text

    def _discover_listing_urls(self, soup: BeautifulSoup, base_url: str) -> list[str]:
        urls = []
        source_domain = urlparse(base_url).netloc
        for anchor in soup.select("a[href]"):
            href = anchor.get("href", "")
            absolute = urljoin(base_url, href)
            parsed = urlparse(absolute)
            if parsed.netloc != source_domain:
                continue
            lowered = absolute.lower()
            text = anchor.get_text(" ", strip=True).lower()
            if any(term in lowered or term in text for term in ("event", "trade-show", "trade-shows", "exhibition", "conference", "fairs")):
                urls.append(absolute)
        return urls[: self.max_pages]

    def _parse_cards(self, soup: BeautifulSoup, page_url: str) -> list[EventCreate]:
        events: list[EventCreate] = []
        seen: set[str] = set()
        cards = []
        for selector in CARD_SELECTORS:
            cards.extend(soup.select(selector))
        if not cards:
            cards = [soup]

        for card in cards[:60]:
            try:
                name = _first_text(card, TITLE_SELECTORS)
                if len(name) < 5 or name.lower() in {"events", "event", "home"}:
                    continue
                date_text = _first_text(card, DATE_SELECTORS) or _clean(card.get_text(" ", strip=True))
                start_date = _parse_date(date_text)
                if not start_date or not _is_future_or_current(start_date):
                    continue
                location_text = _first_text(card, LOCATION_SELECTORS)
                city, country = _split_location(location_text)
                country = country or self.default_country
                link = _first_link(card, page_url)
                category = _infer_category(link, self.default_category)
                dh = self.make_hash(name, start_date, city)
                if dh in seen:
                    continue
                seen.add(dh)

                events.append(EventCreate(
                    id=self.make_id(),
                    source_platform=self.source_platform,
                    source_url=link,
                    dedup_hash=dh,
                    name=name[:250],
                    description=f"Business event sourced from {self.source_platform}.",
                    short_summary=f"{self.source_platform} listing for {name[:180]}",
                    start_date=start_date,
                    end_date=start_date,
                    city=city,
                    country=country,
                    category=category,
                    industry_tags=self.default_tags,
                    audience_personas=self.default_audience,
                    est_attendees=self.default_attendees,
                    ticket_price_usd=0.0,
                    price_description="See website",
                    registration_url=link,
                ))
            except Exception as exc:
                logger.debug(f"{self.source_platform} card parse error: {exc}")
        return events

    async def fetch(self) -> List[EventCreate]:
        events: list[EventCreate] = []
        seen_hashes: set[str] = set()
        pages_to_visit = list(dict.fromkeys(self.seed_urls))
        visited: set[str] = set()

        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
            idx = 0
            while idx < len(pages_to_visit) and len(visited) < self.max_pages:
                url = pages_to_visit[idx]
                idx += 1
                if url in visited:
                    continue
                visited.add(url)

                try:
                    html = await self._get(client, url)
                except Exception as exc:
                    logger.debug(f"{self.source_platform} {url}: {exc}")
                    continue

                soup = BeautifulSoup(html, "html.parser")
                for discovered_url in self._discover_listing_urls(soup, url):
                    if discovered_url not in visited and discovered_url not in pages_to_visit:
                        pages_to_visit.append(discovered_url)

                for event in self._parse_cards(soup, url):
                    if event.dedup_hash in seen_hashes:
                        continue
                    seen_hashes.add(event.dedup_hash)
                    events.append(event)

        logger.info(f"{self.source_platform}: {len(events)} events from {len(visited)} pages.")
        return events


class ScraperEventsEye(_DirectoryScraper):
    name = "EventsEye"
    source_platform = "EventsEye"
    seed_urls = EVENTSEYE_SEED_URLS
    max_pages = 14
    default_category = "trade show"
    default_tags = "all industries,global trade shows,exhibitions,conferences,mice"
    default_audience = "trade buyers,exhibitors,industry professionals,executives,distributors"
    default_attendees = 1200


class ScraperSACEOS(_DirectoryScraper):
    name = "SACEOS"
    source_platform = "SACEOS"
    seed_urls = SACEOS_URLS
    max_pages = 6
    default_country = "Singapore"
    default_category = "mice"
    default_tags = "singapore,mice,business events,conferences,exhibitions,official directory"
    default_audience = "event planners,mice professionals,association leaders,corporate buyers"
    default_attendees = 350


class ScraperMyCEB(_DirectoryScraper):
    name = "MyCEB"
    source_platform = "MyCEB"
    seed_urls = MYCEB_URLS
    max_pages = 8
    default_country = "Malaysia"
    default_category = "mice"
    default_tags = "malaysia,mice,business events,conferences,exhibitions,official directory"
    default_audience = "event planners,mice professionals,association leaders,corporate buyers"
    default_attendees = 500
