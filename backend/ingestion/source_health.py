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

State is persisted to the app's own DB (Postgres/Neon or SQLite —
whatever `database_url` already points at, no new infra) and reloaded
at startup. This matters specifically on free hosting tiers (e.g.
Render's free plan spins the instance down after ~15min idle): a
purely in-memory circuit breaker resets on every cold start, so a
permanently-dead endpoint like a retired API gets re-probed on the
very next request after every idle period, burning latency and
(for quota-limited APIs) actual request budget for a call that is
certain to fail. Persisting the open/closed state — not hardcoding
a permanent "disabled" flag — keeps this dynamic: a source becomes
available again automatically as soon as its cool-off window elapses,
across restarts, with zero manual intervention.

Uses wall-clock time (time.time()) rather than time.time() so
cool-off windows survive a process restart — monotonic time resets to
0 on every new process and can't be compared across runs.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from loguru import logger
from sqlalchemy import text

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
        self._loaded = False   # set True once DB state has been loaded at startup

    def _state(self, source: str) -> _SourceState:
        return self._states.setdefault(source, _SourceState())

    def _persist_async(self, source: str) -> None:
        """
        Fire-and-forget persist of one source's state to the DB, mirroring
        the same non-blocking pattern already used elsewhere in this
        codebase (e.g. api/routes_events.py's post-search DB writes).
        Never awaited by callers — record_success/record_failure stay
        synchronous so every existing call site keeps working unchanged.
        """
        import asyncio
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return  # no loop (e.g. a script/test) — in-memory state still works
        asyncio.ensure_future(_persist_one(source, self._states[source]))

    # ── reporting ──────────────────────────────────────────────
    def record_success(self, source: str) -> None:
        st = self._state(source)
        st.soft_failures = 0
        if st.open_until:
            logger.info(f"source_health: {source} recovered — circuit closed")
        st.open_until = 0.0
        st.reason = ""
        self._persist_async(source)

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
        now = time.time()

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
        self._persist_async(source)

    # ── querying ───────────────────────────────────────────────
    def is_available(self, source: str) -> bool:
        st = self._states.get(source)
        if st is None or time.time() >= st.open_until:
            return True
        # remind at most once a minute so logs stay readable
        now = time.time()
        if now - st.last_logged > 60:
            st.last_logged = now
            mins = int((st.open_until - now) / 60)
            logger.info(f"source_health: skipping {source} ({st.reason}; retry in ~{mins} min)")
        return False

    def snapshot(self) -> dict:
        """For /admin diagnostics."""
        now = time.time()
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


# ── DB persistence ──────────────────────────────────────────────────
# Uses whatever engine db/database.py already resolved (Neon Postgres in
# production, SQLite locally) — no new infra, no new env vars. Table is
# tiny (one row per source) and self-heals: any failure here just means
# the circuit breaker falls back to in-memory-only behaviour for that
# request, never blocks or breaks ingestion.

async def ensure_table(conn) -> None:
    """Called from db.database.init_db() alongside its other migrations."""
    await conn.execute(text(
        "CREATE TABLE IF NOT EXISTS source_health ("
        "  source TEXT PRIMARY KEY,"
        "  open_until REAL DEFAULT 0,"
        "  reason TEXT DEFAULT '',"
        "  total_trips INTEGER DEFAULT 0"
        ")"
    ))


async def load_from_db(session_factory) -> None:
    """Seed the in-memory registry from persisted state. Call once at startup."""
    try:
        async with session_factory() as db:
            rows = (await db.execute(text(
                "SELECT source, open_until, reason, total_trips FROM source_health"
            ))).fetchall()
        now = time.time()
        loaded_open = 0
        for source, open_until, reason, total_trips in rows:
            st = source_health._state(source)
            st.open_until = float(open_until or 0)
            st.reason = reason or ""
            st.total_trips = int(total_trips or 0)
            if st.open_until > now:
                loaded_open += 1
        source_health._loaded = True
        if loaded_open:
            logger.info(
                f"source_health: restored {len(rows)} source(s) from DB, "
                f"{loaded_open} still in cool-off — survives cold starts on "
                f"free hosting tiers instead of re-probing dead endpoints"
            )
    except Exception as exc:
        logger.debug(f"source_health: DB state not loaded ({exc}) — starting fresh")


async def _persist_one(source: str, st: "_SourceState") -> None:
    try:
        from db.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                "INSERT INTO source_health (source, open_until, reason, total_trips) "
                "VALUES (:s, :o, :r, :t) "
                "ON CONFLICT (source) DO UPDATE SET "
                "  open_until = :o, reason = :r, total_trips = :t"
            ), {"s": source, "o": st.open_until, "r": st.reason, "t": st.total_trips})
            await db.commit()
    except Exception as exc:
        logger.debug(f"source_health: persist skipped for {source} ({exc})")
