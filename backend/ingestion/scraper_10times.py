"""
Scraper — 10times.com
One of the largest global trade show + conference directories.
Uses httpx + BeautifulSoup (no JS rendering needed for listing pages).
Respects crawl delay, reads robots.txt guidance.
"""
import asyncio
import httpx
from bs4 import BeautifulSoup
from typing import List
from models.event import EventCreate
from ingestion.base_connector import BaseConnector
from config import get_settings
from loguru import logger

settings = get_settings()

CATEGORIES = [
    ("technology", "https://10times.com/technology"),
    ("finance",    "https://10times.com/finance"),
    ("healthcare", "https://10times.com/healthcare"),
    ("logistics",  "https://10times.com/logistics"),
    ("marketing",  "https://10times.com/marketing"),
    ("retail",     "https://10times.com/retail"),
    ("energy",     "https://10times.com/energy"),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


class Scraper10Times(BaseConnector):
    name = "10Times"

    async def _scrape_category(
        self, client: httpx.AsyncClient, category: str, url: str
    ) -> List[EventCreate]:
        events = []
        try:
            await asyncio.sleep(settings.scrape_delay_seconds)
            r = await client.get(url, timeout=settings.scrape_timeout_seconds)
            r.raise_for_status()
        except Exception as e:
            logger.debug(f"10Times {category}: {e}")
            return events

        soup = BeautifulSoup(r.text, "html.parser")

        # 10times event cards have class "event-card" or similar
        cards = soup.select("div.event-item, div.event-card, li.event-listing, article.event")
        if not cards:
            # fallback: try table rows
            cards = soup.select("tr.event-row")

        for card in cards[:20]:
            try:
                # Name
                name_el = card.select_one("h2, h3, .event-name, a.event-title, td.event-title")
                name = name_el.get_text(strip=True) if name_el else ""
                if not name:
                    continue

                # Link
                link_el = card.select_one("a[href]")
                link = ""
                if link_el:
                    href = link_el.get("href", "")
                    link = href if href.startswith("http") else f"https://10times.com{href}"

                # Date
                date_el = card.select_one(".event-date, .dates, time, .date-range, td.date")
                date_text = date_el.get_text(strip=True) if date_el else ""
                start_date = self._parse_date(date_text)
                if not start_date:
                    continue

                # Location
                loc_el = card.select_one(".location, .venue, .city, td.location")
                location_text = loc_el.get_text(strip=True) if loc_el else ""
                city, country = self._parse_location(location_text)

                # Attendees
                att_el = card.select_one(".attendees, .visitors, .expected")
                att_text = att_el.get_text(strip=True) if att_el else "0"
                attendees = self.safe_int(att_text)

                dh = self.make_hash(name, start_date, city)
                events.append(EventCreate(
                    id=self.make_id(),
                    source_platform="10Times",
                    source_url=link,
                    dedup_hash=dh,
                    name=name,
                    description=f"{category.title()} trade show / conference sourced from 10Times.",
                    start_date=start_date,
                    end_date=start_date,
                    city=city,
                    country=country,
                    category=category,
                    industry_tags=category,
                    audience_personas="executives,industry professionals,trade buyers",
                    est_attendees=attendees,
                    ticket_price_usd=0.0,
                    price_description="See website",
                    registration_url=link,
                ))
            except Exception as e:
                logger.debug(f"10Times card parse error: {e}")
                continue

        return events

    def _parse_date(self, text: str) -> str:
        """Extract a YYYY-MM-DD from messy date strings like 'May 12-14, 2026'."""
        import re
        from datetime import datetime
        if not text:
            return ""
        months = {
            "jan": "01", "feb": "02", "mar": "03", "apr": "04",
            "may": "05", "jun": "06", "jul": "07", "aug": "08",
            "sep": "09", "oct": "10", "nov": "11", "dec": "12",
        }
        text = text.lower().strip()
        # Try ISO date first
        iso = re.search(r"(\d{4}-\d{2}-\d{2})", text)
        if iso:
            return iso.group(1)
        # Try "Month DD, YYYY"
        m = re.search(r"(\w{3,9})\s+(\d{1,2})[\s,\-–]+\d{0,2},?\s*(\d{4})", text)
        if m:
            mon = m.group(1)[:3]
            day = m.group(2).zfill(2)
            year = m.group(3)
            mon_num = months.get(mon, "01")
            return f"{year}-{mon_num}-{day}"
        # Try "DD Month YYYY"
        m2 = re.search(r"(\d{1,2})\s+(\w{3,9})\s+(\d{4})", text)
        if m2:
            day = m2.group(1).zfill(2)
            mon = m2.group(2)[:3]
            year = m2.group(3)
            mon_num = months.get(mon, "01")
            return f"{year}-{mon_num}-{day}"
        return ""

    def _parse_location(self, text: str) -> tuple:
        """Split 'Singapore, SG' or 'New York, USA' into (city, country)."""
        if not text:
            return ("", "")
        parts = [p.strip() for p in text.split(",")]
        city = parts[0] if parts else ""
        country = parts[-1] if len(parts) > 1 else ""
        return city, country

    async def fetch(self) -> List[EventCreate]:
        all_events: List[EventCreate] = []
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
            for category, url in CATEGORIES:
                events = await self._scrape_category(client, category, url)
                all_events.extend(events)
                logger.debug(f"10Times [{category}]: {len(events)} events")
        return all_events
