"""
llm_client.py — cost-capped OpenAI LLM gateway.

Every LLM call in the app should go through `chat_json()` instead of
calling the OpenAI SDK directly. Unlike Groq's free tier, OpenAI bills
per token — so this layer's job is to make sure traffic never turns into
a surprise bill:

  • Token budgeting  — estimates prompt tokens before sending; refuses
    (returns None) or lets callers chunk instead of sending an
    oversized (and expensive) request.
  • TPM rate limiter — sliding 60s window of tokens sent per model, a
    self-imposed throttle so a traffic spike queues briefly instead of
    firing an unbounded number of billed calls at once.
  • Daily USD budget — tracks estimated spend per UTC day; once it
    crosses `settings.openai_daily_usd_budget`, calls are refused
    (returns None) instead of silently continuing to bill. Every call
    site already degrades gracefully on None (skip validation, fall
    back to rule-based scoring), so this fails safe.
  • Model fallback   — on errors/429/5xx the call cascades down a chain
    of configured models (keep every entry on the cheap mini/nano tier).
  • Robust JSON      — code-fence stripping + best-effort JSON repair
    (trailing commas, unquoted keys, truncated tails) so one malformed
    character doesn't discard an otherwise good (and already paid-for)
    completion.
  • Response cache   — small TTL cache keyed on (model, prompts); avoids
    re-billing for identical repeated work.

All knobs live in config.Settings so they can be tuned per deployment
via environment variables.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Type

from loguru import logger
from pydantic import BaseModel, ValidationError

from config import get_settings

settings = get_settings()

try:
    from openai import OpenAI
except ImportError:                                     # pragma: no cover
    OpenAI = None


# ── Token estimation ───────────────────────────────────────────────
# We only need a safe upper-ish estimate for budgeting/throttling, not
# exact billing figures (the API response has real usage for that).
# English prose ≈ 4 chars/token; JSON payloads are denser in symbols,
# so use 3.4 chars/token to stay conservative.

def estimate_tokens(text: str) -> int:
    return int(len(text) / 3.4) + 1


# ── Per-model $ pricing (USD per 1M tokens) — mini/nano tier only ───
# Used solely to estimate spend for the daily budget guard. Approximate
# on purpose: the guard just needs to be in the right ballpark to stop
# a runaway loop, not match the invoice to the cent.
_PRICING_PER_1M: dict[str, tuple[float, float]] = {
    # (input $/1M, output $/1M)
    "gpt-4o-mini":  (0.15, 0.60),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4o":       (2.50, 10.00),
}
_DEFAULT_PRICING = (0.50, 1.50)  # conservative fallback for unlisted models


def _estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    in_price, out_price = _PRICING_PER_1M.get(model, _DEFAULT_PRICING)
    return (prompt_tokens / 1_000_000) * in_price + (completion_tokens / 1_000_000) * out_price


# ── Sliding-window TPM limiter ─────────────────────────────────────

class _TPMWindow:
    """Tracks tokens sent in the last 60s and how long to wait."""

    def __init__(self) -> None:
        self._events: list[tuple[float, int]] = []      # (ts, tokens)
        self._lock = asyncio.Lock()

    async def reserve(self, tokens: int, limit: int, max_wait: float) -> bool:
        """Wait (bounded) until `tokens` fits in the window. False = give up."""
        deadline = time.monotonic() + max_wait
        while True:
            async with self._lock:
                now = time.monotonic()
                self._events = [(t, n) for t, n in self._events if now - t < 60]
                used = sum(n for _, n in self._events)
                if used + tokens <= limit:
                    self._events.append((now, tokens))
                    return True
                # earliest event whose expiry frees enough tokens
                wait = min((60 - (now - t)) for t, _ in self._events) + 0.05
            if time.monotonic() + wait > deadline:
                return False
            await asyncio.sleep(min(wait, deadline - time.monotonic()))


# ── Daily USD spend guard ────────────────────────────────────────────

class _DailyBudget:
    """Tracks estimated spend for the current UTC day; resets at midnight."""

    def __init__(self) -> None:
        self._day: Optional[str] = None
        self._spent: float = 0.0
        self._lock = asyncio.Lock()

    @staticmethod
    def _today() -> str:
        return time.strftime("%Y-%m-%d", time.gmtime())

    async def remaining(self, budget: float) -> float:
        async with self._lock:
            today = self._today()
            if today != self._day:
                self._day, self._spent = today, 0.0
            return max(0.0, budget - self._spent)

    async def add(self, usd: float) -> None:
        async with self._lock:
            today = self._today()
            if today != self._day:
                self._day, self._spent = today, 0.0
            self._spent += usd

    async def spent_today(self) -> float:
        async with self._lock:
            today = self._today()
            if today != self._day:
                return 0.0
            return self._spent


# ── JSON repair ────────────────────────────────────────────────────

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def extract_json(raw: str) -> Optional[Any]:
    """Best-effort: parse raw LLM output into a Python object."""
    if not raw:
        return None
    text = raw.strip()

    m = _FENCE_RE.search(text)
    if m:
        text = m.group(1).strip()

    # slice from the first { or [ to the matching region
    start = min([i for i in (text.find("{"), text.find("[")) if i >= 0], default=-1)
    if start > 0:
        text = text[start:]

    for candidate in (text, _repair(text), _repair_cut(text)):
        if candidate is None:
            continue
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
    return None


def _clean(text: str) -> str:
    t = text
    # smart quotes → straight
    t = t.replace("“", '"').replace("”", '"').replace("’", "'")
    # trailing commas before } or ]
    t = re.sub(r",\s*([}\]])", r"\1", t)
    # control chars are illegal inside JSON strings
    t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", t)
    return t


def _balance(t: str) -> str:
    t = re.sub(r",\s*$", "", t.rstrip())
    if t.count('"') % 2:
        t += '"'
    # close in reverse order of what's most recently open (approximation)
    t += "]" * max(0, t.count("[") - t.count("]"))
    t += "}" * max(0, t.count("{") - t.count("}"))
    return t


def _repair(text: str) -> Optional[str]:
    """Fix the classic LLM-JSON defects; balance brackets on truncation."""
    if not text:
        return None
    return _balance(_clean(text))


def _repair_cut(text: str) -> Optional[str]:
    """Harsher repair: drop the last (incomplete) element, then balance."""
    if not text:
        return None
    t = _clean(text)
    last = max(t.rfind("}"), t.rfind("]"), t.rfind('",'), t.rfind('"'))
    if last <= 0:
        return None
    return _balance(t[: last + 1])


# ── TTL response cache ─────────────────────────────────────────────

@dataclass
class _CacheEntry:
    value: Any
    expires: float


class _TTLCache:
    def __init__(self, max_items: int = 256) -> None:
        self._store: dict[str, _CacheEntry] = {}
        self._max = max_items

    def get(self, key: str) -> Optional[Any]:
        e = self._store.get(key)
        if e and e.expires > time.monotonic():
            return e.value
        self._store.pop(key, None)
        return None

    def put(self, key: str, value: Any, ttl: float) -> None:
        if len(self._store) >= self._max:
            # drop oldest-expiring entries
            for k in sorted(self._store, key=lambda k: self._store[k].expires)[:32]:
                self._store.pop(k, None)
        self._store[key] = _CacheEntry(value, time.monotonic() + ttl)


# ── The client ─────────────────────────────────────────────────────

@dataclass
class LLMStats:
    calls: int = 0
    cache_hits: int = 0
    fallbacks: int = 0
    failures: int = 0
    budget_blocked: int = 0
    tokens_sent: int = 0
    estimated_usd: float = 0.0


class LLMClient:
    # substrings identifying non-chat models we must never route JSON to
    _NON_CHAT = ("whisper", "tts", "embed", "moderation", "dall-e", "davinci",
                 "babbage", "audio", "realtime", "transcribe", "image")

    def __init__(self) -> None:
        self._client: Optional["OpenAI"] = None
        self._windows: dict[str, _TPMWindow] = {}
        self._cache = _TTLCache()
        self._budget = _DailyBudget()
        self.stats = LLMStats()
        self._available_models: Optional[set[str]] = None
        self._models_fetched_at: float = 0.0
        self._resolved_chain: Optional[list[str]] = None

    # -- infra ------------------------------------------------------
    def _openai(self) -> Optional["OpenAI"]:
        if self._client is None and OpenAI and settings.openai_api_key:
            self._client = OpenAI(api_key=settings.openai_api_key)
        return self._client

    @property
    def _configured_chain(self) -> list[str]:
        chain = [settings.openai_model] + [
            m.strip() for m in settings.openai_fallback_models.split(",") if m.strip()
        ]
        seen: set[str] = set()
        return [m for m in chain if not (m in seen or seen.add(m))]

    async def _fetch_available_models(self) -> Optional[set[str]]:
        """Live model list from OpenAI's /models endpoint, cached for 1h."""
        now = time.monotonic()
        if self._available_models is not None and now - self._models_fetched_at < 3600:
            return self._available_models
        client = self._openai()
        if client is None:
            return None
        try:
            resp = await asyncio.wait_for(asyncio.to_thread(client.models.list), timeout=10)
            ids = {
                m.id for m in resp.data
                if not any(s in m.id.lower() for s in self._NON_CHAT)
            }
            if ids:
                self._available_models = ids
                self._models_fetched_at = now
                self._resolved_chain = None          # re-resolve against fresh list
                return ids
        except Exception as exc:
            logger.warning(f"llm_client: could not list OpenAI models ({exc}) — using configured chain")
        return self._available_models

    async def resolve_model_chain(self) -> list[str]:
        """Configured chain, filtered to models that actually exist (best-effort)."""
        if self._resolved_chain is not None:
            return self._resolved_chain

        configured = self._configured_chain
        available = await self._fetch_available_models()
        if not available:                            # can't verify — trust config
            self._resolved_chain = configured
            return configured

        chain = [m for m in configured if m in available]
        dropped = [m for m in configured if m not in available]
        if dropped:
            logger.warning(f"llm_client: model(s) not available on this account {dropped}")
        if not chain:
            chain = configured  # trust config over an incomplete/odd model list

        self._resolved_chain = chain
        return chain

    def _window(self, model: str) -> _TPMWindow:
        return self._windows.setdefault(model, _TPMWindow())

    # -- public helpers ----------------------------------------------
    def fits_budget(self, *texts: str, completion_tokens: int = 0) -> bool:
        """Can this payload ever fit under the self-imposed TPM ceiling?"""
        need = sum(estimate_tokens(t) for t in texts) + completion_tokens
        return need <= settings.openai_tpm_limit

    def budget_for_payload(self, fixed: str, completion_tokens: int) -> int:
        """Chars available for the variable part of a prompt."""
        spare = settings.openai_tpm_limit - estimate_tokens(fixed) - completion_tokens
        return max(0, int(spare * 3.4 * 0.9))           # 10% safety margin

    async def spend_today(self) -> float:
        return await self._budget.spent_today()

    # -- main entry ---------------------------------------------------
    async def chat_json(
        self,
        system: str,
        user: str,
        *,
        label: str = "llm",
        schema: Optional[Type[BaseModel]] = None,
        max_completion_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        timeout: Optional[int] = None,
        cache_ttl: float = 0.0,
    ) -> Optional[Any]:
        """
        JSON-mode chat completion with budgeting, fallback and repair.

        Returns the parsed object (validated `schema` instance when given,
        else dict/list), or None when every model in the chain failed, the
        payload doesn't fit budget, or the daily spend cap is hit.
        """
        client = self._openai()
        if client is None:
            logger.warning(f"[{label}] OPENAI_API_KEY not configured — skipping LLM call")
            return None

        max_out = max_completion_tokens or settings.openai_max_tokens
        tout = timeout or settings.openai_timeout_seconds
        prompt_tokens = estimate_tokens(system) + estimate_tokens(user)

        cache_key = ""
        if cache_ttl > 0:
            cache_key = hashlib.sha256(f"{system}|{user}".encode()).hexdigest()
            hit = self._cache.get(cache_key)
            if hit is not None:
                self.stats.cache_hits += 1
                logger.debug(f"[{label}] cache hit — $0 spent")
                return hit

        if prompt_tokens + max_out > settings.openai_tpm_limit:
            logger.warning(
                f"[{label}] payload ~{prompt_tokens}+{max_out} tokens exceeds "
                f"self-imposed TPM ceiling {settings.openai_tpm_limit} — caller must chunk; skipping"
            )
            return None

        # Hard daily $ cap — estimate worst-case cost of this call up front
        # (using the primary model's pricing) before spending anything.
        est_cost = _estimate_cost_usd(settings.openai_model, prompt_tokens, max_out)
        remaining = await self._budget.remaining(settings.openai_daily_usd_budget)
        if est_cost > remaining:
            self.stats.budget_blocked += 1
            logger.warning(
                f"[{label}] daily OpenAI budget (${settings.openai_daily_usd_budget:.2f}) "
                f"would be exceeded (${remaining:.4f} left, call ~${est_cost:.4f}) — skipping"
            )
            return None

        chain = await self.resolve_model_chain()
        for i, model in enumerate(chain):
            ok = await self._window(model).reserve(
                prompt_tokens + max_out,
                settings.openai_tpm_limit,
                max_wait=settings.openai_tpm_max_wait_seconds,
            )
            if not ok:
                logger.warning(f"[{label}] TPM window full for {model} — trying next model")
                continue

            raw, usage = await self._request(client, model, system, user, max_out,
                                              temperature, tout, label)
            if raw is None:
                self.stats.fallbacks += 1
                continue

            parsed = extract_json(raw)
            if parsed is None:
                logger.warning(f"[{label}] {model}: unparseable JSON ({len(raw)} chars)")
                self.stats.fallbacks += 1
                continue

            if schema is not None:
                try:
                    parsed = schema.model_validate(parsed)
                except ValidationError as ve:
                    logger.warning(f"[{label}] {model}: schema mismatch — {ve.error_count()} errors")
                    self.stats.fallbacks += 1
                    continue

            # Bill against the daily budget using REAL usage when the API
            # returned it, falling back to the pre-call estimate otherwise.
            in_tok, out_tok = usage if usage else (prompt_tokens, max_out)
            actual_cost = _estimate_cost_usd(model, in_tok, out_tok)
            await self._budget.add(actual_cost)

            self.stats.calls += 1
            self.stats.tokens_sent += in_tok + out_tok
            self.stats.estimated_usd += actual_cost
            if i > 0:
                logger.info(f"[{label}] served by fallback model {model}")
            if cache_key:
                self._cache.put(cache_key, parsed, cache_ttl)
            return parsed

        self.stats.failures += 1
        logger.error(f"[{label}] all models failed: {chain}")
        return None

    async def _request(
        self, client, model, system, user, max_out, temperature, tout, label,
    ) -> tuple[Optional[str], Optional[tuple[int, int]]]:
        kwargs = dict(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=settings.openai_temperature if temperature is None else temperature,
            max_tokens=max_out,
            response_format={"type": "json_object"},
        )

        for attempt in ("json_mode", "plain"):
            try:
                resp = await asyncio.wait_for(
                    asyncio.to_thread(client.chat.completions.create, **kwargs),
                    timeout=tout,
                )
                usage = None
                if getattr(resp, "usage", None):
                    usage = (resp.usage.prompt_tokens, resp.usage.completion_tokens)
                return resp.choices[0].message.content, usage
            except asyncio.TimeoutError:
                logger.warning(f"[{label}] {model} timed out after {tout}s")
                return None, None
            except Exception as exc:
                msg = str(exc)
                if "json" in msg.lower() and attempt == "json_mode":
                    # Some models/prompts reject strict JSON mode outright.
                    # Retry unconstrained — extract_json() can repair
                    # fences/trailing junk that strict mode cannot.
                    logger.warning(f"[{label}] {model} strict JSON mode failed — retrying without response_format")
                    kwargs.pop("response_format", None)
                    continue
                if "rate_limit" in msg.lower() or "429" in msg or "insufficient_quota" in msg.lower():
                    logger.warning(f"[{label}] {model} rate/quota limited — falling back")
                else:
                    logger.error(f"[{label}] {model} error: {exc}")
                return None, None
        return None, None


# module-level singleton
llm = LLMClient()
