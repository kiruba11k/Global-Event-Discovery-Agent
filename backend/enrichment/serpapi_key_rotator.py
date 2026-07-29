"""
enrichment/serpapi_key_rotator.py — pick a SerpAPI key with credits left.

We run multiple free-tier SerpAPI accounts (100 searches/month each).
Rather than hardcoding which key to use, this checks each configured
key's remaining monthly credits via SerpAPI's account endpoint and
returns the first one that has enough left for the batch about to run —
falling through SERPAPI_KEY -> SERPAPI_KEY2 -> SERPAPI_KEY3 in order.

The account endpoint (https://serpapi.com/account.json) does NOT consume
a search credit — it's free to poll — but we still cache each key's
balance for a few minutes so a burst of requests doesn't hammer it.
"""
from __future__ import annotations

import time
from typing import Optional

import httpx
from loguru import logger

_ACCOUNT_URL = "https://serpapi.com/account.json"

# How long a key's credit-balance check is trusted before re-checking.
# Balance only changes as we spend it (roughly once per search job), so
# a short cache avoids an extra HTTP round-trip on every request without
# risking a stale "has credits" read for long.
_BALANCE_CACHE_TTL_SECONDS = 300

# {key: (checked_at_monotonic, searches_left)}
_balance_cache: dict[str, tuple[float, int]] = {}


def _fetch_searches_left(api_key: str) -> Optional[int]:
    """
    Returns remaining searches for this key this month, or None if the
    lookup failed (network error, invalid key, unexpected response shape)
    — callers should treat None as "unknown, don't rely on this key".
    """
    try:
        resp = httpx.get(_ACCOUNT_URL, params={"api_key": api_key}, timeout=8)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning(f"SerpAPI account check failed for key …{api_key[-4:]}: {exc}")
        return None

    # SerpAPI account.json returns plan_searches_left directly for the
    # free tier (no extra_credits); total_searches_left covers accounts
    # with purchased extra credits on top of the plan quota.
    left = data.get("total_searches_left")
    if left is None:
        left = data.get("plan_searches_left")
    if left is None:
        this_month = data.get("this_month_usage", 0)
        plan_limit = data.get("searches_per_month", 0)
        if plan_limit:
            left = max(0, plan_limit - this_month)
    if left is None:
        logger.warning(f"SerpAPI account response for key …{api_key[-4:]} had no usable credit field: {data}")
        return None
    return int(left)


def _searches_left(api_key: str) -> Optional[int]:
    cached = _balance_cache.get(api_key)
    if cached and (time.monotonic() - cached[0]) < _BALANCE_CACHE_TTL_SECONDS:
        return cached[1]

    left = _fetch_searches_left(api_key)
    if left is not None:
        _balance_cache[api_key] = (time.monotonic(), left)
    return left


def pick_active_key(candidate_keys: list[str], needed: int = 1) -> str:
    """
    Returns the first key (in order) with at least `needed` searches left
    this month. Falls back to the first non-empty key if every account
    check fails or all keys are low (better to try and hit a real 429
    than to enrich nothing), and returns "" if no keys are configured.
    """
    keys = [k.strip() for k in candidate_keys if k and k.strip()]
    if not keys:
        return ""
    if len(keys) == 1:
        return keys[0]

    for key in keys:
        left = _searches_left(key)
        if left is not None and left >= needed:
            logger.debug(f"SerpAPI key …{key[-4:]} selected ({left} searches left, need {needed})")
            return key
        if left is not None:
            logger.info(f"SerpAPI key …{key[-4:]} low on credits ({left} left, need {needed}) — trying next key")

    logger.warning("SerpAPI: no key confirmed to have enough credits — using the first configured key anyway")
    return keys[0]
