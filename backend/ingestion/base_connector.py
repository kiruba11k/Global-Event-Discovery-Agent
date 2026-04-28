from abc import ABC, abstractmethod
from typing import List
from models.event import EventCreate
from loguru import logger
import hashlib
import uuid


class BaseConnector(ABC):
    name: str = "base"

    def make_id(self) -> str:
        return str(uuid.uuid4())

    def make_hash(self, name: str, start_date: str, city: str) -> str:
        raw = f"{name.lower().strip()}|{start_date}|{city.lower().strip()}"
        return hashlib.md5(raw.encode()).hexdigest()

    def safe_str(self, val, default="") -> str:
        if val is None:
            return default
        return str(val).strip()

    def safe_int(self, val, default=0) -> int:
        try:
            return int(str(val).replace(",", "").replace("+", "").replace("~", ""))
        except Exception:
            return default

    @abstractmethod
    async def fetch(self) -> List[EventCreate]:
        """Fetch events and return normalised EventCreate objects."""
        pass

    async def run(self) -> List[EventCreate]:
        try:
            logger.info(f"[{self.name}] Starting fetch...")
            events = await self.fetch()
            logger.info(f"[{self.name}] Fetched {len(events)} events.")
            return events
        except Exception as e:
            logger.error(f"[{self.name}] Fetch failed: {e}")
            return []
