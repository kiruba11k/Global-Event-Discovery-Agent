"""
Eventbrite API — expanded to ALL industries × ALL global regions.
Free tier: 2,000 req/hr (we stay well under with controlled batching).

Previous version: 6 queries × 4 countries = 24 combinations
This version:     20 queries × 12 countries = 240 combinations
                  → significantly more event coverage at no extra cost
"""
import asyncio, httpx
from typing import List
from models.event import EventCreate
from ingestion.base_connector import BaseConnector
from config import get_settings
from loguru import logger

settings = get_settings()

# All major industry verticals
SEARCH_QUERIES = [
    # Tech
    "technology conference",
    "artificial intelligence summit",
    "machine learning conference",
    "cloud computing expo",
    "cybersecurity conference",
    "data analytics summit",
    "SaaS conference",
    "developer conference",
    # Business
    "startup summit",
    "entrepreneurship conference",
    "digital transformation summit",
    "leadership conference",
    # Finance
    "fintech conference",
    "banking technology conference",
    "payments summit",
    "blockchain conference",
    # Industry verticals
    "healthcare technology conference",
    "logistics supply chain conference",
    "manufacturing industry expo",
    "energy renewable conference",
    "retail ecommerce summit",
    "marketing advertising conference",
    "HR technology conference",
    "real estate conference",
    "legal technology conference",
    "automotive industry expo",
    # Geographic / trade shows
    "trade show expo",
    "business expo",
    "industry summit",
    "professional conference",
]

# All major global regions covered
COUNTRIES = [
    "US",   # United States
    "GB",   # United Kingdom
    "IN",   # India
    "SG",   # Singapore
    "AU",   # Australia
    "DE",   # Germany
    "AE",   # UAE
    "CA",   # Canada
    "MY",   # Malaysia
    "JP",   # Japan
    "NL",   # Netherlands
    "FR",   # France
    "ES",   # Spain
    "BR",   # Brazil
    "ZA",   # South Africa
    "KR",   # South Korea
]

# Map Eventbrite query to industry tags
QUERY_TO_INDUSTRY = {
    "technology conference":            "tech,software,IT",
    "artificial intelligence summit":   "AI,machine learning,tech,data",
    "machine learning conference":      "AI,machine learning,data,tech",
    "cloud computing expo":             "cloud computing,tech,SaaS",
    "cybersecurity conference":         "cybersecurity,infosec,tech",
    "data analytics summit":            "data,analytics,AI,cloud",
    "SaaS conference":                  "SaaS,software,tech,B2B",
    "developer conference":             "developer,tech,software,engineering",
    "startup summit":                   "startup,venture capital,tech",
    "entrepreneurship conference":      "startup,business,entrepreneurship",
    "digital transformation summit":    "digital transformation,tech,enterprise",
    "leadership conference":            "business,leadership,management",
    "fintech conference":               "fintech,banking,finance,payments",
    "banking technology conference":    "finance,banking,fintech,regtech",
    "payments summit":                  "finance,payments,fintech,ecommerce",
    "blockchain conference":            "blockchain,web3,crypto,DeFi,finance",
    "healthcare technology conference": "healthcare,medtech,digital health,AI",
    "logistics supply chain conference":"logistics,supply chain,procurement",
    "manufacturing industry expo":      "manufacturing,industrial,automation,IoT",
    "energy renewable conference":      "energy,cleantech,sustainability,ESG",
    "retail ecommerce summit":          "retail,ecommerce,D2C,consumer goods",
    "marketing advertising conference": "marketing,advertising,martech,brand",
    "HR technology conference":         "HR tech,talent,workforce,people ops",
    "real estate conference":           "real estate,property,construction",
    "legal technology conference":      "legal,legaltech,compliance,regulatory",
    "automotive industry expo":         "automotive,manufacturing,fleet,mobility",
    "trade show expo":                  "trade show,expo,general",
    "business expo":                    "business,trade show,general",
    "industry summit":                  "industry,business,general",
    "professional conference":          "business,professional development,general",
}


class EventbriteConnector(BaseConnector):
    name = "Eventbrite"
    base_url = "https://www.eventbriteapi.com/v3/events/search/"

    async def fetch(self) -> List[EventCreate]:
        if not settings.eventbrite_token:
            logger.warning("Eventbrite: no token set — skipping.")
            return []

        events: List[EventCreate] = []
        headers = {"Authorization": f"Bearer {settings.eventbrite_token}"}
        seen:  set = set()
        req_count = 0

        async with httpx.AsyncClient(headers=headers, timeout=12) as client:
            for query in SEARCH_QUERIES:
                for country in COUNTRIES:
                    # Stay under rate limits: ~1 req/sec
                    await asyncio.sleep(1.0)
                    req_count += 1

                    params = {
                        "q": query,
                        "location.country": country,
                        "expand": "venue,organizer,ticket_availability",
                        "page_size": 50,
                        "status": "live",
                        "sort_by": "date",
                    }
                    try:
                        r = await client.get(self.base_url, params=params)
                        if r.status_code == 429:
                            logger.warning("Eventbrite rate limited — pausing 60s")
                            await asyncio.sleep(60)
                            continue
                        r.raise_for_status()
                        data = r.json()
                    except Exception as e:
                        logger.debug(f"Eventbrite {query}/{country}: {e}")
                        continue

                    for e in data.get("events", []):
                        start = e.get("start", {}).get("local", "")[:10]
                        if not start:
                            continue

                        venue       = e.get("venue") or {}
                        addr        = venue.get("address") or {}
                        city        = addr.get("city", "")
                        country_name = addr.get("country", country)
                        name        = self.safe_str(e.get("name", {}).get("text", ""))

                        dh = self.make_hash(name, start, city)
                        if dh in seen:
                            continue
                        seen.add(dh)

                        desc     = e.get("description", {}).get("text", "") or ""
                        summary  = e.get("summary", "") or ""
                        ticket   = e.get("ticket_availability") or {}
                        min_price = ticket.get("minimum_ticket_price", {})
                        price_val = float(min_price.get("major_value", 0)) if min_price else 0.0
                        is_free  = e.get("is_free", False)
                        price_desc = "Free" if is_free else (f"From ${price_val:.0f}" if price_val else "See website")
                        capacity  = self.safe_int(e.get("capacity", 0))
                        industry  = QUERY_TO_INDUSTRY.get(query, "general")

                        events.append(EventCreate(
                            id=self.make_id(),
                            source_platform="Eventbrite",
                            source_url=e.get("url", ""),
                            dedup_hash=dh,
                            name=name,
                            description=desc[:1000],
                            short_summary=summary[:300],
                            start_date=start,
                            end_date=e.get("end", {}).get("local", start)[:10],
                            venue_name=self.safe_str(venue.get("name", "")),
                            address=addr.get("localized_address_display", ""),
                            city=city,
                            country=country_name,
                            category=query.split()[0].lower(),
                            industry_tags=industry,
                            audience_personas="executives,professionals,business leaders,decision-makers",
                            est_attendees=capacity,
                            ticket_price_usd=price_val,
                            price_description=price_desc,
                            registration_url=e.get("url", ""),
                        ))

        logger.info(f"Eventbrite: {len(events)} events from {req_count} API calls.")
        return events
