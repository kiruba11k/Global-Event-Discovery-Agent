"""
ingestion/confstech.py - confs.tech open conference dataset connector.

Source: https://github.com/tech-conferences/conference-data
Community-maintained JSON files, one per year/topic, served from
raw.githubusercontent.com (no key, no rate limits, PR-reviewed data).

Format verified live (2026/security.json):
  [
    {"name": "Nullcon Goa", "url": "https://nullcon.net/goa-2026",
     "startDate": "2026-02-28", "endDate": "2026-03-01",
     "city": "Goa", "country": "India", "online": false,
     "cfpUrl": "...", "twitter": "..."}
  ]

Topics are fetched per-year; a missing topic file (404) is normal -
not every topic exists every year - and is skipped silently.
"""
from datetime import date
from typing import List

import httpx
from loguru import logger

from ingestion.base_connector import BaseConnector
from models.event import EventCreate

_RAW_BASE = "https://raw.githubusercontent.com/tech-conferences/conference-data/main/conferences"

# Topics verified to exist for 2026 (missing years/topics 404 harmlessly).
# topic -> (industry_tags, audience_personas)
_TOPICS: dict[str, tuple[str, str]] = {
    "security":      ("cybersecurity, information security, tech",
                      "CISO, security director, head of security, security engineer"),
    "devops":        ("devops, cloud, software, tech",
                      "CTO, VP engineering, head of devops, cloud architect"),
    "data":          ("data & analytics, big data, AI, tech",
                      "CDO, head of data, data engineer, analytics manager"),
    "general":       ("technology, software, tech",
                      "CTO, CIO, VP engineering, developer"),
    "javascript":    ("software, web development, tech",
                      "CTO, VP engineering, frontend lead, developer"),
    "typescript":    ("software, web development, tech",
                      "CTO, VP engineering, developer"),
    "python":        ("software, AI, data science, tech",
                      "CTO, data scientist, ML engineer, developer"),
    "java":          ("software, enterprise software, tech",
                      "CTO, VP engineering, enterprise architect"),
    "dotnet":        ("software, enterprise software, tech",
                      "CTO, VP engineering, enterprise architect"),
    "php":           ("software, web development, tech",
                      "CTO, VP engineering, developer"),
    "rust":          ("software, systems engineering, tech",
                      "CTO, VP engineering, developer"),
    "kotlin":        ("software, mobile development, tech",
                      "CTO, VP engineering, mobile lead"),
    "android":       ("mobile development, software, tech",
                      "CTO, mobile lead, product head"),
    "ios":           ("mobile development, software, tech",
                      "CTO, mobile lead, product head"),
    "css":           ("web development, design, tech",
                      "frontend lead, design lead, developer"),
    "graphql":       ("software, api, web development, tech",
                      "CTO, VP engineering, developer"),
    "clojure":       ("software, tech", "CTO, VP engineering, developer"),
    "iot":           ("iot, hardware, industrial iot, tech",
                      "CTO, VP engineering, product head, IoT architect"),
    "networking":    ("networking, telecom, infrastructure, tech",
                      "CIO, CTO, network architect, infrastructure manager"),
    "ux":            ("design, ux, product, tech",
                      "head of design, product head, UX director"),
    "product":       ("product management, saas, tech",
                      "CPO, VP product, product manager"),
    "leadership":    ("engineering leadership, management, tech",
                      "CTO, VP engineering, engineering manager"),
    "performance":   ("software, web performance, tech",
                      "CTO, VP engineering, developer"),
    "testing":       ("software, qa, testing, tech",
                      "QA lead, VP engineering, test manager"),
    "opensource":    ("open source, software, tech",
                      "CTO, VP engineering, developer advocate"),
    "accessibility": ("accessibility, ux, web development, tech",
                      "head of design, frontend lead, compliance manager"),
}


class ConfsTechConnector(BaseConnector):
    name = "ConfsTech"

    def _years(self) -> list[int]:
        y = date.today().year
        return [y, y + 1]

    async def fetch(self) -> List[EventCreate]:
        events: List[EventCreate] = []
        seen: set[str] = set()
        today = date.today().isoformat()

        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            for year in self._years():
                for topic, (industry, personas) in _TOPICS.items():
                    url = f"{_RAW_BASE}/{year}/{topic}.json"
                    try:
                        resp = await client.get(url)
                    except httpx.HTTPError as exc:
                        logger.debug(f"[ConfsTech] {url}: {exc}")
                        continue
                    if resp.status_code != 200:
                        continue        # topic doesn't exist for this year
                    try:
                        rows = resp.json()
                    except ValueError:
                        logger.warning(f"[ConfsTech] {url}: invalid JSON")
                        continue
                    if not isinstance(rows, list):
                        continue

                    for row in rows:
                        ev = self._to_event(row, topic, industry, personas, today)
                        if ev is None or ev.dedup_hash in seen:
                            continue
                        seen.add(ev.dedup_hash)
                        events.append(ev)

        logger.info(f"ConfsTech: {len(events)} upcoming conferences loaded.")
        return events

    def _to_event(self, row: dict, topic: str, industry: str,
                  personas: str, today: str) -> EventCreate | None:
        if not isinstance(row, dict):
            return None
        name  = self.safe_str(row.get("name"))
        start = self.safe_str(row.get("startDate"))
        url   = self.safe_str(row.get("url"))
        if not name or not start or len(start) < 10:
            return None
        if start < today:
            return None

        online  = bool(row.get("online"))
        city    = self.safe_str(row.get("city")) or ("Online" if online else "")
        country = self.safe_str(row.get("country")) or ("Online" if online else "")
        end     = self.safe_str(row.get("endDate")) or start
        year    = start[:4]
        # Editions repeat yearly under the same name - keep the year visible
        display = name if year in name else f"{name} {year}"

        desc = (
            f"{display} is a {topic} conference"
            + (f" in {city}, {country}" if city and not online else
               " held online" if online else "")
            + f". Listed in the community-curated confs.tech index ({topic} track)."
        )

        return EventCreate(
            id=self.make_id(),
            source_platform="ConfsTech",
            source_url=url or f"https://confs.tech/{year[:4]}",
            dedup_hash=self.make_hash(display, start, city),
            name=display,
            description=desc,
            short_summary=desc[:150],
            start_date=start,
            end_date=end,
            city=city,
            country=country,
            is_virtual=online,
            category="conference",
            industry_tags=industry,
            audience_personas=personas,
            est_attendees=0,
            ticket_price_usd=0.0,
            price_description="See website",
            registration_url=url,
            website=url,
            sponsors="",
            speakers_url="",
            agenda_url="",
        )
