"""
Scraper — EventsEye.com
The single most comprehensive free global trade show directory.
Covers all industries, all continents, 12,000+ events indexed.

Strategy: scrape by industry category pages + key country pages.
EventsEye is respectful to bots but expects a real UA and delays.
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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.eventseye.com/",
}

# All industry category slugs on EventsEye
CATEGORY_PAGES = [
    ("agriculture",    "https://www.eventseye.com/fairs/c1_trade-shows-agriculture.html"),
    ("automotive",     "https://www.eventseye.com/fairs/c1_trade-shows-automotive.html"),
    ("aviation",       "https://www.eventseye.com/fairs/c1_trade-shows-aviation-aerospace.html"),
    ("building",       "https://www.eventseye.com/fairs/c1_trade-shows-building.html"),
    ("business",       "https://www.eventseye.com/fairs/c1_trade-shows-business.html"),
    ("chemicals",      "https://www.eventseye.com/fairs/c1_trade-shows-chemicals.html"),
    ("clothing",       "https://www.eventseye.com/fairs/c1_trade-shows-clothing-textiles.html"),
    ("communications", "https://www.eventseye.com/fairs/c1_trade-shows-communications-it.html"),
    ("education",      "https://www.eventseye.com/fairs/c1_trade-shows-education.html"),
    ("electronics",    "https://www.eventseye.com/fairs/c1_trade-shows-electronics.html"),
    ("energy",         "https://www.eventseye.com/fairs/c1_trade-shows-energy-environment.html"),
    ("finance",        "https://www.eventseye.com/fairs/c1_trade-shows-finance.html"),
    ("food",           "https://www.eventseye.com/fairs/c1_trade-shows-food-beverages.html"),
    ("health",         "https://www.eventseye.com/fairs/c1_trade-shows-health-medical.html"),
    ("industry",       "https://www.eventseye.com/fairs/c1_trade-shows-industry-manufacturing.html"),
    ("jewellery",      "https://www.eventseye.com/fairs/c1_trade-shows-jewellery.html"),
    ("logistics",      "https://www.eventseye.com/fairs/c1_trade-shows-logistics.html"),
    ("media",          "https://www.eventseye.com/fairs/c1_trade-shows-media-entertainment.html"),
    ("real-estate",    "https://www.eventseye.com/fairs/c1_trade-shows-real-estate.html"),
    ("retail",         "https://www.eventseye.com/fairs/c1_trade-shows-retail.html"),
    ("sport",          "https://www.eventseye.com/fairs/c1_trade-shows-sport.html"),
    ("travel",         "https://www.eventseye.com/fairs/c1_trade-shows-travel-tourism.html"),
]

# Key country pages for deeper regional coverage
COUNTRY_PAGES = [
    ("USA",          "https://www.eventseye.com/fairs/p11_trade-shows-united-states.html"),
    ("Germany",      "https://www.eventseye.com/fairs/p3_trade-shows-germany.html"),
    ("UAE",          "https://www.eventseye.com/fairs/p30_trade-shows-united-arab-emirates.html"),
    ("China",        "https://www.eventseye.com/fairs/p6_trade-shows-china.html"),
    ("India",        "https://www.eventseye.com/fairs/p22_trade-shows-india.html"),
    ("UK",           "https://www.eventseye.com/fairs/p4_trade-shows-united-kingdom.html"),
    ("France",       "https://www.eventseye.com/fairs/p5_trade-shows-france.html"),
    ("Singapore",    "https://www.eventseye.com/fairs/p33_trade-shows-singapore.html"),
    ("Japan",        "https://www.eventseye.com/fairs/p14_trade-shows-japan.html"),
    ("Australia",    "https://www.eventseye.com/fairs/p18_trade-shows-australia.html"),
    ("Canada",       "https://www.eventseye.com/fairs/p15_trade-shows-canada.html"),
    ("Netherlands",  "https://www.eventseye.com/fairs/p9_trade-shows-netherlands.html"),
    ("Spain",        "https://www.eventseye.com/fairs/p8_trade-shows-spain.html"),
    ("Italy",        "https://www.eventseye.com/fairs/p7_trade-shows-italy.html"),
    ("South Korea",  "https://www.eventseye.com/fairs/p20_trade-shows-south-korea.html"),
    ("Malaysia",     "https://www.eventseye.com/fairs/p34_trade-shows-malaysia.html"),
    ("Brazil",       "https://www.eventseye.com/fairs/p25_trade-shows-brazil.html"),
    ("Thailand",     "https://www.eventseye.com/fairs/p35_trade-shows-thailand.html"),
    ("Hong Kong",    "https://www.eventseye.com/fairs/p13_trade-shows-hong-kong.html"),
    ("Saudi Arabia", "https://www.eventseye.com/fairs/p31_trade-shows-saudi-arabia.html"),
]

MONTHS = {
    "jan":"01","feb":"02","mar":"03","apr":"04","may":"05","jun":"06",
    "jul":"07","aug":"08","sep":"09","oct":"10","nov":"11","dec":"12",
    "january":"01","february":"02","march":"03","april":"04","june":"06","july":"07",
    "august":"08","september":"09","october":"10","november":"11","december":"12",
}

# industry category → tags
CAT_TAGS = {
    "agriculture":    "agriculture,food,farming",
    "automotive":     "automotive,manufacturing,technology",
    "aviation":       "aviation,aerospace,manufacturing",
    "building":       "construction,real estate,architecture",
    "business":       "business services,management,consulting",
    "chemicals":      "chemicals,manufacturing,pharma",
    "clothing":       "fashion,textiles,retail",
    "communications": "tech,telecommunications,IT,software",
    "education":      "education,edtech,training",
    "electronics":    "electronics,tech,semiconductor",
    "energy":         "energy,cleantech,sustainability,ESG",
    "finance":        "finance,fintech,banking,insurance",
    "food":           "food,beverages,FMCG,retail",
    "health":         "healthcare,medtech,pharma,biotech",
    "industry":       "manufacturing,industrial,automation,IoT",
    "jewellery":      "jewellery,luxury,retail",
    "logistics":      "logistics,supply chain,freight,shipping",
    "media":          "media,entertainment,marketing,advertising",
    "real-estate":    "real estate,construction,property",
    "retail":         "retail,ecommerce,consumer goods,FMCG",
    "sport":          "sports,health,wellness",
    "travel":         "travel,tourism,hospitality",
}

PERSONA_MAP = {
    "agriculture":    "agri-business leader,procurement head,farm owner",
    "automotive":     "COO,VP manufacturing,fleet manager,CTO",
    "aviation":       "COO,VP operations,CTO,procurement head",
    "building":       "CEO,COO,project director,real estate developer",
    "business":       "CEO,COO,VP operations,business development manager",
    "chemicals":      "VP manufacturing,procurement head,R&D director",
    "clothing":       "CMO,merchandising director,VP retail,buyer",
    "communications": "CIO,CTO,CDO,VP engineering,CISO",
    "education":      "CHRO,learning & development director,VP HR",
    "electronics":    "CTO,VP engineering,product head,R&D director",
    "energy":         "CEO,sustainability director,COO,government official",
    "finance":        "CFO,CTO,head of payments,CEO,digital banking leader",
    "food":           "CMO,VP retail,procurement head,category manager",
    "health":         "hospital CIO,healthcare administrator,CMO,CDO",
    "industry":       "COO,VP manufacturing,plant manager,CTO",
    "jewellery":      "CMO,merchandising director,VP retail",
    "logistics":      "supply chain head,COO,VP logistics,fleet manager",
    "media":          "CMO,marketing director,content head,CRO",
    "real-estate":    "CEO,COO,real estate developer,CFO",
    "retail":         "CMO,VP ecommerce,VP retail,CTO",
    "sport":          "COO,VP marketing,events director",
    "travel":         "CEO,VP sales,marketing director,travel buyer",
}


def _parse_date(text: str) -> str:
    if not text:
        return ""
    t = text.lower().strip()
    iso = re.search(r"(\d{4}-\d{2}-\d{2})", t)
    if iso:
        return iso.group(1)
    # "15-18 Mar 2026" or "Mar 15-18, 2026"
    m = re.search(r"(\d{1,2})[\s\-–]+\d{0,2}\s*(\w{3,9})[,\s]+(\d{4})", t)
    if m:
        mon = MONTHS.get(m.group(2)[:3], "01")
        return f"{m.group(3)}-{mon}-{m.group(1).zfill(2)}"
    m2 = re.search(r"(\w{3,9})\s+(\d{1,2})[\s\-–,]+\d{0,2}[,\s]+(\d{4})", t)
    if m2:
        mon = MONTHS.get(m2.group(1)[:3], "01")
        return f"{m2.group(3)}-{mon}-{m2.group(2).zfill(2)}"
    m3 = re.search(r"(\d{1,2})\s+(\w{3,9})\s+(\d{4})", t)
    if m3:
        mon = MONTHS.get(m3.group(2)[:3], "01")
        return f"{m3.group(3)}-{mon}-{m3.group(1).zfill(2)}"
    return ""


def _parse_attendees(text: str) -> int:
    if not text:
        return 1500
    t = text.lower().replace(",", "").replace("+", "")
    m = re.search(r"(\d+)\s*k", t)
    if m:
        return int(m.group(1)) * 1000
    m2 = re.search(r"(\d+)", t)
    if m2:
        return int(m2.group(1))
    return 1500


class ScraperEventsEye(BaseConnector):
    name = "EventsEye"

    async def _scrape_page(
        self,
        client: httpx.AsyncClient,
        url: str,
        industry_key: str,
        country_override: str = "",
    ) -> List[EventCreate]:
        events: List[EventCreate] = []
        seen: set = set()

        try:
            await asyncio.sleep(settings.scrape_delay_seconds + 1)  # extra polite
            r = await client.get(url, timeout=settings.scrape_timeout_seconds)
            r.raise_for_status()
        except Exception as e:
            logger.debug(f"EventsEye {url}: {e}")
            return events

        soup = BeautifulSoup(r.text, "html.parser")

        # EventsEye uses table rows or div cards for event listings
        rows = (
            soup.select("table.fair-list tr, tr.fair-row, tr[class*='fair']") or
            soup.select("div.fair-item, div.event-item, article.fair") or
            soup.select("table tr")[1:]  # skip header row
        )

        if not rows:
            # Fallback: look for any links that look like fair detail pages
            links = soup.select("a[href*='/fairs/f']")
            for link in links[:30]:
                name = link.get_text(strip=True)
                if not name or len(name) < 5:
                    continue
                href = link.get("href", "")
                full_link = href if href.startswith("http") else f"https://www.eventseye.com{href}"
                # Use surrounding context for date/location
                parent = link.parent
                parent_text = parent.get_text(" ", strip=True) if parent else ""
                start_date = _parse_date(parent_text)
                if not start_date:
                    continue
                city = country_override
                dh = self.make_hash(name, start_date, city)
                if dh in seen:
                    continue
                seen.add(dh)
                industry_tags = CAT_TAGS.get(industry_key, "trade show,conference")
                personas      = PERSONA_MAP.get(industry_key, "executives,trade buyers,professionals")
                events.append(EventCreate(
                    id=self.make_id(), source_platform="EventsEye", source_url=full_link,
                    dedup_hash=dh, name=name,
                    description=f"Global trade fair in {industry_key} sector. Source: EventsEye.",
                    start_date=start_date, end_date=start_date,
                    city=city, country=country_override,
                    category="trade show", industry_tags=industry_tags,
                    audience_personas=personas, est_attendees=2000,
                    ticket_price_usd=0.0, price_description="See website", registration_url=full_link,
                ))
            return events

        industry_tags = CAT_TAGS.get(industry_key, "trade show,conference")
        personas      = PERSONA_MAP.get(industry_key, "executives,trade buyers,professionals")

        for row in rows[:40]:
            try:
                cells = row.find_all(["td", "th"])
                if len(cells) < 2:
                    continue

                # Column order on EventsEye varies — try to infer
                name_el = (
                    row.select_one("td.fair-name a, td a.fair-link, .fair-name") or
                    row.select_one("a[href*='/fairs/']") or
                    cells[0].find("a")
                )
                if not name_el:
                    continue
                name = name_el.get_text(strip=True)
                if not name or len(name) < 4:
                    continue

                href = name_el.get("href", "")
                link = href if href.startswith("http") else f"https://www.eventseye.com{href}"

                # Try to find date cell
                date_text = ""
                for cell in cells:
                    txt = cell.get_text(strip=True)
                    if re.search(r"\d{4}", txt) and re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|\d{2}[-/]\d{2})", txt, re.I):
                        date_text = txt
                        break

                start_date = _parse_date(date_text)
                if not start_date:
                    continue

                # Location
                city    = country_override
                country = country_override
                for cell in cells:
                    txt = cell.get_text(strip=True)
                    if len(txt) > 2 and len(txt) < 50 and not re.search(r"\d{4}", txt):
                        # Looks like a location cell
                        parts = [p.strip() for p in txt.split(",")]
                        if parts:
                            city    = parts[0]
                            country = parts[-1] if len(parts) > 1 else country_override
                        break

                # Attendees
                att_text = ""
                for cell in cells:
                    txt = cell.get_text(strip=True)
                    if re.search(r"\d[\d,.]+\s*(k|visitors|exhibitors|attendees)?", txt, re.I):
                        att_text = txt
                        break
                attendees = _parse_attendees(att_text)

                dh = self.make_hash(name, start_date, city)
                if dh in seen:
                    continue
                seen.add(dh)

                events.append(EventCreate(
                    id=self.make_id(), source_platform="EventsEye", source_url=link,
                    dedup_hash=dh, name=name,
                    description=f"Global trade fair: {name}. Category: {industry_key}. Source: EventsEye.com.",
                    start_date=start_date, end_date=start_date,
                    city=city, country=country,
                    category="trade show", industry_tags=industry_tags,
                    audience_personas=personas, est_attendees=attendees,
                    ticket_price_usd=0.0, price_description="See website", registration_url=link,
                ))
            except Exception as e:
                logger.debug(f"EventsEye row parse: {e}")

        return events

    async def fetch(self) -> List[EventCreate]:
        all_events: List[EventCreate] = []
        seen_hashes: set = set()

        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:

            # ── Industry category pages ────────────────────────────
            for industry_key, url in CATEGORY_PAGES:
                evs = await self._scrape_page(client, url, industry_key)
                for ev in evs:
                    if ev.dedup_hash not in seen_hashes:
                        seen_hashes.add(ev.dedup_hash)
                        all_events.append(ev)
                logger.debug(f"EventsEye [{industry_key}]: {len(evs)} events parsed.")

            # ── Country pages for regional depth ──────────────────
            for country, url in COUNTRY_PAGES:
                evs = await self._scrape_page(client, url, "general", country_override=country)
                for ev in evs:
                    if ev.dedup_hash not in seen_hashes:
                        seen_hashes.add(ev.dedup_hash)
                        all_events.append(ev)
                logger.debug(f"EventsEye [{country}]: {len(evs)} events parsed.")

        logger.info(f"EventsEye total: {len(all_events)} unique events.")
        return all_events
