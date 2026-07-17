"""
queueing/search_queue.py — Redis-backed job queue for POST /api/search.

Why a queue: running the full search pipeline (DB query + scoring +
OpenAI ranking) synchronously inside the request/response cycle means
N simultaneous requests all race the same DB pool and OpenAI budget/TPM
window at once — under real concurrent load many time out. Instead:

  1. POST /api/search validates + persists the submission, pushes a job
     onto a Redis list, and returns {job_id, status: "queued"} immediately.
  2. A small pool of background workers (started at app startup, see
     main.py's lifespan) pull jobs one at a time and run the real
     pipeline (relevance/... scoring, OpenAI ranking).
  3. GET /api/search/status/{job_id} polls the job's status/result,
     stored in Redis so it's visible from ANY worker process — not just
     whichever one happens to actually run the job.

Without Redis configured, enqueue() returns None and the caller (the
/api/search route) runs the pipeline inline instead — same synchronous
behavior as before this feature existed. The queue only activates once
REDIS_URL is set, same fallback philosophy as relevance/llm_client.py.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Awaitable, Callable, Optional

from loguru import logger

from lib.redis_client import get_redis

QUEUE_KEY       = "search:queue"
JOB_KEY_PREFIX  = "search:job:"
JOB_TTL_SECONDS = 3600          # results expire after 1h — plenty of time to poll


async def enqueue(payload: dict) -> Optional[str]:
    """Push a job onto the queue. Returns job_id, or None if Redis is
    unavailable (caller should run the pipeline inline instead)."""
    r = await get_redis()
    if r is None:
        return None
    job_id = str(uuid.uuid4())
    job = {"status": "queued", "payload": payload, "result": None, "error": None}
    try:
        await r.set(f"{JOB_KEY_PREFIX}{job_id}", json.dumps(job, default=str), ex=JOB_TTL_SECONDS)
        await r.rpush(QUEUE_KEY, job_id)
        return job_id
    except Exception as exc:
        logger.warning(f"search_queue: enqueue failed ({exc}) — caller should run inline")
        return None


async def get_job(job_id: str) -> Optional[dict]:
    r = await get_redis()
    if r is None:
        return None
    try:
        raw = await r.get(f"{JOB_KEY_PREFIX}{job_id}")
        return json.loads(raw) if raw else None
    except Exception as exc:
        logger.warning(f"search_queue: get_job failed ({exc})")
        return None


async def _set_job(job_id: str, job: dict) -> None:
    r = await get_redis()
    if r is None:
        return
    try:
        await r.set(f"{JOB_KEY_PREFIX}{job_id}", json.dumps(job, default=str), ex=JOB_TTL_SECONDS)
    except Exception as exc:
        logger.warning(f"search_queue: set_job failed ({exc})")


ProcessFn = Callable[[dict], Awaitable[dict]]


async def worker_loop(worker_name: str, process_fn: ProcessFn) -> None:
    """
    Runs until cancelled, pulling job_ids from the queue and calling
    `process_fn(payload) -> result_dict` (the actual search pipeline).
    process_fn should raise on failure — caught here and stored as the
    job's error so GET /api/search/status/{job_id} can report it.
    """
    r = await get_redis()
    if r is None:
        logger.info(f"search_queue[{worker_name}]: Redis not configured — worker idle")
        return
    logger.info(f"search_queue[{worker_name}]: started")
    while True:
        try:
            popped = await r.blpop(QUEUE_KEY, timeout=5)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"search_queue[{worker_name}]: blpop failed ({exc}) — retrying in 2s")
            await asyncio.sleep(2)
            continue
        if not popped:
            continue
        _, job_id = popped
        job = await get_job(job_id)
        if job is None:
            continue
        job["status"] = "processing"
        await _set_job(job_id, job)
        try:
            result = await process_fn(job["payload"])
            job["status"] = "done"
            job["result"] = result
        except Exception as exc:
            logger.error(f"search_queue[{worker_name}]: job {job_id} failed: {exc}")
            job["status"] = "error"
            job["error"] = str(exc)
        await _set_job(job_id, job)
