"""
Scrapers — SACEOS (Singapore) + MyCEB (Malaysia)
Both are official government-backed MICE directories for SE Asia.
Free, no API key required.

SACEOS: Singapore Association of Convention & Exhibition Organisers & Suppliers
MyCEB:  Malaysia Convention & Exhibition Bureau
"""
import asyncio, re, httpx
from bs4 import BeautifulSoup
from typing import List
from models.event import EventCreate
from ingestion.base_connector import BaseConnector
from config import get_settings
from loguru import logger

settings = get_settings()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*",
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
    iso = re.search(r"(\d{4}-\d{2}-\d{2})", t)
    if iso:
        return iso.group(1)
    m = re.search(r"(\d{1,2})[\s\-–]+\d{0,2}\s*(\w{3,9})[,\s]+(\d{4})", t)
    if m:
        mon = MONTHS.get(m.group(2)[:3], "01")
        return f"{m.group(3)}-{mon}-{m.group(1).zfill(2)}"
    m2 = re.search(r"(\w{3,9})\s+(\d{1,2})[,\s–\-]+\d{0,2}[,\s]+(\d{4})", t)
    if m2:
        mon = MONTHS.get(m2.group(1)[:3], "01")
        return f"{m2.group(3)}-{mon}-{m2.group(2).zfill(2)}"
    m3 = re.search(r"(\d{1,2})\s+(\w{3,9})\s+(\d{4})", t)
    if m3:
        mon = MONTHS.get(m3.group(2)[:3], "01")
        return f"{m3.group(3)}-{mon}-{m3.group(1).zfill(2)}"
    return ""


# ═══════════════════════════════════════════════════════════
# SACEOS — Singapore
# ═══════════════════════════════════════════════════════════

SACEOS_URLS = [
    "https://saceos.org.sg/industry-events/",
    "https://saceos.org.sg/events/",
    "https://saceos.org.sg/calendar/",
]

class ScraperSACEOS(BaseConnector):
    name = "SACEOS"

    async def fetch(self) -> List[EventCreate]:
        events: List[EventCreate] = []
        seen: set = set()

        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
            for url in SACEOS_URLS:
                try:
                    await asyncio.sleep(settings.scrape_delay_seconds)
                    r = await client.get(url, timeout=settings.scrape_timeout_seconds)
                    r.raise_for_status()
                except Exception as e:
                    logger.debug(f"SACEOS {url}: {e}")
                    continue

                soup = BeautifulSoup(r.text, "html.parser")

                # Try multiple card selectors
                cards = (
                    soup.select("article.event, div.event-item, div.tribe-event, .tribe-events-calendar-list__event") or
                    soup.select("div.card, article.post, div.event-card") or
                    soup.select("li.event, div[class*='event']")
                )

                for card in cards[:30]:
                    try:
                        name_el = card.select_one("h2, h3, h4, .event-title, a.tribe-event-url, .entry-title")
                        if not name_el:
                            continue
                        name = name_el.get_text(strip=True)
                        if not name or len(name) < 5:
                            continue

                        link_el = card.select_one("a[href]") or name_el.find_parent("a")
                        href = link_el.get("href", "") if link_el else url
                        link = href if href.startswith("http") else f"https://saceos.org.sg{href}"

                        date_el = card.select_one(
                            "time, .event-date, .tribe-event-date-start, "
                            ".date, abbr[title], [class*='date']"
                        )
                        date_text = ""
                        if date_el:
                            date_text = date_el.get("datetime", "") or date_el.get("title", "") or date_el.get_text(strip=True)

                        start_date = _parse_date(date_text)
                        if not start_date:
                            # Search the whole card text
                            start_date = _parse_date(card.get_text(" ", strip=True))
                        if not start_date:
                            continue

                        desc_el = card.select_one("p, .excerpt, .description, .tribe-events-schedule")
                        desc = desc_el.get_text(strip=True)[:300] if desc_el else ""

                        dh = self.make_hash(name, start_date, "Singapore")
                        if dh in seen:
                            continue
                        seen.add(dh)

                        events.append(EventCreate(
                            id=self.make_id(), source_platform="SACEOS",
                            source_url=link, dedup_hash=dh,
                            name=name,
                            description=f"Singapore MICE industry event. {desc}".strip(),
                            start_date=start_date, end_date=start_date,
                            city="Singapore", country="Singapore",
                            category="conference",
                            industry_tags="tech,finance,logistics,manufacturing,trade show,MICE,ASEAN,events industry",
                            audience_personas=(
                                "CIO,CTO,CEO,COO,event organiser,exhibition manager,"
                                "procurement head,MICE professional,hotel manager,government official"
                            ),
                            est_attendees=800,
                            ticket_price_usd=0.0, price_description="See website",
                            registration_url=link,
                        ))
                    except Exception as e:
                        logger.debug(f"SACEOS card: {e}")

        logger.info(f"SACEOS: {len(events)} events.")
        return events


# ═══════════════════════════════════════════════════════════
# MyCEB — Malaysia
# ═══════════════════════════════════════════════════════════

MYCEB_URLS = [
    "https://www.myceb.com.my/index.cfm/events/",
    "https://www.myceb.com.my/events/",
    "https://www.myceb.com.my/index.cfm/business-events/upcoming-events/",
    "https://malaysia.travel/events",
]

class ScraperMyCEB(BaseConnector):
    name = "MyCEB"

    async def fetch(self) -> List[EventCreate]:
        events: List[EventCreate] = []
        seen: set = set()

        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
            for url in MYCEB_URLS:
                try:
                    await asyncio.sleep(settings.scrape_delay_seconds)
                    r = await client.get(url, timeout=settings.scrape_timeout_seconds)
                    r.raise_for_status()
                except Exception as e:
                    logger.debug(f"MyCEB {url}: {e}")
                    continue

                soup = BeautifulSoup(r.text, "html.parser")

                cards = (
                    soup.select("div.event-item, article.event, .event-card, .event-listing") or
                    soup.select("div.card, article, li.event") or
                    soup.select("div[class*='event'], div[class*='listing']")
                )

                # Also check for table-based listings
                if not cards:
                    cards = soup.select("table tr")[1:31]

                for card in cards[:30]:
                    try:
                        name_el = card.select_one("h2, h3, h4, .event-title, .title, a")
                        if not name_el:
                            continue
                        name = name_el.get_text(strip=True)
                        if not name or len(name) < 5:
                            continue

                        link_el = card.select_one("a[href]")
                        href    = link_el.get("href", "") if link_el else url
                        link    = href if href.startswith("http") else f"https://www.myceb.com.my{href}"

                        date_el   = card.select_one("time, .date, .event-date, [class*='date']")
                        date_text = ""
                        if date_el:
                            date_text = date_el.get("datetime", "") or date_el.get_text(strip=True)
                        start_date = _parse_date(date_text) or _parse_date(card.get_text(" ", strip=True))
                        if not start_date:
                            continue

                        loc_el = card.select_one(".location, .venue, .city, [class*='venue']")
                        city   = loc_el.get_text(strip=True) if loc_el else "Kuala Lumpur"
                        if not city:
                            city = "Kuala Lumpur"

                        att_el   = card.select_one(".attendees, .visitors, [class*='attend']")
                        att_text = att_el.get_text(strip=True) if att_el else ""
                        attendees = int(re.search(r"\d+", att_text.replace(",", "")).group()) if re.search(r"\d+", att_text) else 600

                        dh = self.make_hash(name, start_date, city)
                        if dh in seen:
                            continue
                        seen.add(dh)

                        events.append(EventCreate(
                            id=self.make_id(), source_platform="MyCEB",
                            source_url=link, dedup_hash=dh,
                            name=name,
                            description=f"Malaysia MICE business event. Source: MyCEB (Malaysia Convention & Exhibition Bureau).",
                            start_date=start_date, end_date=start_date,
                            city=city, country="Malaysia",
                            category="conference",
                            industry_tags=(
                                "MICE,business,tech,finance,logistics,manufacturing,"
                                "healthcare,trade show,Malaysia,ASEAN"
                            ),
                            audience_personas=(
                                "CEO,COO,CIO,government official,MICE professional,"
                                "procurement head,hotel manager,event organiser,trade buyer"
                            ),
                            est_attendees=attendees,
                            ticket_price_usd=0.0, price_description="See website",
                            registration_url=link,
                        ))
                    except Exception as e:
                        logger.debug(f"MyCEB card: {e}")

        logger.info(f"MyCEB: {len(events)} events.")
        return events
