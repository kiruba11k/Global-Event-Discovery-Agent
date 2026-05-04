"""
Ticketmaster Discovery API — free tier: 5,000 calls/day
Register: developer.ticketmaster.com
"""
import httpx
from typing import List
from models.event import EventCreate
from ingestion.base_connector import BaseConnector
from config import get_settings
from loguru import logger

settings = get_settings()

MARKETS = [
    ("Singapore",  "SG"),
    ("India",      "IN"),
    ("Malaysia",   "MY"),
    ("USA",        "US"),
    ("UK",         "GB"),
    ("Australia",  "AU"),
]


class TicketmasterConnector(BaseConnector):
    name = "Ticketmaster"
    base_url = "https://app.ticketmaster.com/discovery/v2/events.json"

    async def _fetch_page(self, client: httpx.AsyncClient, params: dict) -> list:
        params["apikey"] = settings.ticketmaster_key
        params["size"] = 50
        params["classificationName"] = "conference,business,technology,expo"
        try:
            r = await client.get(self.base_url, params=params, timeout=10)
            r.raise_for_status()
            data = r.json()
            return data.get("_embedded", {}).get("events", [])
        except Exception as e:
            logger.debug(f"Ticketmaster page error: {e}")
            return []

    async def fetch(self) -> List[EventCreate]:
        if not settings.ticketmaster_key:
            logger.warning("Ticketmaster: no API key set — skipping.")
            return []

        events: List[EventCreate] = []
        async with httpx.AsyncClient() as client:
            for country_name, country_code in MARKETS:
                raw = await self._fetch_page(client, {"countryCode": country_code})
                for e in raw:
                    dates = e.get("dates", {}).get("start", {})
                    start_date = dates.get("localDate", "")
                    if not start_date:
                        continue

                    venue_list = e.get("_embedded", {}).get("venues", [{}])
                    venue = venue_list[0] if venue_list else {}
                    city = venue.get("city", {}).get("name", country_name)
                    country = venue.get("country", {}).get("name", country_name)
                    address = venue.get("address", {}).get("line1", "")

                    classifications = e.get("classifications", [{}])
                    segment = classifications[0].get("segment", {}).get("name", "Business")
                    genre = classifications[0].get("genre", {}).get("name", "")
                    industry_tag = f"{segment},{genre}".strip(",").lower()

                    price_ranges = e.get("priceRanges", [])
                    price_min = price_ranges[0].get("min", 0.0) if price_ranges else 0.0
                    price_desc = f"From ${price_min:.0f}" if price_min else "See website"

                    name = self.safe_str(e.get("name", ""))
                    dh = self.make_hash(name, start_date, city)

                    events.append(EventCreate(
                        id=self.make_id(),
                        source_platform="Ticketmaster",
                        source_url=e.get("url", ""),
                        dedup_hash=dh,
                        name=name,
                        description=self.safe_str(e.get("info", "")),
                        short_summary=self.safe_str(e.get("pleaseNote", "")),
                        start_date=start_date,
                        end_date=dates.get("localDate", start_date),
                        venue_name=self.safe_str(venue.get("name", "")),
                        address=address,
                        city=city,
                        country=country,
                        category="conference",
                        industry_tags=industry_tag,
                        audience_personas="business professionals,executives",
                        ticket_price_usd=float(price_min),
                        price_description=price_desc,
                        registration_url=e.get("url", ""),
                    ))
        return events
