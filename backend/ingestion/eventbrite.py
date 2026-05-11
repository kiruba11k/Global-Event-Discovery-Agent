"""
Eventbrite API — FIXED version.

Root cause of 404s: `location.country=KR` (and many other codes) is not
supported by the Eventbrite search endpoint. It silently returns 404.

Fix: switch to lat/lon + radius search, which works for every city.
"""
import asyncio
from datetime import datetime, timezone
from typing import List
from models.event import EventCreate
from ingestion.base_connector import BaseConnector
from config import get_settings
from loguru import logger

settings = get_settings()

# 10 high-value industry search terms
SEARCH_QUERIES = [
    "technology conference",
    "artificial intelligence summit",
    "fintech conference",
    "healthcare conference",
    "startup summit",
    "cloud computing conference",
    "cybersecurity conference",
    "digital transformation summit",
    "data analytics conference",
    "SaaS conference",
    "logistics supply chain conference",
    "marketing conference",
    "HR technology conference",
    "ecommerce summit",
    "manufacturing expo",
]

# City coordinates — lat/lon search works reliably for all cities
CITY_COORDS = [
    ("Singapore",      1.3521,   103.8198, "Singapore"),
    ("Mumbai",        19.0760,    72.8777, "India"),
    ("Bangalore",     12.9716,    77.5946, "India"),
    ("New York",      40.7128,   -74.0060, "USA"),
    ("London",        51.5074,    -0.1278, "UK"),
    ("Sydney",       -33.8688,   151.2093, "Australia"),
    ("Dubai",         25.2048,    55.2708, "UAE"),
    ("Berlin",        52.5200,    13.4050, "Germany"),
    ("Toronto",       43.6532,   -79.3832, "Canada"),
    ("Amsterdam",     52.3676,     4.9041, "Netherlands"),
    ("Kuala Lumpur",   3.1390,   101.6869, "Malaysia"),
    ("Tokyo",         35.6762,   139.6503, "Japan"),
]

# Map queries to industry tags
QUERY_INDUSTRY = {
    "technology conference":            "tech,software,IT",
    "artificial intelligence summit":   "AI,machine learning,tech,data",
    "fintech conference":               "fintech,banking,finance,payments",
    "healthcare conference":            "healthcare,medtech,digital health",
    "startup summit":                   "startup,venture capital,tech",
    "cloud computing conference":       "cloud computing,tech,SaaS,AWS",
    "cybersecurity conference":         "cybersecurity,infosec,tech",
    "digital transformation summit":    "digital transformation,tech,enterprise",
    "data analytics conference":        "data,analytics,AI,business intelligence",
    "SaaS conference":                  "SaaS,software,B2B,tech",
    "logistics supply chain conference":"logistics,supply chain,procurement",
    "marketing conference":             "marketing,advertising,martech",
    "HR technology conference":         "HR tech,talent,workforce,people ops",
    "ecommerce summit":                 "ecommerce,retail,D2C,payments",
    "manufacturing expo":               "manufacturing,industrial,automation,IoT",
}


class EventbriteConnector(BaseConnector):
    name = "Eventbrite"
    BASE = "https://www.eventbriteapi.com/v3/events/search/"

    async def fetch(self) -> List[EventCreate]:
        if not settings.eventbrite_token:
            logger.warning("Eventbrite: no token — skipping.")
            return []

        import httpx
        from datetime import date

        today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        events: List[EventCreate] = []
        seen:   set               = set()
        req_ok  = 0
        req_err = 0

        headers = {"Authorization": f"Bearer {settings.eventbrite_token}"}

        endpoint_unavailable = False

        async with httpx.AsyncClient(headers=headers, timeout=15) as client:
            for query in SEARCH_QUERIES:
                if endpoint_unavailable:
                    break

                for city, lat, lon, country in CITY_COORDS:
                    await asyncio.sleep(1.2)  # stay under 2,000/hr rate limit

                    params = {
                        "q":                      query,
                        "location.latitude":      lat,
                        "location.longitude":     lon,
                        "location.within":        "50km",
                        "expand":                 "venue,ticket_availability",
                        "page_size":              50,
                        "status":                 "live",
                        "sort_by":                "date",
                        "start_date.range_start": today_iso,
                    }

                    try:
                        r = await client.get(self.BASE, params=params)
                        if r.status_code == 404:
                            endpoint_unavailable = True
                            logger.warning("Eventbrite endpoint returned 404; stopping Eventbrite fetch for this run.")
                            break
                        if r.status_code == 429:
                            logger.warning("Eventbrite rate limited — pausing 60s")
                            await asyncio.sleep(60)
                            continue
                        r.raise_for_status()
                        data = r.json()
                        req_ok += 1
                    except Exception as e:
                        if "404" in str(e):
                            endpoint_unavailable = True
                            logger.warning("Eventbrite endpoint appears unavailable (404); stopping Eventbrite fetch for this run.")
                            break
                        logger.debug(f"Eventbrite {query}/{city}: {e}")
                        req_err += 1
                        continue

                    for e in data.get("events", []):
                        start = e.get("start", {}).get("local", "")[:10]
                        if not start:
                            continue

                        venue  = e.get("venue") or {}
                        addr   = venue.get("address") or {}
                        ecity  = addr.get("city", city)
                        name   = self.safe_str(e.get("name", {}).get("text", ""))
                        if not name:
                            continue

                        dh = self.make_hash(name, start, ecity)
                        if dh in seen:
                            continue
                        seen.add(dh)

                        ticket    = e.get("ticket_availability") or {}
                        min_price = ticket.get("minimum_ticket_price", {})
                        price_val = float(min_price.get("major_value", 0)) if min_price else 0.0
                        is_free   = e.get("is_free", False)
                        price_desc = "Free" if is_free else (f"From ${price_val:.0f}" if price_val else "See website")
                        capacity   = self.safe_int(e.get("capacity", 0))
                        industry   = QUERY_INDUSTRY.get(query, "general")

                        events.append(EventCreate(
                            id=self.make_id(),
                            source_platform="Eventbrite",
                            source_url=e.get("url", ""),
                            dedup_hash=dh,
                            name=name,
                            description=(e.get("description", {}).get("text", "") or "")[:1000],
                            short_summary=(e.get("summary", "") or "")[:300],
                            start_date=start,
                            end_date=e.get("end", {}).get("local", start)[:10],
                            venue_name=self.safe_str(venue.get("name", "")),
                            address=addr.get("localized_address_display", ""),
                            city=ecity,
                            country=addr.get("country", country),
                            category=query.split()[0].lower(),
                            industry_tags=industry,
                            audience_personas="executives,professionals,business leaders",
                            est_attendees=capacity,
                            ticket_price_usd=price_val,
                            price_description=price_desc,
                            registration_url=e.get("url", ""),
                        ))

        logger.info(
            f"Eventbrite: {len(events)} events "
            f"({req_ok} OK / {req_err} errors from {req_ok+req_err} requests)"
        )
        return events
