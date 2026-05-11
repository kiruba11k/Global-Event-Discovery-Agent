"""
Meetup GraphQL API — expanded global coverage.
No API key required for public events.

Previous: 5 topics × 5 cities  = 25 queries
This:     20 topics × 20 cities = 400 queries (rate-limited, ~60 per run)

Strategy: rotate through topic+city combos each run so over several
daily refreshes the full matrix is covered without hammering the API.
"""
import asyncio, random, hashlib
from datetime import date
from typing import List
from loguru import logger

try:
    import httpx
    HTTPX_OK = True
except ImportError:
    HTTPX_OK = False

from models.event import EventCreate
from ingestion.base_connector import BaseConnector

GQL_URL = "https://api.meetup.com/gql"

# Expanded topic list — all major B2B verticals
TOPICS = [
    "tech",
    "artificial-intelligence",
    "machine-learning",
    "data-science",
    "cloud-computing",
    "cybersecurity",
    "devops",
    "fintech",
    "blockchain",
    "startup",
    "entrepreneurship",
    "product-management",
    "digital-marketing",
    "ecommerce",
    "healthcare-technology",
    "logistics-supply-chain",
    "manufacturing",
    "energy-environment",
    "hr-technology",
    "legal-technology",
    "real-estate-technology",
    "saas",
    "sales",
    "leadership",
]

# Global cities with coordinates — all major regions
CITIES = [
    # Asia Pacific
    ("Singapore",     "SG",  1.3521,   103.8198),
    ("Mumbai",        "IN",  19.0760,   72.8777),
    ("Bangalore",     "IN",  12.9716,   77.5946),
    ("Delhi",         "IN",  28.7041,   77.1025),
    ("Hyderabad",     "IN",  17.3850,   78.4867),
    ("Sydney",        "AU", -33.8688,  151.2093),
    ("Melbourne",     "AU", -37.8136,  144.9631),
    ("Tokyo",         "JP",  35.6762,  139.6503),
    ("Seoul",         "KR",  37.5665,  126.9780),
    ("Kuala Lumpur",  "MY",   3.1390,  101.6869),
    ("Bangkok",       "TH",  13.7563,  100.5018),
    ("Jakarta",       "ID",  -6.2088,  106.8456),
    ("Hong Kong",     "HK",  22.3193,  114.1694),
    ("Shanghai",      "CN",  31.2304,  121.4737),
    # Middle East & Africa
    ("Dubai",         "AE",  25.2048,   55.2708),
    ("Riyadh",        "SA",  24.7136,   46.6753),
    ("Nairobi",       "KE",  -1.2921,   36.8219),
    ("Cape Town",     "ZA", -33.9249,   18.4241),
    # Europe
    ("London",        "GB",  51.5074,   -0.1278),
    ("Berlin",        "DE",  52.5200,   13.4050),
    ("Amsterdam",     "NL",  52.3676,    4.9041),
    ("Paris",         "FR",  48.8566,    2.3522),
    ("Stockholm",     "SE",  59.3293,   18.0686),
    ("Zurich",        "CH",  47.3769,    8.5417),
    # Americas
    ("New York",      "US",  40.7128,  -74.0060),
    ("San Francisco", "US",  37.7749, -122.4194),
    ("Austin",        "US",  30.2672,  -97.7431),
    ("Chicago",       "US",  41.8781,  -87.6298),
    ("Toronto",       "CA",  43.6532,  -79.3832),
    ("São Paulo",     "BR", -23.5505,  -46.6333),
]

GQL_QUERY = """
query($query: String!, $lat: Float!, $lon: Float!) {
  keywordSearch(
    filter: { query: $query, lat: $lat, lon: $lon, radius: 80 }
    input: { first: 25 }
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
            venue { name address city country }
            group { name topics { name } }
          }
        }
      }
    }
  }
}
"""

# How many topic-city combos to run per ingestion call.
# At 1 req/sec this is ~60s of API time.
# Rotate randomly so all combos are covered over multiple daily runs.
MAX_COMBOS_PER_RUN = 60


class MeetupConnector(BaseConnector):
    name = "Meetup"

    async def fetch(self) -> List[EventCreate]:
        if not HTTPX_OK:
            logger.warning("httpx not installed — skipping Meetup.")
            return []

        events: List[EventCreate] = []
        seen:   set               = set()

        # Build all combos, shuffle, take a random slice each run
        combos = [
            (topic, city, country, lat, lon)
            for topic in TOPICS
            for city, country, lat, lon in CITIES
        ]
        random.shuffle(combos)
        combos = combos[:MAX_COMBOS_PER_RUN]

        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            for topic, city, country, lat, lon in combos:
                payload = {
                    "query": GQL_QUERY,
                    "variables": {"query": topic, "lat": lat, "lon": lon},
                }
                try:
                    await asyncio.sleep(1.1)   # ~1 req/sec — polite rate limit
                    r = await client.post(GQL_URL, json=payload)
                    r.raise_for_status()
                    data = r.json()
                except Exception as e:
                    logger.debug(f"Meetup {topic}/{city}: {e}")
                    continue

                edges = (
                    data.get("data", {})
                        .get("keywordSearch", {})
                        .get("edges", [])
                )

                for edge in edges:
                    node = edge.get("node", {}).get("result", {})
                    if not node or "title" not in node:
                        continue

                    name       = self.safe_str(node.get("title", ""))
                    dt         = node.get("dateTime", "")
                    start_date = dt[:10] if dt else ""
                    if not start_date or not name:
                        continue

                    # Skip past events
                    if start_date < date.today().isoformat():
                        continue

                    venue        = node.get("venue") or {}
                    event_city   = venue.get("city", city)
                    event_country= venue.get("country", country)

                    dh = self.make_hash(name, start_date, event_city)
                    if dh in seen:
                        continue
                    seen.add(dh)

                    group      = node.get("group") or {}
                    raw_topics = [t.get("name", "") for t in group.get("topics", [])]
                    ind_tags   = ",".join(raw_topics[:6]).lower() or topic

                    going     = self.safe_int(node.get("going", 0))
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
                        category=topic.replace("-", " "),
                        industry_tags=ind_tags,
                        audience_personas="developers,tech professionals,startup founders,business leaders",
                        est_attendees=going,
                        ticket_price_usd=0.0,
                        price_description="Free (Meetup)",
                        registration_url=node.get("eventUrl", ""),
                    ))

        logger.info(f"Meetup: {len(events)} events from {len(combos)} queries.")
        return events
