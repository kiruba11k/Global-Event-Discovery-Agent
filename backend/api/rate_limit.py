"""
api/rate_limit.py — up to DAILY_SEARCH_LIMIT searches per browser AND per
email per UTC day, with a per-IP abuse ceiling as a last-resort check.

Three layers, each catching what the others miss:

1. Device id (X-Device-Id header, a random UUID the frontend creates
   once and persists in localStorage). Identifies "this browser" —
   survives switching networks, but resets if someone clears
   localStorage or uses a different browser/incognito window.

2. Work email (from the ICP form, required on every search). Catches
   someone who clears localStorage / switches browsers but reuses
   their real email. Normalised (lowercased, trimmed) before keying.

3. IP address, with a much higher ceiling. Pure IP-based limiting alone
   produces false positives — home WiFi routers, office networks, and
   mobile carrier CGNAT all put many distinct people behind one public
   IP — so this is deliberately generous and exists only to catch
   someone spoofing BOTH a new device id AND a new fake email on every
   request (e.g. scripted abuse), not to gate normal shared-network use.

A request is blocked if EITHER the device or the email counter is
already at DAILY_SEARCH_LIMIT — whichever bypass someone tries (fake
email, cleared browser), the other layer still holds. Falls back to
IP-only limiting (at DAILY_SEARCH_LIMIT) when no device id is sent at
all — old cached frontend builds, direct API callers, curl, etc. — so
nothing is left unprotected.

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

DAILY_SEARCH_LIMIT         = 3    # per device / per email — the real per-user limit
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


def _normalise_email(email: str) -> str:
    return (email or "").strip().lower()


def _seconds_until_utc_midnight() -> int:
    now = time.gmtime()
    seconds_today = now.tm_hour * 3600 + now.tm_min * 60 + now.tm_sec
    return max(60, 86400 - seconds_today)


async def _incr(r, key: str) -> int:
    return await r.eval(_INCR_WITH_TTL_SCRIPT, 1, key, _seconds_until_utc_midnight())


async def _raise_limit(r, key: str, limit: int, scope: str) -> None:
    ttl = await r.ttl(key)
    hours = max(1, (ttl or 0) // 3600)
    if scope == "ip":
        detail = (
            "Too many searches from your network today. "
            f"Please try again in about {hours} hour{'s' if hours != 1 else ''} "
            "(resets at midnight UTC)."
        )
    else:
        detail = (
            f"You've used all {limit} free searches for today. "
            f"Please try again in about {hours} hour{'s' if hours != 1 else ''} "
            "(resets at midnight UTC)."
        )
    raise HTTPException(429, detail=detail)


async def enforce_daily_search_limit(request: Request, email: str = "") -> str:
    """
    Raises HTTPException(429) once this browser, this email, or (as a
    fallback / abuse ceiling) this IP has used its daily search
    allowance. Returns the IP address used for the check (caller can
    log/persist it).
    """
    ip    = client_ip(request)
    dev   = device_id(request)
    mail  = _normalise_email(email)
    r = await get_redis()
    if r is None:
        logger.warning("rate_limit: Redis unavailable — allowing request (fail-open)")
        return ip

    today = time.strftime("%Y-%m-%d", time.gmtime())

    try:
        if dev or mail:
            # Primary layers: per-device and per-email limits. Between
            # them these actually stop one person from exceeding the
            # daily quota, regardless of which one someone tries to
            # dodge (fake email keeps the device cap; cleared browser
            # keeps the email cap).
            if dev:
                dev_key = f"searchlimit:device:{dev}:{today}"
                dev_count = await _incr(r, dev_key)
                if dev_count > DAILY_SEARCH_LIMIT:
                    await _raise_limit(r, dev_key, DAILY_SEARCH_LIMIT, scope="device")

            if mail:
                mail_key = f"searchlimit:email:{mail}:{today}"
                mail_count = await _incr(r, mail_key)
                if mail_count > DAILY_SEARCH_LIMIT:
                    await _raise_limit(r, mail_key, DAILY_SEARCH_LIMIT, scope="email")

            # Secondary: per-IP abuse ceiling, much higher, catches
            # someone spoofing both a new device id and a new email.
            ip_key = f"searchlimit:ip:{ip}:{today}"
            ip_count = await _incr(r, ip_key)
            if ip_count > DAILY_SEARCH_LIMIT_PER_IP:
                await _raise_limit(r, ip_key, DAILY_SEARCH_LIMIT_PER_IP, scope="ip")
        else:
            # No device id AND no email — fall back to the original
            # IP-only behavior so this path is never left unprotected.
            ip_key = f"searchlimit:ip:{ip}:{today}"
            ip_count = await _incr(r, ip_key)
            if ip_count > DAILY_SEARCH_LIMIT:
                await _raise_limit(r, ip_key, DAILY_SEARCH_LIMIT, scope="device")
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(f"rate_limit: Redis error ({exc}) — allowing request (fail-open)")
    return ip
