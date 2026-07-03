"""
llm_client.py — free-tier-aware Groq LLM gateway.

Every LLM call in the app should go through `chat_json()` instead of
calling the Groq SDK directly. This layer exists because the project
runs on free tiers, where the constraints ARE the architecture:

  • Token budgeting  — estimates prompt tokens before sending; refuses
    (returns None) or lets callers chunk instead of burning a 413.
  • TPM rate limiter — sliding 60s window of tokens sent per model, so
    we queue briefly rather than trip Groq's on-demand TPM ceiling.
  • Model fallback   — on 413/429/5xx the call cascades down a chain of
    smaller/cheaper models instead of failing outright.
  • Robust JSON      — code-fence stripping + best-effort JSON repair
    (trailing commas, unquoted keys, truncated tails) so one malformed
    character doesn't discard an otherwise good completion.
  • Response cache   — small TTL cache keyed on (model, prompts); free
    tiers punish retries of identical work.

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
    from groq import Groq
except ImportError:                                     # pragma: no cover
    Groq = None


# ── Token estimation ───────────────────────────────────────────────
# Groq counts real tokens; we only need a safe upper-ish estimate.
# English prose ≈ 4 chars/token; JSON payloads are denser in symbols,
# so use 3.4 chars/token to stay conservative.

def estimate_tokens(text: str) -> int:
    return int(len(text) / 3.4) + 1


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
    tokens_sent: int = 0


class LLMClient:
    # substrings identifying non-chat models we must never route JSON to
    _NON_CHAT = ("whisper", "tts", "guard", "embed", "moderation", "vision-preview")

    def __init__(self) -> None:
        self._client: Optional["Groq"] = None
        self._windows: dict[str, _TPMWindow] = {}
        self._cache = _TTLCache()
        self.stats = LLMStats()
        self._available_models: Optional[set[str]] = None
        self._models_fetched_at: float = 0.0
        self._resolved_chain: Optional[list[str]] = None

    # -- infra ------------------------------------------------------
    def _groq(self) -> Optional["Groq"]:
        if self._client is None and Groq and settings.groq_api_key:
            self._client = Groq(api_key=settings.groq_api_key)
        return self._client

    @property
    def _configured_chain(self) -> list[str]:
        chain = [settings.groq_model] + [
            m.strip() for m in settings.groq_fallback_models.split(",") if m.strip()
        ]
        seen: set[str] = set()
        return [m for m in chain if not (m in seen or seen.add(m))]

    async def _fetch_available_models(self) -> Optional[set[str]]:
        """Live model list from Groq's /models endpoint, cached for 1h.

        Models get decommissioned on free tiers without notice; asking the
        API is the only future-proof source of truth.
        """
        now = time.monotonic()
        if self._available_models is not None and now - self._models_fetched_at < 3600:
            return self._available_models
        client = self._groq()
        if client is None:
            return None
        try:
            resp = await asyncio.wait_for(asyncio.to_thread(client.models.list), timeout=10)
            ids = {
                m.id for m in resp.data
                if getattr(m, "active", True)
                and not any(s in m.id.lower() for s in self._NON_CHAT)
            }
            if ids:
                self._available_models = ids
                self._models_fetched_at = now
                self._resolved_chain = None          # re-resolve against fresh list
                return ids
        except Exception as exc:
            logger.warning(f"llm_client: could not list Groq models ({exc}) — using configured chain")
        return self._available_models

    async def resolve_model_chain(self) -> list[str]:
        """Configured chain filtered to models that actually exist right now,
        padded with live models when everything configured is decommissioned."""
        if self._resolved_chain is not None:
            return self._resolved_chain

        configured = self._configured_chain
        available = await self._fetch_available_models()
        if not available:                            # can't verify — trust config
            return configured

        chain = [m for m in configured if m in available]
        dropped = [m for m in configured if m not in available]
        if dropped:
            logger.warning(f"llm_client: dropping decommissioned model(s) {dropped}")

        if len(chain) < 2:
            # auto-pick fallbacks from what Groq actually serves, small-first
            def _pref(mid: str) -> int:
                m = mid.lower()
                if "gpt-oss-20b" in m: return 0
                if "gpt-oss" in m:     return 1
                if "qwen" in m:        return 2
                if "llama" in m:       return 3
                return 4
            for mid in sorted(available, key=_pref):
                if mid not in chain:
                    chain.append(mid)
                if len(chain) >= 3:
                    break
            logger.info(f"llm_client: auto-resolved model chain → {chain}")

        self._resolved_chain = chain
        return chain

    def _window(self, model: str) -> _TPMWindow:
        return self._windows.setdefault(model, _TPMWindow())

    # -- public helpers ----------------------------------------------
    def fits_budget(self, *texts: str, completion_tokens: int = 0) -> bool:
        """Can this payload ever fit under the per-request token ceiling?"""
        need = sum(estimate_tokens(t) for t in texts) + completion_tokens
        return need <= settings.groq_tpm_limit

    def budget_for_payload(self, fixed: str, completion_tokens: int) -> int:
        """Chars available for the variable part of a prompt."""
        spare = settings.groq_tpm_limit - estimate_tokens(fixed) - completion_tokens
        return max(0, int(spare * 3.4 * 0.9))           # 10% safety margin

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
        else dict/list), or None when every model in the chain failed.
        """
        client = self._groq()
        if client is None:
            logger.warning(f"[{label}] GROQ_API_KEY not configured — skipping LLM call")
            return None

        max_out = max_completion_tokens or settings.groq_max_tokens
        tout = timeout or settings.groq_timeout_seconds
        prompt_tokens = estimate_tokens(system) + estimate_tokens(user)

        cache_key = ""
        if cache_ttl > 0:
            cache_key = hashlib.sha256(f"{system}|{user}".encode()).hexdigest()
            hit = self._cache.get(cache_key)
            if hit is not None:
                self.stats.cache_hits += 1
                logger.debug(f"[{label}] cache hit")
                return hit

        if prompt_tokens + max_out > settings.groq_tpm_limit:
            logger.warning(
                f"[{label}] payload ~{prompt_tokens}+{max_out} tokens exceeds "
                f"TPM limit {settings.groq_tpm_limit} — caller must chunk; skipping"
            )
            return None

        chain = await self.resolve_model_chain()
        for i, model in enumerate(chain):
            ok = await self._window(model).reserve(
                prompt_tokens + max_out,
                settings.groq_tpm_limit,
                max_wait=settings.groq_tpm_max_wait_seconds,
            )
            if not ok:
                logger.warning(f"[{label}] TPM window full for {model} — trying next model")
                continue

            raw = await self._request(client, model, system, user, max_out,
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

            self.stats.calls += 1
            self.stats.tokens_sent += prompt_tokens
            if i > 0:
                logger.info(f"[{label}] served by fallback model {model}")
            if cache_key:
                self._cache.put(cache_key, parsed, cache_ttl)
            return parsed

        self.stats.failures += 1
        logger.error(f"[{label}] all models failed: {chain}")
        return None

    @staticmethod
    def _is_reasoning_model(model: str) -> bool:
        """Reasoning models (gpt-oss, qwen3, deepseek-r1) spend completion
        tokens thinking before emitting JSON — they need extra headroom and
        low reasoning effort, or strict json_object mode 400s with
        'max completion tokens reached before generating a valid document'."""
        m = model.lower()
        return "gpt-oss" in m or "qwen3" in m or "r1" in m

    async def _request(
        self, client, model, system, user, max_out, temperature, tout, label,
    ) -> Optional[str]:
        kwargs = dict(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=settings.groq_temperature if temperature is None else temperature,
            max_tokens=max_out,
            response_format={"type": "json_object"},
        )
        if self._is_reasoning_model(model):
            # keep thinking short and give the JSON room to finish
            kwargs["reasoning_effort"] = "low"
            kwargs["max_tokens"] = max(max_out, settings.groq_min_reasoning_tokens)

        for attempt in ("json_mode", "plain"):
            try:
                resp = await asyncio.wait_for(
                    asyncio.to_thread(client.chat.completions.create, **kwargs),
                    timeout=tout,
                )
                return resp.choices[0].message.content
            except asyncio.TimeoutError:
                logger.warning(f"[{label}] {model} timed out after {tout}s")
                return None
            except TypeError:
                # SDK/model rejects reasoning_effort — retry without it
                kwargs.pop("reasoning_effort", None)
                continue
            except Exception as exc:
                msg = str(exc)
                if "json_validate_failed" in msg and attempt == "json_mode":
                    # Groq's strict JSON mode discards the whole completion on a
                    # formatting slip. Retry unconstrained — extract_json() can
                    # repair fences/trailing junk that strict mode cannot.
                    logger.warning(f"[{label}] {model} strict JSON mode failed — retrying without response_format")
                    kwargs.pop("response_format", None)
                    kwargs["max_tokens"] = max(kwargs["max_tokens"], settings.groq_min_reasoning_tokens)
                    continue
                if "413" in msg or "rate_limit" in msg or "429" in msg:
                    logger.warning(f"[{label}] {model} rate/size limited — falling back")
                else:
                    logger.error(f"[{label}] {model} error: {exc}")
                return None
        return None


# module-level singleton
llm = LLMClient()
