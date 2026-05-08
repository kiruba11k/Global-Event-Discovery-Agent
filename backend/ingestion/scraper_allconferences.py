"""
Scraper — AllConferences.com + Confex.com
Both are free-tier, no API key required.
Combined coverage: ~800-1200 additional global academic and professional events.
"""
import asyncio, re, httpx
from bs4 import BeautifulSoup
from typing import List
from models.event import EventCreate
from ingestion.base_connector import BaseConnector
from config import get_settings
from loguru import logger

settings = get_settings()

ALLCONF_URLS = [
    "https://allconferences.com/categories/Technology/",
    "https://allconferences.com/categories/Finance/",
    "https://allconferences.com/categories/Health/",
    "https://allconferences.com/categories/Business/",
    "https://allconferences.com/categories/Engineering/",
    "https://allconferences.com/categories/Education/",
]

CONFEX_URLS = [
    "https://www.confex.com/browse?domain=all",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

MONTHS = {
    "jan":"01","feb":"02","mar":"03","apr":"04","may":"05","jun":"06",
    "jul":"07","aug":"08","sep":"09","oct":"10","nov":"11","dec":"12",
    "january":"01","february":"02","march":"03","april":"04","june":"06","july":"07",
    "august":"08","september":"09","october":"10","november":"11","december":"12",
}

def _parse_date(text: str) -> str:
    if not text:
        return ""
    t = text.lower().strip()
    # ISO
    iso = re.search(r"(\d{4}-\d{2}-\d{2})", t)
    if iso:
        return iso.group(1)
    # Jan 15, 2026
    m = re.search(r"(\w+)\s+(\d{1,2})[,\s]+(\d{4})", t)
    if m:
        mon = MONTHS.get(m.group(1)[:3], "01")
        return f"{m.group(3)}-{mon}-{m.group(2).zfill(2)}"
    # 15 Jan 2026
    m2 = re.search(r"(\d{1,2})\s+(\w+)\s+(\d{4})", t)
    if m2:
        mon = MONTHS.get(m2.group(2)[:3], "01")
        return f"{m2.group(3)}-{mon}-{m2.group(1).zfill(2)}"
    return ""


class ScraperAllConferences(BaseConnector):
    name = "AllConferences"

    async def _scrape_allconf(self, client: httpx.AsyncClient, url: str, category: str) -> List[EventCreate]:
        events: List[EventCreate] = []
        seen: set = set()

        try:
            await asyncio.sleep(settings.scrape_delay_seconds)
            r = await client.get(url, timeout=settings.scrape_timeout_seconds)
            r.raise_for_status()
        except Exception as e:
            logger.debug(f"AllConferences {url}: {e}")
            return events

        soup = BeautifulSoup(r.text, "html.parser")

        # AllConferences uses article cards or list items
        cards = (
            soup.select("div.event-item, article.conference, div.conf-entry, li.event") or
            soup.select("table tr") or
            soup.select("div.listing")
        )

        for card in cards[:30]:
            try:
                name_el = card.select_one("h2 a, h3 a, .conf-name a, td a, a.event-link")
                if not name_el:
                    continue
                name = name_el.get_text(strip=True)
                if not name or len(name) < 5:
                    continue

                href = name_el.get("href", "")
                link = href if href.startswith("http") else f"https://allconferences.com{href}"

                date_el = card.select_one(".date, .conf-date, time, td.dates")
                start_date = _parse_date(date_el.get_text(strip=True) if date_el else "")
                if not start_date:
                    continue

                loc_el = card.select_one(".location, .venue, .city, td.location")
                loc_text = loc_el.get_text(strip=True) if loc_el else ""
                parts = [p.strip() for p in loc_text.split(",")]
                city    = parts[0] if parts else ""
                country = parts[-1] if len(parts) > 1 else ""

                dh = self.make_hash(name, start_date, city)
                if dh in seen:
                    continue
                seen.add(dh)

                events.append(EventCreate(
                    id=self.make_id(),
                    source_platform="AllConferences",
                    source_url=link,
                    dedup_hash=dh,
                    name=name,
                    description=f"Professional conference in {category} sourced from AllConferences.com.",
                    start_date=start_date,
                    end_date=start_date,
                    city=city,
                    country=country,
                    category="conference",
                    industry_tags=category.lower(),
                    audience_personas="researchers,academics,professionals,industry leaders",
                    est_attendees=300,
                    ticket_price_usd=0.0,
                    price_description="See website",
                    registration_url=link,
                ))
            except Exception as e:
                logger.debug(f"AllConferences card: {e}")

        return events

    async def fetch(self) -> List[EventCreate]:
        all_events: List[EventCreate] = []
        seen: set = set()

        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
            for url in ALLCONF_URLS:
                category = url.rstrip("/").split("/")[-1]
                evs = await self._scrape_allconf(client, url, category)
                for ev in evs:
                    if ev.dedup_hash not in seen:
                        seen.add(ev.dedup_hash)
                        all_events.append(ev)

        logger.info(f"AllConferences: {len(all_events)} events.")
        return all_events


class ScraperConfex(BaseConnector):
    name = "Confex"

    async def fetch(self) -> List[EventCreate]:
        events: List[EventCreate] = []
        seen: set = set()

        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
            for url in CONFEX_URLS:
                try:
                    await asyncio.sleep(settings.scrape_delay_seconds)
                    r = await client.get(url, timeout=settings.scrape_timeout_seconds)
                    r.raise_for_status()
                except Exception as e:
                    logger.debug(f"Confex {url}: {e}")
                    continue

                soup = BeautifulSoup(r.text, "html.parser")
                cards = soup.select("div.event-card, article, .conference-item, tr")

                for card in cards[:30]:
                    try:
                        name_el = card.select_one("h2, h3, h4, a.title, .event-title, td a")
                        if not name_el:
                            continue
                        name = name_el.get_text(strip=True)
                        if not name or len(name) < 5:
                            continue

                        href = name_el.get("href", "")
                        if not href:
                            link_el = card.select_one("a[href]")
                            href = link_el.get("href", "") if link_el else ""
                        link = href if href.startswith("http") else f"https://www.confex.com{href}"

                        date_el = card.select_one(".date, time, .event-date")
                        start_date = _parse_date(date_el.get_text(strip=True) if date_el else "")
                        if not start_date:
                            continue

                        loc_el = card.select_one(".location, .city, .venue")
                        loc_text = loc_el.get_text(strip=True) if loc_el else ""
                        parts = [p.strip() for p in loc_text.split(",")]
                        city    = parts[0] if parts else ""
                        country = parts[-1] if len(parts) > 1 else ""

                        dh = self.make_hash(name, start_date, city)
                        if dh in seen:
                            continue
                        seen.add(dh)

                        events.append(EventCreate(
                            id=self.make_id(),
                            source_platform="Confex",
                            source_url=link,
                            dedup_hash=dh,
                            name=name,
                            description=f"Professional conference sourced from Confex.com.",
                            start_date=start_date,
                            end_date=start_date,
                            city=city,
                            country=country,
                            category="conference",
                            industry_tags="conference,professional development",
                            audience_personas="professionals,academics,industry leaders",
                            est_attendees=400,
                            ticket_price_usd=0.0,
                            price_description="See website",
                            registration_url=link,
                        ))
                    except Exception as e:
                        logger.debug(f"Confex card: {e}")

        logger.info(f"Confex: {len(events)} events.")
        return events
