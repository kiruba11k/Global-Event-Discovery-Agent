"""
api/rate_limit.py — up to DAILY_SEARCH_LIMIT searches per browser per UTC day,
with a per-IP abuse ceiling as a secondary check.

Primary key: a client-generated device id (X-Device-Id header, a random
UUID the frontend creates once and persists in localStorage). This is
what actually identifies "one user" — unlike IP, it survives switching
networks and isn't shared with other people behind the same NAT (home
WiFi router, office network, mobile carrier CGNAT all put many distinct
people behind one public IP, which made pure IP-based limiting produce
false positives for anyone sharing a network with someone who'd already
used their quota).

Secondary key: IP address, with a much higher ceiling. This exists only
to catch trivial abuse (repeatedly clearing localStorage / spoofing a
new device id) — it should essentially never trigger for real users.

Falls back to IP-only limiting (at DAILY_SEARCH_LIMIT, the original
behavior) when no device id is sent — old cached frontend builds, direct
API callers, curl, etc. — so nothing is left unprotected.

Backed by Redis (INCR-based counters with a TTL expiring at the next
UTC midnight) so the limit is shared across worker processes — an
in-process counter would silently give every worker its own separate
quota for the same key.

INCR+EXPIRE is done via a single Lua script (EVAL) so the increment and
the "set expiry only on the first hit of the day" step are atomic — two
separate round-trips (INCR then check-and-EXPIRE) would race under
concurrent requests for the same key and could let the TTL never get
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

DAILY_SEARCH_LIMIT         = 3    # per browser/device — the real per-user limit
DAILY_SEARCH_LIMIT_PER_IP  = 15   # per IP — abuse ceiling only, generous enough
                                   # that a shared network full of real distinct
                                   # users never legitimately hits it

DEVICE_ID_HEADER = "x-device-id"

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


def device_id(request: Request) -> str:
    """Client-generated random id, persisted in the browser's localStorage.
    Empty string if the client didn't send one (old build, direct API call)."""
    return (request.headers.get(DEVICE_ID_HEADER) or "").strip()[:128]


def _seconds_until_utc_midnight() -> int:
    now = time.gmtime()
    seconds_today = now.tm_hour * 3600 + now.tm_min * 60 + now.tm_sec
    return max(60, 86400 - seconds_today)


async def _incr(r, key: str) -> int:
    return await r.eval(_INCR_WITH_TTL_SCRIPT, 1, key, _seconds_until_utc_midnight())


async def _raise_limit(r, key: str, limit: int, scope: str) -> None:
    ttl = await r.ttl(key)
    hours = max(1, (ttl or 0) // 3600)
    if scope == "device":
        detail = (
            f"You've used all {limit} free searches for today. "
            f"Please try again in about {hours} hour{'s' if hours != 1 else ''} "
            "(resets at midnight UTC)."
        )
    else:
        detail = (
            "Too many searches from your network today. "
            f"Please try again in about {hours} hour{'s' if hours != 1 else ''} "
            "(resets at midnight UTC)."
        )
    raise HTTPException(429, detail=detail)


async def enforce_daily_search_limit(request: Request) -> str:
    """
    Raises HTTPException(429) once this browser (or, as a fallback, this
    IP) has used its daily search allowance. Returns the IP address used
    for the check (caller can log/persist it).
    """
    ip  = client_ip(request)
    dev = device_id(request)
    r = await get_redis()
    if r is None:
        logger.warning("rate_limit: Redis unavailable — allowing request (fail-open)")
        return ip

    today = time.strftime("%Y-%m-%d", time.gmtime())

    try:
        if dev:
            # Primary: per-device limit. This is what actually stops one
            # person from searching more than DAILY_SEARCH_LIMIT times —
            # it doesn't care what IP they're on.
            dev_key = f"searchlimit:device:{dev}:{today}"
            dev_count = await _incr(r, dev_key)
            if dev_count > DAILY_SEARCH_LIMIT:
                await _raise_limit(r, dev_key, DAILY_SEARCH_LIMIT, scope="device")

            # Secondary: per-IP abuse ceiling, much higher, catches
            # someone clearing localStorage / spoofing device ids.
            ip_key = f"searchlimit:ip:{ip}:{today}"
            ip_count = await _incr(r, ip_key)
            if ip_count > DAILY_SEARCH_LIMIT_PER_IP:
                await _raise_limit(r, ip_key, DAILY_SEARCH_LIMIT_PER_IP, scope="ip")
        else:
            # No device id sent — fall back to the original IP-only
            # behavior so this path is never left unprotected.
            ip_key = f"searchlimit:ip:{ip}:{today}"
            ip_count = await _incr(r, ip_key)
            if ip_count > DAILY_SEARCH_LIMIT:
                await _raise_limit(r, ip_key, DAILY_SEARCH_LIMIT, scope="device")
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(f"rate_limit: Redis error ({exc}) — allowing request (fail-open)")
    return ip
