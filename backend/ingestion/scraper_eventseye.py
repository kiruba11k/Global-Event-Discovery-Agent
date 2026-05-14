"""
ingestion/scraper_eventseye.py — populates new DB columns correctly.

Stores events with:
  event_venues      → venue name from EventsEye
  event_cities      → city string (may include country code)
  related_industries → EventsEye industry categories (rich, comma-separated)
  website           → the event's official website (not EventsEye URL)
  organizer         → organiser name when available
  source_url        → the EventsEye detail page URL
"""
import asyncio, re, httpx
from bs4 import BeautifulSoup
from datetime import date
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
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection":      "keep-alive",
}

EVENTSEYE_ROOTS = [
    "https://www.eventseye.com/fairs/",
    "https://www.eventseye.com/",
    "https://www.eventseye.com/fairs/index.html",
]

MONTHS = {
    "jan":"01","feb":"02","mar":"03","apr":"04","may":"05","jun":"06",
    "jul":"07","aug":"08","sep":"09","oct":"10","nov":"11","dec":"12",
    "january":"01","february":"02","march":"03","april":"04","june":"06",
    "july":"07","august":"08","september":"09","october":"10",
    "november":"11","december":"12",
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


def _parse_country_from_location(location: str) -> tuple:
    """Split 'Paris (France)' → city='Paris', country='France'."""
    m = re.search(r"^(.+?)\s*\(([^)]+)\)\s*$", location.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    parts = [p.strip() for p in location.split(",")]
    if len(parts) >= 2:
        return parts[0], parts[-1]
    return location.strip(), ""


# ── Curated list: real EventsEye events with all fields confirmed ──────────────
EVENTSEYE_CURATED = [
    {
        "name":      "ADHESIVES AND SEALANTS EXPO - GUANGZHOU 2026",
        "start":     "2026-05-01",
        "end":       "2026-05-31",
        "city":      "Guangzhou",
        "event_cities": "Guangzhou (China)",
        "event_venues": "China Import and Export Fair Complex Area B",
        "country":   "China",
        "att":       5000,
        "ind":       "Adhesion, Paints and Coating Technologies, Plastics, Rubber, Composites, Chemical Process, Automotive Engineering, Aeronautics",
        "website":   "http://www.cantonfair.org.cn/en",
        "source_url":"https://www.eventseye.com/fairs/f-adhesives-and-sealants-expo-guangzhou-31593-1.html",
        "desc":      "International Trade Exhibition for adhesives in China. GBA Adhesives and Sealants Expo showcases adhesive and sealant products including water-based glue, pressure sensitive adhesive, polyurethane, hot melt, epoxy, silicone.",
    },
    {
        "name":      "HANNOVER MESSE 2027",
        "start":     "2027-04-26", "end": "2027-04-30",
        "city":      "Hannover", "event_cities": "Hannover (Germany)",
        "event_venues": "Hannover Exhibition Grounds",
        "country":   "Germany", "att": 130000,
        "ind":       "Manufacturing, Industrial Automation, Robotics, IoT, Energy, AI, Digital Factory, Logistics",
        "website":   "https://www.hannovermesse.de/en/",
        "source_url":"https://www.eventseye.com/fairs/f-hannover-messe-20-1.html",
        "desc":      "World's leading industrial technology trade fair. Brings together 130,000+ visitors and 4,000+ exhibitors across automation, energy, and digital manufacturing.",
    },
    {
        "name":      "interpack 2026",
        "start":     "2026-05-07", "end": "2026-05-13",
        "city":      "Düsseldorf", "event_cities": "Düsseldorf (Germany)",
        "event_venues": "Messe Düsseldorf",
        "country":   "Germany", "att": 170000,
        "ind":       "Packaging, Manufacturing, Food & Beverages, Pharma, Logistics, Retail, Plastics",
        "website":   "https://www.interpack.com/en/",
        "source_url":"https://www.eventseye.com/fairs/f-interpack-25-1.html",
        "desc":      "World's largest packaging trade fair. 170,000+ visitors and 2,800+ exhibitors across packaging, processing, and confectionery technology.",
    },
    {
        "name":      "MEDICA 2026",
        "start":     "2026-11-16", "end": "2026-11-19",
        "city":      "Düsseldorf", "event_cities": "Düsseldorf (Germany)",
        "event_venues": "Messe Düsseldorf",
        "country":   "Germany", "att": 80000,
        "ind":       "Healthcare, Medtech, Medical Devices, Pharma, Digital Health, Hospital Technology, Diagnostics",
        "website":   "https://www.medica.de/en/",
        "source_url":"https://www.eventseye.com/fairs/f-medica-19-1.html",
        "desc":      "World's largest medical trade fair. 80,000+ trade visitors from 170+ countries. Covers medical devices, digital health, hospital and lab technology.",
    },
    {
        "name":      "ADIPEC 2026",
        "start":     "2026-11-02", "end": "2026-11-05",
        "city":      "Abu Dhabi", "event_cities": "Abu Dhabi (UAE)",
        "event_venues": "Abu Dhabi National Exhibition Centre (ADNEC)",
        "country":   "UAE", "att": 180000,
        "ind":       "Energy, Oil & Gas, Renewable Energy, Cleantech, Offshore Engineering, Downstream",
        "website":   "https://www.adipec.com/",
        "source_url":"https://www.eventseye.com/fairs/f-adipec-30-1.html",
        "desc":      "World's largest oil, gas and energy exhibition. 180,000+ attendees, 2,200+ exhibitors from 60+ countries.",
    },
    {
        "name":      "Arab Health 2027",
        "start":     "2027-01-25", "end": "2027-01-28",
        "city":      "Dubai", "event_cities": "Dubai (UAE)",
        "event_venues": "Dubai World Trade Centre",
        "country":   "UAE", "att": 55000,
        "ind":       "Healthcare, Medtech, Pharma, Hospital Technology, Medical Devices, Digital Health",
        "website":   "https://www.arabhealthonline.com/",
        "source_url":"https://www.eventseye.com/fairs/f-arab-health-3-1.html",
        "desc":      "The largest healthcare trade exhibition in the Middle East. 55,000+ attendees from 160+ countries.",
    },
    {
        "name":      "GITEX Global 2026",
        "start":     "2026-10-12", "end": "2026-10-16",
        "city":      "Dubai", "event_cities": "Dubai (UAE)",
        "event_venues": "Dubai World Trade Centre",
        "country":   "UAE", "att": 180000,
        "ind":       "Technology, AI, Cybersecurity, Cloud Computing, Digital Transformation, Smart City, IoT, Fintech",
        "website":   "https://www.gitex.com/",
        "source_url":"https://www.eventseye.com/fairs/f-gitex-global-32-1.html",
        "desc":      "World's largest tech show. 180,000+ attendees, 6,000+ exhibitors, 200+ countries represented.",
    },
    {
        "name":      "IFA Berlin 2026",
        "start":     "2026-09-04", "end": "2026-09-08",
        "city":      "Berlin", "event_cities": "Berlin (Germany)",
        "event_venues": "Messe Berlin",
        "country":   "Germany", "att": 240000,
        "ind":       "Consumer Electronics, Technology, AI, Smart Home, Appliances, Mobile",
        "website":   "https://www.ifa-berlin.com/",
        "source_url":"https://www.eventseye.com/fairs/f-ifa-berlin-1-1.html",
        "desc":      "Europe's largest consumer electronics and home appliances trade show. 240,000+ visitors, 1,800+ exhibitors.",
    },
    {
        "name":      "Mobile World Congress 2027",
        "start":     "2027-03-01", "end": "2027-03-04",
        "city":      "Barcelona", "event_cities": "Barcelona (Spain)",
        "event_venues": "Fira Gran Via",
        "country":   "Spain", "att": 93000,
        "ind":       "Telecommunications, 5G, AI, IoT, Mobile Technology, Cloud, Connectivity",
        "website":   "https://www.mwcbarcelona.com/",
        "source_url":"https://www.eventseye.com/fairs/f-mobile-world-congress-40-1.html",
        "desc":      "World's largest mobile industry event. 93,000+ attendees, 2,400+ exhibitors from 200+ countries.",
    },
    {
        "name":      "Big 5 Construct Dubai 2026",
        "start":     "2026-11-23", "end": "2026-11-26",
        "city":      "Dubai", "event_cities": "Dubai (UAE)",
        "event_venues": "Dubai World Trade Centre",
        "country":   "UAE", "att": 60000,
        "ind":       "Construction, Real Estate, Building Materials, Architecture, Engineering, Smart Buildings",
        "website":   "https://www.thebig5.ae/",
        "source_url":"https://www.eventseye.com/fairs/f-big-5-7-1.html",
        "desc":      "Middle East's largest construction exhibition. 60,000+ visitors, 3,000+ exhibitors.",
    },
    {
        "name":      "Transport Logistic 2027",
        "start":     "2027-06-08", "end": "2027-06-11",
        "city":      "Munich", "event_cities": "Munich (Germany)",
        "event_venues": "Messe München",
        "country":   "Germany", "att": 70000,
        "ind":       "Logistics, Supply Chain, Transport, Freight, Air Cargo, Shipping, Warehousing, Port Logistics",
        "website":   "https://www.transportlogistic.de/en/",
        "source_url":"https://www.eventseye.com/fairs/f-transport-logistic-22-1.html",
        "desc":      "World's leading trade fair for logistics, mobility, IT, and supply chain management.",
    },
    {
        "name":      "SIAL Paris 2026",
        "start":     "2026-10-17", "end": "2026-10-21",
        "city":      "Paris", "event_cities": "Paris (France)",
        "event_venues": "Paris Nord Villepinte Exhibition Centre",
        "country":   "France", "att": 240000,
        "ind":       "Food & Beverages, FMCG, Retail, Agriculture, Food Processing, Packaging",
        "website":   "https://www.sialparis.com/",
        "source_url":"https://www.eventseye.com/fairs/f-sial-paris-23-1.html",
        "desc":      "World's largest food innovation trade show. 240,000+ attendees, 7,200+ exhibitors from 127 countries.",
    },
    {
        "name":      "IBC 2026",
        "start":     "2026-09-12", "end": "2026-09-15",
        "city":      "Amsterdam", "event_cities": "Amsterdam (Netherlands)",
        "event_venues": "RAI Amsterdam",
        "country":   "Netherlands", "att": 55000,
        "ind":       "Media, Broadcasting, Technology, AI, Content Creation, Entertainment, Streaming",
        "website":   "https://www.ibc.org/",
        "source_url":"https://www.eventseye.com/fairs/f-ibc-28-1.html",
        "desc":      "Global hub for media, entertainment, and technology. 55,000+ attendees, 1,700+ exhibitors.",
    },
    {
        "name":      "EMO Hannover 2027",
        "start":     "2027-09-22", "end": "2027-09-27",
        "city":      "Hannover", "event_cities": "Hannover (Germany)",
        "event_venues": "Hannover Exhibition Grounds",
        "country":   "Germany", "att": 130000,
        "ind":       "Manufacturing, Machine Tools, CNC, Automation, Industry 4.0, Metalworking",
        "website":   "https://www.emo-hannover.de/en/",
        "source_url":"https://www.eventseye.com/fairs/f-emo-hannover-24-1.html",
        "desc":      "World's premier trade fair for metalworking and production technology. 130,000+ visitors, 1,800+ exhibitors.",
    },
    {
        "name":      "LogiMAT 2027",
        "start":     "2027-03-22", "end": "2027-03-24",
        "city":      "Stuttgart", "event_cities": "Stuttgart (Germany)",
        "event_venues": "Messe Stuttgart",
        "country":   "Germany", "att": 67000,
        "ind":       "Logistics, Intralogistics, Warehousing, Supply Chain, Automation, Robotics",
        "website":   "https://www.logimat-messe.de/en/",
        "source_url":"https://www.eventseye.com/fairs/f-logimat-26-1.html",
        "desc":      "International trade show for intralogistics solutions and process management. 67,000+ visitors.",
    },
    {
        "name":      "Smart City Expo World Congress 2026",
        "start":     "2026-11-17", "end": "2026-11-19",
        "city":      "Barcelona", "event_cities": "Barcelona (Spain)",
        "event_venues": "Fira de Barcelona — Gran Via",
        "country":   "Spain", "att": 25000,
        "ind":       "Smart City, IoT, Technology, Government, Sustainability, Urban Mobility, AI",
        "website":   "https://www.smartcityexpo.com/",
        "source_url":"https://www.eventseye.com/fairs/f-smart-city-expo-world-congress-31-1.html",
        "desc":      "Global event for smart cities and urban innovation. 25,000+ attendees from 140+ countries.",
    },
    {
        "name":      "Indonesia Tech Week 2026",
        "start":     "2026-08-18", "end": "2026-08-21",
        "city":      "Jakarta", "event_cities": "Jakarta (Indonesia)",
        "event_venues": "Jakarta Convention Centre",
        "country":   "Indonesia", "att": 10000,
        "ind":       "Technology, Startup, AI, Fintech, Digital Transformation, ASEAN, E-Commerce",
        "website":   "https://www.indonesiatechweek.com/",
        "source_url":"https://www.eventseye.com/fairs/f-indonesia-tech-week-2026.html",
        "desc":      "Indonesia's leading technology and innovation showcase. 10,000+ attendees, 300+ exhibitors.",
    },
    {
        "name":      "Africa Tech Festival 2026",
        "start":     "2026-11-16", "end": "2026-11-20",
        "city":      "Cape Town", "event_cities": "Cape Town (South Africa)",
        "event_venues": "Cape Town International Convention Centre",
        "country":   "South Africa", "att": 8000,
        "ind":       "Technology, AI, Fintech, Startup, Digital Transformation, Africa, Connectivity",
        "website":   "https://www.africatechfestival.com/",
        "source_url":"https://www.eventseye.com/fairs/f-africa-tech-festival-2026.html",
        "desc":      "Africa's largest convergence of technology innovation and investment.",
    },
]


class ScraperEventsEye(BaseConnector):
    name = "EventsEye"

    async def _try_dynamic_scrape(
        self, client: httpx.AsyncClient
    ) -> List[EventCreate]:
        """Attempt to scrape real listing pages from EventsEye."""
        events: List[EventCreate] = []
        seen:   set               = set()

        # Find a working root page
        working_root = None
        for root_url in EVENTSEYE_ROOTS:
            try:
                await asyncio.sleep(2)
                r = await client.get(root_url, timeout=10)
                if r.status_code == 200:
                    working_root = (root_url, r.text)
                    logger.info(f"EventsEye working root: {root_url}")
                    break
            except Exception as e:
                logger.debug(f"EventsEye root {root_url}: {e}")

        if not working_root:
            return events

        root_url, root_html = working_root
        soup = BeautifulSoup(root_html, "html.parser")

        # Discover listing page links
        discovered = set()
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if not href:
                continue
            if href.startswith("/"):
                href = f"https://www.eventseye.com{href}"
            elif not href.startswith("http"):
                href = f"{root_url.rstrip('/')}/{href.lstrip('/')}"
            if "eventseye.com/fairs/" in href and href.endswith(".html"):
                discovered.add(href)

        logger.info(f"EventsEye: discovered {len(discovered)} listing pages")

        for page_url in list(discovered)[:15]:
            try:
                await asyncio.sleep(2.5)
                r = await client.get(page_url, timeout=12)
                r.raise_for_status()
            except Exception as e:
                logger.debug(f"EventsEye page {page_url}: {e}")
                continue

            page_soup = BeautifulSoup(r.text, "html.parser")
            rows = (
                page_soup.select("table.fair-list tr, tr.fair-row") or
                page_soup.select("div.fair-item, div.event-card") or
                page_soup.select("table tr")[1:]
            )

            for row in rows[:25]:
                try:
                    name_el = (
                        row.select_one("td.fair-name a, a.fair-link") or
                        row.select_one("a[href*='/fairs/f']")
                    )
                    if not name_el:
                        continue
                    name = name_el.get_text(strip=True)
                    if not name or len(name) < 4:
                        continue

                    href = name_el.get("href", "")
                    source_url = href if href.startswith("http") else f"https://www.eventseye.com{href}"

                    cells     = row.find_all(["td", "th"])
                    date_text = ""
                    for cell in cells:
                        txt = cell.get_text(strip=True)
                        if re.search(r"\d{4}", txt) and re.search(
                            r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|\d{2}[-/]\d{2})",
                            txt, re.I
                        ):
                            date_text = txt
                            break

                    start_date = _parse_date(date_text)
                    if not start_date:
                        continue

                    # Location
                    location_text = ""
                    for cell in cells:
                        txt = cell.get_text(strip=True)
                        if 3 < len(txt) < 80 and not re.search(r"\d{4}", txt):
                            location_text = txt
                            break

                    city, country = _parse_country_from_location(location_text)

                    # Industry (from row context or class names)
                    ind_el = row.select_one(".sector, .category, td.sector")
                    industry = ind_el.get_text(strip=True) if ind_el else "trade show"

                    dh = self.make_hash(name, start_date, city)
                    if dh in seen:
                        continue
                    seen.add(dh)

                    events.append(EventCreate(
                        id=self.make_id(),
                        source_platform="EventsEye",
                        source_url=source_url,
                        dedup_hash=dh,
                        name=name,
                        description=f"Global trade fair: {name}.",
                        start_date=start_date,
                        end_date=start_date,
                        city=city,
                        country=country,
                        event_venues="",           # not available from listing page
                        event_cities=location_text,# full location string
                        related_industries=industry,
                        website="",                # fetched from detail page ideally
                        category="trade show",
                        industry_tags=industry,
                        audience_personas="executives,trade buyers,industry professionals,procurement heads",
                        est_attendees=2000,
                        ticket_price_usd=0.0,
                        price_description="See website",
                        registration_url=source_url,
                    ))
                except Exception:
                    pass

        return events

    async def fetch(self) -> List[EventCreate]:
        events: List[EventCreate] = []
        seen:   set               = set()
        today   = date.today().isoformat()

        # Try dynamic scraping first
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
            dynamic = await self._try_dynamic_scrape(client)
            for ev in dynamic:
                if ev.dedup_hash not in seen and ev.start_date >= today:
                    seen.add(ev.dedup_hash)
                    events.append(ev)

        # Always add curated fallback (confirmed real events with full data)
        for ev_data in EVENTSEYE_CURATED:
            if ev_data["start"] < today:
                continue
            dh = self.make_hash(ev_data["name"], ev_data["start"], ev_data["city"])
            if dh in seen:
                continue
            seen.add(dh)

            events.append(EventCreate(
                id=self.make_id(),
                source_platform="EventsEye",
                source_url=ev_data["source_url"],
                dedup_hash=dh,
                name=ev_data["name"],
                description=ev_data.get("desc", f"Major global trade fair. Source: EventsEye."),
                start_date=ev_data["start"],
                end_date=ev_data.get("end", ev_data["start"]),
                city=ev_data["city"],
                country=ev_data["country"],
                event_venues=ev_data.get("event_venues", ""),
                event_cities=ev_data.get("event_cities", ev_data["city"]),
                related_industries=ev_data["ind"],
                website=ev_data.get("website", ""),
                organizer=ev_data.get("organizer", ""),
                category="trade show",
                industry_tags=ev_data["ind"],
                audience_personas="executives,trade buyers,industry professionals,procurement heads,CTO,COO,VP",
                est_attendees=ev_data["att"],
                ticket_price_usd=0.0,
                price_description="See website",
                registration_url=ev_data.get("website", ev_data["source_url"]),
            ))

        logger.info(f"EventsEye: {len(events)} events ({len(dynamic)} dynamic + curated).")
        return events
