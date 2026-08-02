"""
Regression tests for scripts/clean_event_import.py's city repair.

Guards against the production bug where the raw source CSV had `city`
values corrupted upstream (truncated at a multi-byte UTF-8 boundary,
e.g. "Angoulme" -> "me"; or a bare US state abbreviation, e.g.
"Chicago, IL (USA)" -> "IL") while `event_cities` still held the intact
value - so `city` must be rebuilt from `event_cities`, not trusted as-is.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from clean_event_import import derive_city  # noqa: E402


def test_derive_city_from_city_state_country():
    assert derive_city("Chicago, IL (USA)") == "Chicago"


def test_derive_city_from_city_country_no_state():
    assert derive_city("Dusseldorf (Germany)") == "Dusseldorf"


def test_derive_city_strips_replacement_char():
    assert derive_city("Angoul�me (France)") == "Angoul�me".replace("�", "")


def test_derive_city_handles_blank():
    assert derive_city("") == ""
    assert derive_city(None) == ""
