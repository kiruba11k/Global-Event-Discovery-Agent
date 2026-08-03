"""
api/bot_protection.py — CAPTCHA verification, honeypot check, and
duplicate-submission detection for the ICP form (POST /api/search).

Three independent layers, same "degrade, never hard-fail the request
pipeline" philosophy as api/rate_limit.py:

1. Honeypot — a hidden field real users never see/fill. Any non-empty
   value is a near-certain bot. Checked first since it's free (no I/O).

2. CAPTCHA (Cloudflare Turnstile) — verified server-side against
   Cloudflare's siteverify endpoint. Fails OPEN (treated as verified)
   if TURNSTILE_SECRET_KEY isn't configured, so this doesn't brick the
   form in dev / before the site key is provisioned — same fallback
   pattern as lib/redis_client.py / api/rate_limit.py.

3. Duplicate-submission — a short-lived Redis lock keyed by a
   fingerprint of (ip + email + company_name + buyer_description), so
   the same form re-submitted (double-click, retry) within the window
   is flagged. Fails OPEN (never flags) if Redis is unavailable.
"""
from __future__ import annotations

import hashlib
import os
import time

import httpx
from loguru import logger

from lib.redis_client import get_redis

TURNSTILE_SECRET_KEY = os.environ.get("TURNSTILE_SECRET_KEY", "")
TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"

DUPLICATE_WINDOW_SECONDS = 45


def honeypot_triggered(honeypot_value: str) -> bool:
    return bool((honeypot_value or "").strip())


async def verify_captcha(token: str, ip: str = "") -> bool:
    """Returns True if verified (or CAPTCHA isn't configured — fail-open).
    Returns False only when Turnstile is configured AND actively rejects
    the token."""
    if not TURNSTILE_SECRET_KEY:
        logger.debug("bot_protection: TURNSTILE_SECRET_KEY not set — captcha check skipped (fail-open)")
        return True
    if not token:
        return False
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(TURNSTILE_VERIFY_URL, data={
                "secret":   TURNSTILE_SECRET_KEY,
                "response": token,
                "remoteip": ip,
            })
            data = resp.json()
            return bool(data.get("success"))
    except Exception as exc:
        logger.warning(f"bot_protection: Turnstile verify failed ({exc}) — allowing request (fail-open)")
        return True


def _fingerprint(ip: str, email: str, company_name: str, buyer_description: str) -> str:
    raw = f"{ip}|{(email or '').strip().lower()}|{(company_name or '').strip().lower()}|{(buyer_description or '').strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


async def check_duplicate_submission(ip: str, email: str, company_name: str, buyer_description: str) -> tuple[bool, str]:
    """Returns (is_duplicate, fingerprint). Uses SET NX + short TTL as a
    lock — the first submission claims the key, any repeat within the
    window is a duplicate. Fails OPEN (never a duplicate) if Redis is
    unavailable, matching every other Redis-backed check in this app."""
    fp = _fingerprint(ip, email, company_name, buyer_description)
    r = await get_redis()
    if r is None:
        return False, fp
    key = f"submitlock:icp:{fp}"
    try:
        was_set = await r.set(key, str(time.time()), nx=True, ex=DUPLICATE_WINDOW_SECONDS)
        return (not was_set), fp
    except Exception as exc:
        logger.warning(f"bot_protection: duplicate-check Redis error ({exc}) — allowing request (fail-open)")
        return False, fp
