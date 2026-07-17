"""
lib/redis_client.py — single shared Redis connection for rate limiting
and the search job queue (relevance/llm_client.py keeps its own separate
connection for the LLM cache/budget/TPM state — different concern, no
need to share).

Same fallback philosophy as the rest of this app: if REDIS_URL isn't
set, or Redis is unreachable, get_redis() returns None and callers must
degrade (fail-open for rate limiting, run-inline for the job queue).
Never raises.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from loguru import logger

from config import get_settings

settings = get_settings()

try:
    import redis.asyncio as aioredis
except ImportError:                                     # pragma: no cover
    aioredis = None

_client: Optional["aioredis.Redis"] = None
_checked = False
_lock: Optional[asyncio.Lock] = None


def _get_lock() -> asyncio.Lock:
    # Created lazily, inside the running event loop — a module-level
    # `asyncio.Lock()` created at import time can bind to the wrong loop
    # under a test runner / multiple event loops.
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


async def get_redis() -> Optional["aioredis.Redis"]:
    """
    Resolve the shared Redis connection once, then cache the result
    (including a failed/unconfigured outcome) for every later call.

    Guarded by a lock: many callers hit this concurrently at process
    startup (queue workers) and per-request (rate limiter) — without a
    lock, N concurrent first-calls each see `_checked=False`, each try
    to connect, and whichever happens to run last silently overwrites
    whatever the others decided, i.e. a real, reproducible race.

    IMPORTANT: `_checked` is only set to True once the connection attempt
    has fully resolved (success OR failure) — NOT the moment we start
    trying. Acquiring an uncontended asyncio.Lock does not yield control,
    so the first caller runs synchronously right up to `await ping()`
    without giving other tasks a chance to run. If `_checked` were set
    True before that await, a concurrent second caller's fast-path check
    above (`if _checked: return _client`) would see _checked=True while
    _client is still None (the first caller hasn't finished yet) and
    return the wrong, stale None — bypassing the lock entirely. This was
    reproduced empirically: 3 concurrent callers, 2 got None while the
    3rd was still mid-connection and later succeeded.
    """
    global _client, _checked
    if _checked:
        return _client
    async with _get_lock():
        if _checked:                 # re-check: another task may have
            return _client           # resolved this while we waited for the lock
        if not (aioredis and settings.redis_url):
            _checked = True
            return None
        try:
            client = aioredis.from_url(
                settings.redis_url, decode_responses=True, socket_connect_timeout=3,
            )
            await client.ping()
            _client = client
            logger.info("lib.redis_client: connected")
        except Exception as exc:
            logger.warning(f"lib.redis_client: unavailable ({exc}) — dependent features degrade")
            _client = None
        finally:
            _checked = True       # only mark resolved AFTER _client has its final value
        return _client
