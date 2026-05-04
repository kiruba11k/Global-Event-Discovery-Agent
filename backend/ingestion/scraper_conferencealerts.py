"""Scraper — conferencealerts.com"""
import asyncio, re, httpx
from bs4 import BeautifulSoup
from typing import List
from models.event import EventCreate
from ingestion.base_connector import BaseConnector
from config import get_settings
from loguru import logger

settings = get_settings()

CATEGORY_URLS = [
    ("computer-science",        "https://conferencealerts.com/topic-listing?topic=computer-science"),
    ("artificial-intelligence", "https://conferencealerts.com/topic-listing?topic=artificial-intelligence"),
    ("finance",                 "https://conferencealerts.com/topic-listing?topic=finance"),
    ("healthcare",              "https://conferencealerts.com/topic-listing?topic=health-sciences"),
    ("management",              "https://conferencealerts.com/topic-listing?topic=management"),
    ("engineering",             "https://conferencealerts.com/topic-listing?topic=engineering"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; EventBot/1.0; research)",
    "Accept": "text/html,application/xhtml+xml",
}

MONTHS = {
    "january":"01","february":"02","march":"03","april":"04","may":"05","june":"06",
    "july":"07","august":"08","september":"09","october":"10","november":"11","december":"12",
    "jan":"01","feb":"02","mar":"03","apr":"04","jun":"06","jul":"07","aug":"08",
    "sep":"09","oct":"10","nov":"11","dec":"12",
}


def _parse_date(text: str) -> str:
    text = text.strip().lower()
    iso = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if iso: return iso.group(1)
    m = re.search(r"(\w+)\s+(\d{1,2})[,\s\-–]+(\d{4})", text)
    if m: return f"{m.group(3)}-{MONTHS.get(m.group(1)[:3],'01')}-{m.group(2).zfill(2)}"
    m2 = re.search(r"(\d{1,2})[–\-]?\d{0,2}\s+(\w+),?\s+(\d{4})", text)
    if m2: return f"{m2.group(3)}-{MONTHS.get(m2.group(2)[:3],'01')}-{m2.group(1).zfill(2)}"
    return ""


class ScraperConferenceAlerts(BaseConnector):
    name = "ConferenceAlerts"

    async def fetch(self) -> List[EventCreate]:
        all_events: List[EventCreate] = []
        seen = set()

        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=15) as client:
            for category, url in CATEGORY_URLS:
                await asyncio.sleep(settings.scrape_delay_seconds)
                try:
                    r = await client.get(url)
                    r.raise_for_status()
                except Exception as e:
                    logger.debug(f"ConferenceAlerts {category}: {e}")
                    continue

                soup = BeautifulSoup(r.text, "html.parser")
                rows = soup.select("table tr, .conference-list li, .conf-item") or soup.select("div.event")

                for row in rows[:25]:
                    try:
                        name_el = row.select_one("a.conf-title, td a, h3 a, .title a, a[href*='conference']")
                        if not name_el: continue
                        name = name_el.get_text(strip=True)
                        link = name_el.get("href", "")
                        if not link.startswith("http"):
                            link = "https://conferencealerts.com" + link
                        date_el = row.select_one(".date, td.dates, .conf-date, time")
                        start_date = _parse_date(date_el.get_text(strip=True) if date_el else "")
                        if not start_date: continue
                        loc_el = row.select_one(".location, td.venue, .conf-venue, .place")
                        location = loc_el.get_text(strip=True) if loc_el else ""
                        parts = [p.strip() for p in location.split(",")]
                        city = parts[0] if parts else ""
                        country = parts[-1] if len(parts) > 1 else ""
                        dh = self.make_hash(name, start_date, city)
                        if dh in seen: continue
                        seen.add(dh)
                        all_events.append(EventCreate(
                            id=self.make_id(), source_platform="ConferenceAlerts",
                            source_url=link, dedup_hash=dh, name=name,
                            description=f"Professional conference in {category} sourced from ConferenceAlerts.",
                            start_date=start_date, end_date=start_date, city=city, country=country,
                            category=category, industry_tags=category,
                            audience_personas="researchers,academics,professionals,industry leaders",
                            est_attendees=200, ticket_price_usd=0.0,
                            price_description="See website", registration_url=link,
                        ))
                    except Exception as e:
                        logger.debug(f"ConferenceAlerts row parse: {e}")

        logger.info(f"ConferenceAlerts: {len(all_events)} events.")
        return all_events
