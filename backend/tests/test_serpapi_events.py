from ingestion.icp_query_builder import SerpAPIQuery
from ingestion.serpapi_events import _build_google_events_params, _redact_api_key_from_error


def test_google_events_params_put_event_location_in_query_not_location_param():
    params = _build_google_events_params(
        SerpAPIQuery(q="AI conference 2026", location="New York USA", year="2026")
    )

    assert params == {
        "engine": "google_events",
        "q": "AI conference 2026 in New York USA",
        "hl": "en",
        "gl": "us",
    }
    assert "location" not in params


def test_google_events_params_does_not_duplicate_existing_location():
    params = _build_google_events_params(
        SerpAPIQuery(q="AI conference 2026 in New York USA", location="New York USA", year="2026")
    )

    assert params["q"] == "AI conference 2026 in New York USA"
    assert "location" not in params


def test_google_events_params_sets_country_gl_from_location():
    params = _build_google_events_params(
        SerpAPIQuery(q="fintech summit 2026", location="London UK", year="2026")
    )

    assert params["q"] == "fintech summit 2026 in London UK"
    assert params["gl"] == "uk"


def test_serpapi_error_redaction_masks_api_key_in_url():
    exc = RuntimeError(
        "400 Client Error: Bad Request for url: "
        "https://serpapi.com/search?engine=google_events&q=x&api_key=secret123&hl=en"
    )

    message = _redact_api_key_from_error(exc)

    assert "secret123" not in message
    assert "api_key=%2A%2A%2A" in message or "api_key=***" in message
