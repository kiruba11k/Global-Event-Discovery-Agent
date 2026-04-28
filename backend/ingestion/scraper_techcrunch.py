"""
Scraper — TechCrunch Events page
techcrunch.com/events
"""
import asyncio
import httpx
from bs4 import BeautifulSoup
from typing import List
from models.event import EventCreate
from ingestion.base_connector import BaseConnector
from config import get_settings
from loguru import logger
import re

settings = get_settings()

TC_EVENTS_URL = "https://techcrunch.com/events/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html",
}

MONTHS = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}


def parse_tc_date(text: str) -> str:
    text = text.strip().lower()
    m = re.search(r"(\w{3,9})\s+(\d{1,2})[,\s–\-]+\d{0,2},?\s*(\d{4})", text)
    if m:
        mon = MONTHS.get(m.group(1)[:3], "01")
        return f"{m.group(3)}-{mon}-{m.group(2).zfill(2)}"
    m2 = re.search(r"(\w{3,9})\s+(\d{1,2}),\s*(\d{4})", text)
    if m2:
        mon = MONTHS.get(m2.group(1)[:3], "01")
        return f"{m2.group(3)}-{mon}-{m2.group(2).zfill(2)}"
    return ""


class ScraperTechCrunch(BaseConnector):
    name = "TechCrunch"

    async def fetch(self) -> List[EventCreate]:
        events: List[EventCreate] = []
        await asyncio.sleep(settings.scrape_delay_seconds)

        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=15) as client:
            try:
                r = await client.get(TC_EVENTS_URL)
                r.raise_for_status()
            except Exception as e:
                logger.debug(f"TechCrunch events: {e}")
                return events

        soup = BeautifulSoup(r.text, "html.parser")
        cards = soup.select("article, .event-card, .event-item, div[class*='event']")
        if not cards:
            cards = soup.select("a[href*='/events/']")

        seen = set()
        for card in cards[:20]:
            try:
                name_el = card.select_one("h2, h3, h4, .event-title, strong")
                if not name_el:
                    continue
                name = name_el.get_text(strip=True)
                if not name or len(name) < 5:
                    continue

                link_el = card.select_one("a[href]")
                link = link_el.get("href", "") if link_el else TC_EVENTS_URL

                date_el = card.select_one("time, .date, .event-date, p")
                date_text = date_el.get_text(strip=True) if date_el else ""
                start_date = parse_tc_date(date_text)
                if not start_date:
                    from datetime import date
                    start_date = date.today().isoformat()

                loc_el = card.select_one(".location, .venue, .city")
                city = loc_el.get_text(strip=True) if loc_el else "USA"

                dh = self.make_hash(name, start_date, city)
                if dh in seen:
                    continue
                seen.add(dh)

                events.append(EventCreate(
                    id=self.make_id(),
                    source_platform="TechCrunch",
                    source_url=link if link.startswith("http") else f"https://techcrunch.com{link}",
                    dedup_hash=dh,
                    name=name,
                    description="TechCrunch flagship event for startup founders, investors and tech leaders.",
                    start_date=start_date,
                    end_date=start_date,
                    city=city,
                    country="USA",
                    category="tech",
                    industry_tags="startup,venture capital,tech,AI,product",
                    audience_personas="founders,investors,VCs,CTOs,product managers",
                    est_attendees=2000,
                    ticket_price_usd=0.0,
                    price_description="See TechCrunch website",
                    registration_url=link if link.startswith("http") else f"https://techcrunch.com{link}",
                ))
            except Exception as e:
                logger.debug(f"TechCrunch card: {e}")

        logger.info(f"TechCrunch: {len(events)} events.")
        return events
