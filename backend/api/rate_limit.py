"""
api/rate_limit.py — up to DAILY_SEARCH_LIMIT searches per IP per UTC day.

Backed by Redis (INCR-based counter with a TTL expiring at the next UTC
midnight) so the limit is shared across worker processes — an in-process
counter would silently give every worker its own separate quota for the
same IP.

INCR+EXPIRE is done via a single Lua script (EVAL) so the increment and
the "set expiry only on the first hit of the day" step are atomic — two
separate round-trips (INCR then check-and-EXPIRE) would race under
concurrent requests from the same IP and could let the TTL never get
set, or get reset on every request instead of only the first.

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

DAILY_SEARCH_LIMIT = 3

# KEYS[1] = the counter key, ARGV[1] = TTL seconds (only applied on the
# first increment of the day, so later requests don't keep pushing the
# expiry back out).
_INCR_WITH_TTL_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


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
    Raises HTTPException(429) once this IP has used DAILY_SEARCH_LIMIT
    searches today. Returns the IP address used for the check (caller
    can log/persist it).
    """
    ip = client_ip(request)
    r = await get_redis()
    if r is None:
        logger.warning("rate_limit: Redis unavailable — allowing request (fail-open)")
        return ip

    key = f"searchlimit:{ip}:{time.strftime('%Y-%m-%d', time.gmtime())}"
    try:
        count = await r.eval(_INCR_WITH_TTL_SCRIPT, 1, key, _seconds_until_utc_midnight())
        if count > DAILY_SEARCH_LIMIT:
            ttl = await r.ttl(key)
            hours = max(1, (ttl or 0) // 3600)
            raise HTTPException(
                429,
                detail=(
                    f"You've used all {DAILY_SEARCH_LIMIT} free searches for today. "
                    f"Please try again in about {hours} hour{'s' if hours != 1 else ''} "
                    "(resets at midnight UTC)."
                ),
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(f"rate_limit: Redis error ({exc}) — allowing request (fail-open)")
    return ip
