"""
Eventbrite API — free tier: 2,000 req/hr
Register: eventbrite.com/platform/api

The connector intentionally covers a broad industry x geography matrix so the
agent can surface business events globally instead of only a few tech hubs.
"""
import httpx
from typing import List
from models.event import EventCreate
from ingestion.base_connector import BaseConnector
from config import get_settings
from loguru import logger

settings = get_settings()

# Broad B2B/MICE discovery terms spanning major event-producing industries.
SEARCH_QUERIES = [
    "technology conference", "AI summit", "cybersecurity conference",
    "cloud computing conference", "data analytics conference",
    "enterprise software conference", "startup summit", "fintech conference",
    "banking finance conference", "insurance conference", "healthcare conference",
    "medical pharma conference", "biotech conference", "manufacturing expo",
    "industrial engineering expo", "energy conference", "renewable energy expo",
    "oil gas conference", "logistics expo", "supply chain conference",
    "retail ecommerce expo", "marketing conference", "media entertainment conference",
    "education conference", "real estate conference", "construction expo",
    "food beverage trade show", "hospitality conference", "travel tourism expo",
    "agriculture conference", "automotive expo", "aerospace defense conference",
    "mining conference", "legal conference", "HR conference", "MICE conference",
]

# ISO 3166-1 alpha-2 country codes distributed across North America, LATAM,
# Europe, Middle East, Africa, South Asia, Southeast Asia, East Asia, and Oceania.
COUNTRIES = [
    "US", "CA", "MX", "BR", "AR", "CL", "CO", "GB", "IE", "FR", "DE", "NL",
    "BE", "ES", "IT", "CH", "SE", "NO", "DK", "FI", "PL", "AE", "SA", "QA",
    "ZA", "EG", "KE", "NG", "IN", "PK", "BD", "LK", "SG", "MY", "ID", "TH",
    "VN", "PH", "JP", "KR", "CN", "HK", "TW", "AU", "NZ",
]


class EventbriteConnector(BaseConnector):
    name = "Eventbrite"
    base_url = "https://www.eventbriteapi.com/v3/events/search/"

    async def fetch(self) -> List[EventCreate]:
        if not settings.eventbrite_token:
            logger.warning("Eventbrite: no token set — skipping.")
            return []

        events: List[EventCreate] = []
        headers = {"Authorization": f"Bearer {settings.eventbrite_token}"}
        seen = set()

        async with httpx.AsyncClient(headers=headers, timeout=12) as client:
            for query in SEARCH_QUERIES:
                for country in COUNTRIES:
                    params = {
                        "q": query,
                        "location.country": country,
                        "expand": "venue,organizer,ticket_availability,category,subcategory",
                        "page_size": 50,
                        "status": "live",
                        "sort_by": "date",
                    }
                    try:
                        r = await client.get(self.base_url, params=params)
                        r.raise_for_status()
                        data = r.json()
                    except Exception as e:
                        logger.debug(f"Eventbrite {query}/{country}: {e}")
                        continue

                    for e in data.get("events", []):
                        start = e.get("start", {}).get("local", "")[:10]
                        if not start:
                            continue

                        venue = e.get("venue") or {}
                        addr = venue.get("address") or {}
                        city = addr.get("city", "")
                        country_name = addr.get("country", country)
                        name = self.safe_str(e.get("name", {}).get("text", ""))
                        if not name:
                            continue

                        dh = self.make_hash(name, start, city)
                        if dh in seen:
                            continue
                        seen.add(dh)

                        desc = e.get("description", {}).get("text", "") or ""
                        summary = e.get("summary", "") or ""
                        ticket = e.get("ticket_availability") or {}
                        min_price = ticket.get("minimum_ticket_price", {})
                        price_val = float(min_price.get("major_value", 0)) if min_price else 0.0
                        is_free = e.get("is_free", False)
                        price_desc = "Free" if is_free else (f"From ${price_val:.0f}" if price_val else "See website")
                        capacity = self.safe_int(e.get("capacity", 0))
                        category = (e.get("category") or {}).get("short_name") or query.split()[0].lower()
                        subcategory = (e.get("subcategory") or {}).get("short_name") or ""
                        tags = ",".join(filter(None, [query.lower(), category.lower(), subcategory.lower()]))

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
                            category=category,
                            industry_tags=tags,
                            audience_personas="business professionals,executives,managers,founders,industry buyers",
                            est_attendees=capacity,
                            ticket_price_usd=price_val,
                            price_description=price_desc,
                            registration_url=e.get("url", ""),
                        ))

        logger.info(f"Eventbrite: {len(events)} events collected.")
        return events
