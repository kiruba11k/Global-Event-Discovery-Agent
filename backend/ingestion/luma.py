"""
Luma API — free tier, rate-limited
Register: lu.ma/developers
Strong source for tech conferences and startup events 2025-2026
"""
import httpx
from typing import List
from models.event import EventCreate
from ingestion.base_connector import BaseConnector
from config import get_settings
from loguru import logger

settings = get_settings()

BASE = "https://api.lu.ma/public/v1"

QUERY_TERMS = [
    "ai", "tech", "saas", "fintech", "data", "cloud",
    "startup", "product", "devops", "web3",
]


class LumaConnector(BaseConnector):
    name = "Luma"

    async def fetch(self) -> List[EventCreate]:
        if not settings.luma_api_key:
            logger.warning("Luma: no API key — skipping.")
            return []

        events: List[EventCreate] = []
        seen = set()
        headers = {"x-luma-api-key": settings.luma_api_key}

        async with httpx.AsyncClient(headers=headers, timeout=12) as client:
            for term in QUERY_TERMS[:6]:
                try:
                    r = await client.get(
                        f"{BASE}/event/list",
                        params={"query": term, "pagination_limit": 50},
                    )
                    r.raise_for_status()
                    entries = r.json().get("entries", [])
                except Exception as e:
                    logger.debug(f"Luma {term}: {e}")
                    continue

                for item in entries:
                    ev = item.get("event") or item
                    name = self.safe_str(ev.get("name", ""))
                    start_at = ev.get("start_at", "")
                    start_date = start_at[:10] if start_at else ""
                    if not start_date or not name:
                        continue

                    geo = ev.get("geo_address_info") or {}
                    city = geo.get("city", "")
                    country = geo.get("country", "")

                    dh = self.make_hash(name, start_date, city)
                    if dh in seen:
                        continue
                    seen.add(dh)

                    ticket_info = ev.get("ticket_info") or {}
                    is_free = ticket_info.get("is_free", True)
                    price_desc = "Free" if is_free else ticket_info.get("price_str", "See website")

                    events.append(EventCreate(
                        id=self.make_id(),
                        source_platform="Luma",
                        source_url=f"https://lu.ma/{ev.get('url', '')}",
                        dedup_hash=dh,
                        name=name,
                        description=self.safe_str(ev.get("description", ""))[:800],
                        start_date=start_date,
                        end_date=ev.get("end_at", start_at)[:10] if ev.get("end_at") else start_date,
                        venue_name=geo.get("full_address", ""),
                        city=city,
                        country=country,
                        is_virtual=ev.get("kind", "") == "virtual",
                        category="tech",
                        industry_tags=f"{term},tech,startup",
                        audience_personas="founders,developers,investors,product managers",
                        est_attendees=self.safe_int(ev.get("guest_count", 0)),
                        ticket_price_usd=0.0 if is_free else 0.0,
                        price_description=price_desc,
                        registration_url=f"https://lu.ma/{ev.get('url', '')}",
                    ))

        logger.info(f"Luma: {len(events)} events collected.")
        return events
