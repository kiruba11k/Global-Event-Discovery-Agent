"""
Eventbrite API — free tier: 2,000 req/hr
Register: eventbrite.com/platform/api
"""
import httpx
from typing import List
from models.event import EventCreate
from ingestion.base_connector import BaseConnector
from config import get_settings
from loguru import logger

settings = get_settings()

SEARCH_QUERIES = [
    "technology conference", "AI summit", "fintech conference",
    "healthcare conference", "logistics expo", "data conference",
    "cloud computing", "digital transformation", "startup summit",
    "enterprise software", "cybersecurity conference", "ecommerce expo",
]
COUNTRIES = ["SG", "IN", "MY", "US", "GB", "AU", "AE", "DE"]


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
            for query in SEARCH_QUERIES[:6]:
                for country in COUNTRIES[:4]:
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
                            industry_tags=query.lower(),
                            audience_personas="business professionals,executives,managers",
                            est_attendees=capacity,
                            ticket_price_usd=price_val,
                            price_description=price_desc,
                            registration_url=e.get("url", ""),
                        ))

        logger.info(f"Eventbrite: {len(events)} events collected.")
        return events
