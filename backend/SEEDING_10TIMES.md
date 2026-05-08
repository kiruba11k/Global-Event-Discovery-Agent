# Seed 10times events on Render without Shell access

Free Render web services do not include an interactive Shell. This backend now exposes a protected API endpoint that runs `backend/scripts/seed_10times_global.py` inside the deployed Render service, so the seed writes to the same database used by the backend.

## 1. Configure the secret token in Render

In the Render dashboard for your backend service, add an environment variable:

```text
SEED_ADMIN_TOKEN=<choose-a-long-random-secret>
```

Redeploy the backend after adding or changing this value.

## 2. Start a safe dry run

From your local Windows PowerShell terminal:

```powershell
$TOKEN="<the same value as SEED_ADMIN_TOKEN>"
curl.exe -X POST "https://global-event-discovery-agent-backend.onrender.com/api/seed-10times?dry_run=true&limit_events=50&max_pages_per_listing=1" -H "X-Seed-Token: $TOKEN"
```

Check progress:

```powershell
curl.exe "https://global-event-discovery-agent-backend.onrender.com/api/seed-10times/status" -H "X-Seed-Token: $TOKEN"
```

If `last_result.parsed_events` is `0`, 10times blocked the crawl from that network or changed the page markup. In that case, a real seed will not add events until the source can be fetched successfully.

## 3. Seed up to about 1,000 events

After the dry run parses events, run the real seed:

```powershell
curl.exe -X POST "https://global-event-discovery-agent-backend.onrender.com/api/seed-10times?limit_events=1000&max_pages_per_listing=10&concurrency=1&delay_seconds=3" -H "X-Seed-Token: $TOKEN"
```

Poll status until `running` is `false`:

```powershell
curl.exe "https://global-event-discovery-agent-backend.onrender.com/api/seed-10times/status" -H "X-Seed-Token: $TOKEN"
```

Then verify the event count and data:

```powershell
curl.exe "https://global-event-discovery-agent-backend.onrender.com/api/stats"
curl.exe "https://global-event-discovery-agent-backend.onrender.com/api/events?page=1&limit=50"
```

## Notes

- The endpoint requires `X-Seed-Token`; without `SEED_ADMIN_TOKEN` configured, it returns `503`.
- Only one 10times seed job can run at a time.
- Defaults are tuned for Render free tier: `limit_events=1000`, `max_pages_per_listing=10`, `concurrency=1`, and `delay_seconds=3`.
- The source website may return `403 Forbidden`. The endpoint makes the run possible without Shell access, but it cannot guarantee 10times will allow scraping from every network.
