"""
api/rate_limit.py — one search per IP per UTC calendar day.

Backed by Redis (SET NX with a TTL expiring at the next UTC midnight) so
the limit is shared across worker processes — an in-process counter
would silently give every worker its own separate quota for the same IP.

Fails OPEN if Redis is unavailable: a rate limiter you can't check
should not be the reason the whole app goes down, matching the
"everything degrades silently" pattern used throughout this codebase
(pgvector_store.py, llm_client.py, etc.).
"""
from __future__ import annotations

import time

from fastapi import HTTPException, Request
from loguru import logger

from lib.redis_client import get_redis


def client_ip(request: Request) -> str:
    # Render (and most proxies) set X-Forwarded-For: client, proxy1, proxy2
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _seconds_until_utc_midnight() -> int:
    now = time.gmtime()
    seconds_today = now.tm_hour * 3600 + now.tm_min * 60 + now.tm_sec
    return max(60, 86400 - seconds_today)


async def enforce_daily_search_limit(request: Request) -> str:
    """
    Raises HTTPException(429) if this IP already searched today.
    Returns the IP address used for the check (caller can log/persist it).
    """
    ip = client_ip(request)
    r = await get_redis()
    if r is None:
        logger.warning("rate_limit: Redis unavailable — allowing request (fail-open)")
        return ip

    key = f"searchlimit:{ip}:{time.strftime('%Y-%m-%d', time.gmtime())}"
    try:
        was_set = await r.set(key, "1", nx=True, ex=_seconds_until_utc_midnight())
        if not was_set:
            ttl = await r.ttl(key)
            hours = max(1, (ttl or 0) // 3600)
            raise HTTPException(
                429,
                detail=(
                    "You've already used your one free search today. "
                    f"Please try again in about {hours} hour{'s' if hours != 1 else ''} "
                    "(resets at midnight UTC)."
                ),
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(f"rate_limit: Redis error ({exc}) — allowing request (fail-open)")
    return ip
