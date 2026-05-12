"""Scraper — conferencealerts.com advanced search."""
import asyncio
import re
from urllib.parse import quote_plus, urljoin

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from config import get_settings
from ingestion.base_connector import BaseConnector
from models.event import EventCreate

settings = get_settings()

SEARCH_TERMS = (
    "computer science",
    "artificial intelligence",
    "machine learning",
    "data science",
    "software engineering",
    "cyber security",
    "cloud computing",
    "healthcare technology",
    "fintech",
    "management",
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; EventBot/1.0; research)",
    "Accept": "text/html,application/xhtml+xml",
}

MONTHS = {
    "january": "01", "february": "02", "march": "03", "april": "04", "may": "05", "june": "06",
    "july": "07", "august": "08", "september": "09", "october": "10", "november": "11", "december": "12",
}


def _parse_month_header(header_text: str) -> tuple[str, str]:
    text = (header_text or "").strip().lower()
    m = re.search(r"([a-z]+)\s+(\d{4})", text)
    if not m:
        return "", ""
    month = MONTHS.get(m.group(1), "")
    year = m.group(2)
    return year, month


def _parse_event_date(day_text: str, month_header: str) -> str:
    year, month = _parse_month_header(month_header)
    if not year or not month:
        return ""
    day_match = re.search(r"(\d{1,2})", day_text or "")
    if not day_match:
        return ""
    return f"{year}-{month}-{day_match.group(1).zfill(2)}"


class ScraperConferenceAlerts(BaseConnector):
    name = "ConferenceAlerts"

    async def fetch(self) -> list[EventCreate]:
        all_events: list[EventCreate] = []
        seen = set()

        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=20) as client:
            for term in SEARCH_TERMS:
                url = f"https://conferencealerts.com/advanced-search?q={quote_plus(term)}"
                await asyncio.sleep(settings.scrape_delay_seconds)
                try:
                    r = await client.get(url)
                    r.raise_for_status()
                except Exception as e:
                    logger.debug(f"ConferenceAlerts {term}: {e}")
                    continue

                soup = BeautifulSoup(r.text, "html.parser")
                results_root = soup.select_one("div.ca-search-results")
                if not results_root:
                    logger.debug(f"ConferenceAlerts {term}: no results root")
                    continue

                for month_block in results_root.select("div.mb-4"):
                    month_header = month_block.select_one("h2")
                    month_text = month_header.get_text(strip=True) if month_header else ""

                    for row in month_block.select("div.py-2.border-bottom")[:40]:
                        try:
                            link_el = row.select_one("a[href*='show-event']")
                            if not link_el:
                                continue
                            name = link_el.get_text(" ", strip=True)
                            link = urljoin("https://conferencealerts.com/", link_el.get("href", "").strip())

                            day_el = row.select_one("div.fw-bold")
                            start_date = _parse_event_date(day_el.get_text(strip=True) if day_el else "", month_text)
                            if not start_date:
                                continue

                            city_el = row.select_one("span.fw-medium")
                            country_el = row.select_one("span[style*='color:#198754']")
                            city = city_el.get_text(strip=True) if city_el else ""
                            country = country_el.get_text(strip=True) if country_el else ""

                            mode_el = row.select_one("span.badge")
                            mode = mode_el.get_text(" ", strip=True).lower() if mode_el else ""

                            dedup_hash = self.make_hash(name, start_date, city)
                            if dedup_hash in seen:
                                continue
                            seen.add(dedup_hash)

                            all_events.append(EventCreate(
                                id=self.make_id(),
                                source_platform="ConferenceAlerts",
                                source_url=link,
                                dedup_hash=dedup_hash,
                                name=name,
                                description=f"ConferenceAlerts advanced search result for '{term}'.",
                                start_date=start_date,
                                end_date=start_date,
                                city=city,
                                country=country,
                                category=term,
                                industry_tags=term,
                                audience_personas="researchers,academics,professionals,industry leaders",
                                est_attendees=200,
                                ticket_price_usd=0.0,
                                price_description=(f"Mode: {mode}" if mode else "See website"),
                                registration_url=link,
                            ))
                        except Exception as e:
                            logger.debug(f"ConferenceAlerts row parse ({term}): {e}")

        logger.info(f"ConferenceAlerts: {len(all_events)} events.")
        return all_events
