"""
scripts/verify_sources.py - live health check for every data source.

Run before deploying or merging source changes:

    cd backend && python -m scripts.verify_sources          # all sources
    python -m scripts.verify_sources --required-only        # CI gate mode

For each source it performs a real request and validates the response
SHAPE (status, content type, expected markers), not just reachability.
Candidate sources (AUMA, WikiCFP) are probed too, so you can see from
an unrestricted network whether they're worth building connectors for.

Exit code: 0 when all REQUIRED sources pass, 1 otherwise. Candidates
and key-gated APIs (missing keys) never fail the run.

NOTE: some sandboxes/CI networks block outbound traffic to arbitrary
hosts - a NETWORK-BLOCKED result means this machine couldn't reach the
host, not that the source is broken. Re-run from an open network.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

import httpx

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"}


@dataclass
class Check:
    name:     str
    required: bool
    probe:    Callable[[httpx.AsyncClient], Awaitable[str]]  # returns detail, raises on failure


async def _get(client: httpx.AsyncClient, url: str, **kw) -> httpx.Response:
    resp = await client.get(url, headers=UA, **kw)
    resp.raise_for_status()
    return resp


# ── Source probes: each validates the response SHAPE ────────────────

async def probe_confstech(c: httpx.AsyncClient) -> str:
    from datetime import date
    year = date.today().year
    url = ("https://raw.githubusercontent.com/tech-conferences/"
           f"conference-data/main/conferences/{year}/security.json")
    rows = (await _get(c, url)).json()
    assert isinstance(rows, list) and rows, "expected non-empty JSON list"
    r0 = rows[0]
    for field in ("name", "url", "startDate", "country"):
        assert field in r0, f"missing field {field!r} - format changed?"
    return f"{len(rows)} security conferences, fields OK"


async def probe_eventseye(c: httpx.AsyncClient) -> str:
    resp = await _get(c, "https://www.eventseye.com/fairs/cy1_trade-shows-india.html")
    assert "trade show" in resp.text.lower() or "fairs" in resp.text.lower(), \
        "page markers missing - markup changed?"
    return f"listing page OK ({len(resp.text)} bytes)"


async def probe_10times(c: httpx.AsyncClient) -> str:
    resp = await _get(c, "https://10times.com/india/technology")
    assert "10times" in resp.text.lower(), "page markers missing"
    return f"listing page OK ({len(resp.text)} bytes)"


async def probe_conferencealerts(c: httpx.AsyncClient) -> str:
    resp = await _get(c, "https://conferencealerts.com/country-listing?country=India")
    assert "conference" in resp.text.lower(), "page markers missing"
    return f"listing page OK ({len(resp.text)} bytes)"


async def probe_wikipedia(c: httpx.AsyncClient) -> str:
    url = ("https://en.wikipedia.org/w/api.php?action=query&list=search"
           "&srsearch=trade+fair&srlimit=1&format=json")
    data = (await _get(c, url)).json()
    assert "query" in data, "API shape changed"
    return "REST API OK"


async def probe_serpapi(c: httpx.AsyncClient) -> str:
    key = os.environ.get("SERPAPI_KEY", "")
    if not key:
        return "SKIPPED (SERPAPI_KEY not set)"
    url = f"https://serpapi.com/search.json?engine=google_events&q=tech+conference+india&api_key={key}"
    data = (await _get(c, url)).json()
    assert "events_results" in data or "error" not in data, data.get("error", "no events_results")
    return f"{len(data.get('events_results', []))} events returned"


async def probe_ticketmaster(c: httpx.AsyncClient) -> str:
    key = os.environ.get("TICKETMASTER_KEY", "")
    if not key:
        return "SKIPPED (TICKETMASTER_KEY not set)"
    url = f"https://app.ticketmaster.com/discovery/v2/events.json?size=1&apikey={key}"
    data = (await _get(c, url)).json()
    assert "_embedded" in data or "page" in data, "API shape changed"
    return "Discovery API OK"


async def probe_predicthq(c: httpx.AsyncClient) -> str:
    key = os.environ.get("PREDICTHQ_KEY", "")
    if not key:
        return "SKIPPED (PREDICTHQ_KEY not set)"
    resp = await c.get("https://api.predicthq.com/v1/events/?category=conferences&limit=1",
                       headers={**UA, "Authorization": f"Bearer {key}"})
    resp.raise_for_status()
    assert "results" in resp.json(), "API shape changed"
    return "events API OK"


# ── Candidate sources (no connector yet - reachability + shape recon) ─

async def probe_auma(c: httpx.AsyncClient) -> str:
    resp = await _get(c, "https://www.auma.de/en/trade-fair-search")
    return (f"reachable ({len(resp.text)} bytes) - inspect markup before "
            "building a connector")


async def probe_wikicfp(c: httpx.AsyncClient) -> str:
    resp = await _get(c, "http://www.wikicfp.com/cfp/rss?cat=healthcare")
    assert "<rss" in resp.text[:500] or "<?xml" in resp.text[:200], "not RSS"
    return f"RSS feed OK ({resp.text.count('<item>')} items)"


CHECKS: list[Check] = [
    Check("confs.tech (GitHub raw)",   True,  probe_confstech),
    Check("EventsEye",                 True,  probe_eventseye),
    Check("10times",                   True,  probe_10times),
    Check("ConferenceAlerts",          False, probe_conferencealerts),
    Check("Wikipedia API",             False, probe_wikipedia),
    Check("SerpAPI (key-gated)",       False, probe_serpapi),
    Check("Ticketmaster (key-gated)",  False, probe_ticketmaster),
    Check("PredictHQ (key-gated)",     False, probe_predicthq),
    Check("AUMA [candidate]",          False, probe_auma),
    Check("WikiCFP [candidate]",       False, probe_wikicfp),
]


async def main(required_only: bool = False) -> int:
    failures = 0
    async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
        for chk in CHECKS:
            if required_only and not chk.required:
                continue
            tag = "REQUIRED " if chk.required else "optional "
            try:
                detail = await chk.probe(client)
                status = "SKIP" if detail.startswith("SKIPPED") else "PASS"
                print(f"[{status}] {tag}{chk.name:<28} {detail}")
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ProxyError) as exc:
                print(f"[NETWORK-BLOCKED] {tag}{chk.name:<28} {type(exc).__name__}: "
                      f"host unreachable from this machine - re-run from an open network")
                if chk.required:
                    failures += 1
            except httpx.HTTPStatusError as exc:
                body = exc.response.text[:200].lower()
                if exc.response.status_code == 403 and ("allowlist" in body or "egress" in body):
                    print(f"[NETWORK-BLOCKED] {tag}{chk.name:<28} blocked by egress proxy - "
                          f"re-run from an open network")
                    if chk.required:
                        failures += 1
                else:
                    print(f"[FAIL] {tag}{chk.name:<28} HTTP {exc.response.status_code}")
                    if chk.required:
                        failures += 1
            except Exception as exc:
                print(f"[FAIL] {tag}{chk.name:<28} {type(exc).__name__}: {str(exc)[:120]}")
                if chk.required:
                    failures += 1

    print(f"\n{'ALL REQUIRED SOURCES OK' if failures == 0 else f'{failures} REQUIRED source(s) failing'}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--required-only", action="store_true",
                    help="only run required sources (CI gate mode)")
    args = ap.parse_args()
    sys.exit(asyncio.run(main(required_only=args.required_only)))
