"""Scraper — 10times.com"""
import asyncio, re, httpx
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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

MONTHS = {
    "jan":"01","feb":"02","mar":"03","apr":"04","may":"05","jun":"06",
    "jul":"07","aug":"08","sep":"09","oct":"10","nov":"11","dec":"12",
}


class Scraper10Times(BaseConnector):
    name = "10Times"

    def _parse_date(self, text: str) -> str:
        if not text: return ""
        t = text.lower().strip()
        iso = re.search(r"(\d{4}-\d{2}-\d{2})", t)
        if iso: return iso.group(1)
        m = re.search(r"(\w{3,9})\s+(\d{1,2})[\s,\-–]+\d{0,2},?\s*(\d{4})", t)
        if m:
            return f"{m.group(3)}-{MONTHS.get(m.group(1)[:3],'01')}-{m.group(2).zfill(2)}"
        m2 = re.search(r"(\d{1,2})\s+(\w{3,9})\s+(\d{4})", t)
        if m2:
            return f"{m2.group(3)}-{MONTHS.get(m2.group(2)[:3],'01')}-{m2.group(1).zfill(2)}"
        return ""

    def _parse_location(self, text: str) -> tuple:
        if not text: return ("", "")
        parts = [p.strip() for p in text.split(",")]
        return parts[0] if parts else "", parts[-1] if len(parts) > 1 else ""

    def _date_from_card(self, card) -> str:
        date_node = card.select_one("[data-start-date]")
        if date_node:
            raw = str(date_node.get("data-start-date") or "").strip().replace("/", "-")
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
                return raw
        date_el = card.select_one(".event-date, .dates, time, .date-range, td.date, [class*='date']")
        return self._parse_date(date_el.get_text(strip=True) if date_el else "")

    def _link_from_card(self, card) -> str:
        preferred = card.select_one("a.event-title[href], a[href*='/e'][href], h2 a[href], h3 a[href]")
        if preferred and preferred.get("href"):
            href = preferred.get("href", "")
            return href if href.startswith("http") else f"https://10times.com{href}"

        data_url_el = card.select_one("[data-url]")
        if data_url_el and data_url_el.get("data-url"):
            href = data_url_el.get("data-url", "")
            return href if href.startswith("http") else f"https://10times.com{href}"

        clickable = card.select_one("[onclick*='window.open']")
        if clickable:
            onclick = str(clickable.get("onclick") or "")
            match = re.search(r"window\.open\('([^']+)'", onclick)
            if match:
                href = match.group(1)
                return href if href.startswith("http") else f"https://10times.com{href}"

        any_link = card.select_one("a[href]")
        href = any_link.get("href", "") if any_link else ""
        return href if href.startswith("http") else f"https://10times.com{href}" if href else "https://10times.com"

    async def _scrape_category(self, client, category, url) -> List[EventCreate]:
        events = []
        try:
            await asyncio.sleep(settings.scrape_delay_seconds)
            r = await client.get(url, timeout=settings.scrape_timeout_seconds)
            r.raise_for_status()
        except Exception as e:
            logger.debug(f"10Times {category}: {e}")
            return events

        soup = BeautifulSoup(r.text, "html.parser")
        cards = (soup.select("div.event-item, div.event-card, li.event-listing, article.event")
                 or soup.select("tr.event-row"))

        for card in cards[:20]:
            try:
                name_el = card.select_one("h2, h3, .event-name, a.event-title, td.event-title, [data-ga-label], [data-name]")
                name = name_el.get_text(strip=True) if name_el else ""
                if not name: continue
                link = self._link_from_card(card)
                start_date = self._date_from_card(card)
                if not start_date: continue
                loc_el = card.select_one(".location, .venue, .city, td.location")
                city, country = self._parse_location(loc_el.get_text(strip=True) if loc_el else "")
                att_el = card.select_one(".attendees, .visitors, .expected")
                attendees = self.safe_int(att_el.get_text(strip=True) if att_el else "0")
                dh = self.make_hash(name, start_date, city)
                events.append(EventCreate(
                    id=self.make_id(), source_platform="10Times", source_url=link,
                    dedup_hash=dh, name=name,
                    description=f"{category.title()} trade show / conference sourced from 10Times.",
                    start_date=start_date, end_date=start_date, city=city, country=country,
                    category=category, industry_tags=category,
                    audience_personas="executives,industry professionals,trade buyers",
                    est_attendees=attendees, ticket_price_usd=0.0,
                    price_description="See website", registration_url=link,
                ))
            except Exception as e:
                logger.debug(f"10Times card parse error: {e}")
        return events

    async def fetch(self) -> List[EventCreate]:
        all_events: List[EventCreate] = []
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
            for category, url in CATEGORIES:
                evs = await self._scrape_category(client, category, url)
                all_events.extend(evs)
        return all_events
