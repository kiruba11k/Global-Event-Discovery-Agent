"""
Meetup GraphQL API — free, no key required for public events
Endpoint: api.meetup.com/gql
"""
import httpx
from typing import List
from models.event import EventCreate
from ingestion.base_connector import BaseConnector
from loguru import logger

GQL_URL = "https://api.meetup.com/gql"

TOPICS = [
    "tech", "artificial-intelligence", "data-science", "cloud-computing",
    "fintech", "startup", "entrepreneurship", "blockchain",
    "machine-learning", "devops", "product-management",
]

CITIES = [
    ("Singapore", "SG"),
    ("Mumbai", "IN"),
    ("Bangalore", "IN"),
    ("New York", "US"),
    ("London", "GB"),
    ("Sydney", "AU"),
    ("Dubai", "AE"),
    ("Berlin", "DE"),
    ("Kuala Lumpur", "MY"),
]

QUERY = """
query($query: String!, $lat: Float!, $lon: Float!) {
  keywordSearch(
    filter: { query: $query, lat: $lat, lon: $lon, radius: 100 }
    input: { first: 30 }
  ) {
    edges {
      node {
        result {
          ... on Event {
            id
            title
            dateTime
            endTime
            description
            eventUrl
            going
            isOnline
            venue {
              name
              address
              city
              country
            }
            group {
              name
              topics { name }
            }
          }
        }
      }
    }
  }
}
"""

CITY_COORDS = {
    "Singapore":     (1.3521, 103.8198),
    "Mumbai":        (19.0760, 72.8777),
    "Bangalore":     (12.9716, 77.5946),
    "New York":      (40.7128, -74.0060),
    "London":        (51.5074, -0.1278),
    "Sydney":        (-33.8688, 151.2093),
    "Dubai":         (25.2048, 55.2708),
    "Berlin":        (52.5200, 13.4050),
    "Kuala Lumpur":  (3.1390, 101.6869),
}


class MeetupConnector(BaseConnector):
    name = "Meetup"

    async def fetch(self) -> List[EventCreate]:
        events: List[EventCreate] = []
        seen = set()

        async with httpx.AsyncClient(timeout=15) as client:
            for topic in TOPICS[:5]:
                for city, country_code in CITIES[:5]:
                    lat, lon = CITY_COORDS.get(city, (1.35, 103.82))
                    payload = {"query": QUERY, "variables": {"query": topic, "lat": lat, "lon": lon}}
                    try:
                        r = await client.post(GQL_URL, json=payload)
                        r.raise_for_status()
                        data = r.json()
                    except Exception as e:
                        logger.debug(f"Meetup {topic}/{city}: {e}")
                        continue

                    edges = data.get("data", {}).get("keywordSearch", {}).get("edges", [])
                    for edge in edges:
                        node = edge.get("node", {}).get("result", {})
                        if not node or "title" not in node:
                            continue

                        name = self.safe_str(node.get("title", ""))
                        dt = node.get("dateTime", "")
                        start_date = dt[:10] if dt else ""
                        if not start_date or not name:
                            continue

                        venue = node.get("venue") or {}
                        event_city = venue.get("city", city)
                        event_country = venue.get("country", country_code)

                        dh = self.make_hash(name, start_date, event_city)
                        if dh in seen:
                            continue
                        seen.add(dh)

                        group = node.get("group") or {}
                        topics_raw = [t.get("name", "") for t in group.get("topics", [])]
                        industry_tags = ",".join(topics_raw[:5]).lower()

                        going = self.safe_int(node.get("going", 0))
                        is_online = node.get("isOnline", False)

                        events.append(EventCreate(
                            id=self.make_id(),
                            source_platform="Meetup",
                            source_url=node.get("eventUrl", ""),
                            dedup_hash=dh,
                            name=name,
                            description=self.safe_str(node.get("description", ""))[:800],
                            start_date=start_date,
                            end_date=node.get("endTime", dt)[:10] if node.get("endTime") else start_date,
                            venue_name=venue.get("name", ""),
                            address=venue.get("address", ""),
                            city=event_city,
                            country=event_country,
                            is_virtual=is_online,
                            category=topic,
                            industry_tags=industry_tags or topic,
                            audience_personas="developers,tech professionals,startup founders",
                            est_attendees=going,
                            ticket_price_usd=0.0,
                            price_description="Free (Meetup)",
                            registration_url=node.get("eventUrl", ""),
                        ))

        logger.info(f"Meetup: {len(events)} events collected.")
        return events
