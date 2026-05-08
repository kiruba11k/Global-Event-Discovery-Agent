"""
Scraper — Wikipedia List of Trade Fairs
URL: https://en.wikipedia.org/wiki/List_of_trade_fairs
This is one of the most comprehensive free databases of global trade shows.
Scrapes ~600-800 events across all industries globally.
"""
import asyncio, re, httpx
from bs4 import BeautifulSoup
from datetime import date, datetime
from typing import List
from models.event import EventCreate
from ingestion.base_connector import BaseConnector
from config import get_settings
from loguru import logger

settings = get_settings()

WIKI_URLS = [
    "https://en.wikipedia.org/wiki/List_of_trade_fairs",
    "https://en.wikipedia.org/wiki/List_of_world_fairs_and_expositions",
    "https://en.wikipedia.org/wiki/List_of_technology_conferences",
]

HEADERS = {
    "User-Agent": "EventBot/1.0 (educational project; contact@example.com)",
    "Accept": "text/html,application/xhtml+xml",
}

# Industry inference from page section headings / article categories
SECTION_TO_INDUSTRY = {
    "technology":       "tech,software,AI",
    "information":      "tech,data",
    "finance":          "finance,fintech,banking",
    "health":           "healthcare,medtech",
    "medical":          "healthcare",
    "pharma":           "healthcare,pharma",
    "logistics":        "logistics,supply chain",
    "transport":        "logistics,transport",
    "energy":           "energy,cleantech",
    "manufacturing":    "manufacturing,industrial",
    "retail":           "retail,ecommerce",
    "food":             "food,retail,FMCG",
    "agriculture":      "agriculture,food",
    "construction":     "construction,real estate",
    "aerospace":        "aerospace,manufacturing",
    "defence":          "defence,security",
    "automotive":       "automotive,manufacturing",
    "marketing":        "marketing,advertising",
    "media":            "media,marketing",
    "real estate":      "real estate,construction",
    "hr":               "HR tech,workforce",
    "education":        "education,edtech",
    "gaming":           "gaming,tech",
    "security":         "cybersecurity,security",
    "chemical":         "chemicals,manufacturing",
    "textile":          "textile,fashion,retail",
    "jewellery":        "jewellery,retail,luxury",
}


def _infer_industry(text: str, section: str = "") -> str:
    combined = f"{text} {section}".lower()
    matched = []
    for kw, tags in SECTION_TO_INDUSTRY.items():
        if kw in combined:
            matched.extend(tags.split(","))
    return ",".join(dict.fromkeys(matched)) if matched else "trade show,conference"


def _parse_country(text: str) -> tuple:
    """Attempt to extract city/country from location text."""
    # Common patterns: "Berlin, Germany" or "Las Vegas, USA"
    parts = [p.strip() for p in text.split(",")]
    if len(parts) >= 2:
        return parts[0], parts[-1]
    return text.strip(), ""


def _next_occurrence_date(text: str) -> str:
    """
    Wikipedia often has dates like 'annually in March' or '2025'.
    Try to produce a plausible start date.
    """
    today = date.today()
    year  = today.year

    months = {
        "january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
        "july":7,"august":8,"september":9,"october":10,"november":11,"december":12,
        "jan":1,"feb":2,"mar":3,"apr":4,"jun":6,"jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12,
    }

    # Explicit year
    year_m = re.search(r"20(2[4-9]|3\d)", text)
    if year_m:
        year = int(year_m.group())

    # Month name
    text_l = text.lower()
    for mname, mnum in months.items():
        if mname in text_l:
            candidate = date(year, mnum, 1)
            if candidate < today:
                candidate = date(year + 1, mnum, 1)
            return candidate.isoformat()

    # No month — use Q2 of next year as placeholder (better than dropping the event)
    return date(year + 1 if today.month >= 10 else year, 6, 1).isoformat()


class ScraperWikipediaTrades(BaseConnector):
    name = "Wikipedia"

    async def _scrape_page(self, client: httpx.AsyncClient, url: str) -> List[EventCreate]:
        events: List[EventCreate] = []
        seen: set = set()

        try:
            await asyncio.sleep(settings.scrape_delay_seconds)
            r = await client.get(url, timeout=settings.scrape_timeout_seconds)
            r.raise_for_status()
        except Exception as e:
            logger.debug(f"Wikipedia fetch {url}: {e}")
            return events

        soup = BeautifulSoup(r.text, "html.parser")
        content = soup.find("div", {"id": "mw-content-text"})
        if not content:
            return events

        current_section = "general"

        for element in content.find_all(["h2", "h3", "tr", "li"]):
            tag = element.name

            # Track section heading for industry inference
            if tag in ("h2", "h3"):
                heading_text = element.get_text(" ", strip=True).lower()
                for kw in SECTION_TO_INDUSTRY:
                    if kw in heading_text:
                        current_section = kw
                        break
                continue

            # Table rows
            if tag == "tr":
                cells = element.find_all(["th", "td"])
                if len(cells) < 2:
                    continue
                name = cells[0].get_text(" ", strip=True)
                if not name or len(name) < 4:
                    continue

                location_text = cells[1].get_text(" ", strip=True) if len(cells) > 1 else ""
                date_text     = cells[2].get_text(" ", strip=True) if len(cells) > 2 else ""
                desc_text     = cells[3].get_text(" ", strip=True) if len(cells) > 3 else ""

                city, country = _parse_country(location_text)
                start_date    = _next_occurrence_date(date_text or location_text)
                industry      = _infer_industry(f"{name} {desc_text}", current_section)

                # Link
                link_el = cells[0].find("a", href=True)
                link    = ""
                if link_el:
                    href = link_el["href"]
                    link = f"https://en.wikipedia.org{href}" if href.startswith("/") else href

                dh = self.make_hash(name, start_date, city)
                if dh in seen:
                    continue
                seen.add(dh)

                events.append(EventCreate(
                    id=self.make_id(),
                    source_platform="Wikipedia",
                    source_url=link or url,
                    dedup_hash=dh,
                    name=name,
                    description=f"Global trade fair: {name}. {desc_text[:300]}".strip(),
                    short_summary=f"{city}, {country}".strip(", "),
                    start_date=start_date,
                    end_date=start_date,
                    city=city,
                    country=country,
                    category="trade show",
                    industry_tags=industry,
                    audience_personas="executives,trade buyers,industry professionals,procurement heads",
                    est_attendees=2000,
                    ticket_price_usd=0.0,
                    price_description="See website",
                    registration_url=link or url,
                ))

            # List items
            elif tag == "li":
                text = element.get_text(" ", strip=True)
                if len(text) < 6 or len(text) > 200:
                    continue
                link_el = element.find("a", href=True)
                if not link_el:
                    continue

                name = link_el.get_text(strip=True)
                if not name or len(name) < 4:
                    continue
                href = link_el["href"]
                link = f"https://en.wikipedia.org{href}" if href.startswith("/") else href
                start_date = _next_occurrence_date(text)
                city, country = _parse_country(re.sub(r"\[.*?\]", "", text))
                industry = _infer_industry(name, current_section)

                dh = self.make_hash(name, start_date, city)
                if dh in seen:
                    continue
                seen.add(dh)

                events.append(EventCreate(
                    id=self.make_id(),
                    source_platform="Wikipedia",
                    source_url=link,
                    dedup_hash=dh,
                    name=name,
                    description=f"Trade fair/conference: {name}",
                    start_date=start_date,
                    end_date=start_date,
                    city=city,
                    country=country,
                    category="trade show",
                    industry_tags=industry,
                    audience_personas="executives,trade buyers,industry professionals",
                    est_attendees=1500,
                    ticket_price_usd=0.0,
                    price_description="See website",
                    registration_url=link,
                ))

        logger.info(f"Wikipedia {url}: {len(events)} events parsed.")
        return events

    async def fetch(self) -> List[EventCreate]:
        all_events: List[EventCreate] = []
        seen_hashes: set = set()

        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
            for url in WIKI_URLS:
                evs = await self._scrape_page(client, url)
                for ev in evs:
                    if ev.dedup_hash not in seen_hashes:
                        seen_hashes.add(ev.dedup_hash)
                        all_events.append(ev)

        logger.info(f"Wikipedia total: {len(all_events)} unique events.")
        return all_events
