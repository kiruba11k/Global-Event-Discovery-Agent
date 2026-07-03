"""
source_health.py — circuit breaker registry for external event sources.

Free-tier APIs fail in ways that won't heal within a request:
  • 401 → key invalid            (won't fix itself; cool off long)
  • 402 → plan/credit exhausted  (monthly quota; cool off long)
  • 404 → endpoint retired       (won't fix itself; cool off long)
  • 429 → rate limited           (cool off short)
  • timeouts / 5xx               (transient; trip only after a streak)

Connectors report outcomes here; the pipeline asks `is_available()`
before spending queries (and quota) on a source that is known-down.
State is in-memory per process — cheap, and resets on deploy, which is
exactly the moment a fixed key would start working again.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from loguru import logger

# cool-off seconds per failure class
_HARD_COOLOFF = 6 * 3600     # 401 / 402 / 404 — config problems
_RATE_COOLOFF = 15 * 60      # 429
_SOFT_COOLOFF = 5 * 60       # streak of timeouts / 5xx
_SOFT_TRIP_AFTER = 3         # consecutive soft failures before tripping


@dataclass
class _SourceState:
    open_until: float = 0.0            # circuit open (unavailable) until
    reason: str = ""
    soft_failures: int = 0
    last_logged: float = 0.0
    total_trips: int = 0


class SourceHealthRegistry:
    def __init__(self) -> None:
        self._states: dict[str, _SourceState] = {}

    def _state(self, source: str) -> _SourceState:
        return self._states.setdefault(source, _SourceState())

    # ── reporting ──────────────────────────────────────────────
    def record_success(self, source: str) -> None:
        st = self._state(source)
        st.soft_failures = 0
        if st.open_until:
            logger.info(f"source_health: {source} recovered — circuit closed")
        st.open_until = 0.0
        st.reason = ""

    def record_failure(
        self,
        source: str,
        *,
        status: Optional[int] = None,
        kind: str = "transient",       # "auth" | "quota" | "gone" | "rate" | "transient"
        detail: str = "",
    ) -> None:
        """Report a failure. `status` (HTTP code) infers `kind` when given."""
        if status is not None:
            kind = {401: "auth", 403: "auth", 402: "quota",
                    404: "gone", 410: "gone", 429: "rate"}.get(status, "transient")

        st = self._state(source)
        now = time.monotonic()

        if kind in ("auth", "quota", "gone"):
            cool, why = _HARD_COOLOFF, {
                "auth":  "invalid/unauthorized API key",
                "quota": "plan or quota exhausted",
                "gone":  "endpoint no longer exists",
            }[kind]
        elif kind == "rate":
            cool, why = _RATE_COOLOFF, "rate limited"
        else:
            st.soft_failures += 1
            if st.soft_failures < _SOFT_TRIP_AFTER:
                return
            cool, why = _SOFT_COOLOFF, f"{st.soft_failures} consecutive transient failures"

        newly_open = now >= st.open_until
        st.open_until = now + cool
        st.reason = f"{why}{f' ({detail})' if detail else ''}"
        if newly_open:
            st.total_trips += 1
            logger.warning(
                f"source_health: {source} DISABLED for {cool // 60} min — {st.reason}. "
                f"Requests will skip it instead of burning quota."
            )

    # ── querying ───────────────────────────────────────────────
    def is_available(self, source: str) -> bool:
        st = self._states.get(source)
        if st is None or time.monotonic() >= st.open_until:
            return True
        # remind at most once a minute so logs stay readable
        now = time.monotonic()
        if now - st.last_logged > 60:
            st.last_logged = now
            mins = int((st.open_until - now) / 60)
            logger.info(f"source_health: skipping {source} ({st.reason}; retry in ~{mins} min)")
        return False

    def snapshot(self) -> dict:
        """For /admin diagnostics."""
        now = time.monotonic()
        return {
            name: {
                "available": now >= st.open_until,
                "reason": st.reason,
                "retry_in_seconds": max(0, int(st.open_until - now)),
                "total_trips": st.total_trips,
            }
            for name, st in self._states.items()
        }


# module-level singleton
source_health = SourceHealthRegistry()
