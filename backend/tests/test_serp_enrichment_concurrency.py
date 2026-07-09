"""
Regression test for enrichment/serp_enricher.py's enrich_events_batch().

Production incident: enriching the final 6 shown events took 2m19s
wall-clock (fully sequential, one SerpAPI+Groq round trip at a time,
each 8-70s). SerpAPI's free tier caps TOTAL requests per MONTH (100),
not requests per second, so serialising every call bought nothing in
quota safety while making every search feel broken.

Fixed with bounded concurrency (a small semaphore) instead of a full
sequential loop or unlimited fan-out. This test stubs the network call
to assert two properties without hitting a real API:
  1. Requests actually run concurrently (wall time << N * per-call time)
  2. One failing event never breaks the batch for the others
"""
import asyncio
import time

import pytest


class _FakeEvent:
    def __init__(self, idx: int, fail: bool = False):
        self.id = str(idx)
        self.name = f"Event {idx}" + ("-fail" if fail else "")
        self.est_attendees = 0
        self.price_description = ""
        self.description = ""
        self.source_url = ""
        self.website = ""
        self.registration_url = ""
        self.sponsors = "x"  # non-empty -> skip the sponsor sub-call
        self.start_date = "2026-09-01"
        self.city = "Singapore"
        self.industry_tags = "healthcare"


@pytest.mark.asyncio
async def test_enrichment_runs_concurrently_and_isolates_failures():
    import enrichment.serp_enricher as se

    async def fake_enrich_event(**kw):
        await asyncio.sleep(0.4)
        if "fail" in kw["event_name"]:
            raise RuntimeError("simulated SerpAPI failure")
        return {"est_attendees": 1000, "price_description": "$10"}

    se.enrich_event = fake_enrich_event
    se._SERPAPI_OK = True

    events = [_FakeEvent(i, fail=(i == 2)) for i in range(6)]

    t0 = time.monotonic()
    result = await se.enrich_events_batch(events, serpapi_key="fake", max_enrich=6)
    elapsed = time.monotonic() - t0

    assert len(result) == 5, "the one failing event should be excluded, not crash the batch"
    assert "2" not in result
    # 6 events @ 0.4s each, fully sequential would take ~2.4s+; bounded
    # concurrency (_ENRICH_CONCURRENCY, currently 3) should take ~2 batches.
    assert elapsed < 1.5, (
        f"enrichment took {elapsed:.2f}s — looks sequential again, "
        f"not running at concurrency={se._ENRICH_CONCURRENCY}"
    )
