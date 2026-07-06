"""
geo_normaliser.py — canonical country + source-platform normalization.

The events table aggregates a dozen scrapers and APIs which each write
`country` in their own dialect: full names ("Germany"), ISO alpha-2
codes ("DE", from PredictHQ), aliases ("USA", "U.K.", "Holland"),
"City, Country" strings, or junk ("Online", "TBA", a venue name).
Counting DISTINCT on that column claimed 416 countries — more than
exist on Earth.

This module maps any raw value onto a canonical country name (or None
when the value is not recognisably a country), and collapses noisy
source_platform labels ("europe 2026 - eventseye") onto their connector
family ("EventsEye"). Used by /api/stats so the homepage figures are
honest, and available to ingestion for write-time cleaning.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

# ── Canonical country names (UN members + common event destinations) ──
CANONICAL_COUNTRIES: set[str] = {
    "Afghanistan", "Albania", "Algeria", "Andorra", "Angola", "Argentina",
    "Armenia", "Australia", "Austria", "Azerbaijan", "Bahamas", "Bahrain",
    "Bangladesh", "Barbados", "Belarus", "Belgium", "Belize", "Benin",
    "Bhutan", "Bolivia", "Bosnia and Herzegovina", "Botswana", "Brazil",
    "Brunei", "Bulgaria", "Burkina Faso", "Burundi", "Cambodia", "Cameroon",
    "Canada", "Cape Verde", "Chad", "Chile", "China", "Colombia",
    "Costa Rica", "Croatia", "Cuba", "Cyprus", "Czech Republic",
    "Democratic Republic of the Congo", "Denmark", "Djibouti",
    "Dominican Republic", "Ecuador", "Egypt", "El Salvador", "Estonia",
    "Eswatini", "Ethiopia", "Fiji", "Finland", "France", "Gabon", "Gambia",
    "Georgia", "Germany", "Ghana", "Greece", "Guatemala", "Guinea", "Guyana",
    "Haiti", "Honduras", "Hong Kong", "Hungary", "Iceland", "India",
    "Indonesia", "Iran", "Iraq", "Ireland", "Israel", "Italy", "Ivory Coast",
    "Jamaica", "Japan", "Jordan", "Kazakhstan", "Kenya", "Kuwait",
    "Kyrgyzstan", "Laos", "Latvia", "Lebanon", "Lesotho", "Liberia", "Libya",
    "Liechtenstein", "Lithuania", "Luxembourg", "Macau", "Madagascar",
    "Malawi", "Malaysia", "Maldives", "Mali", "Malta", "Mauritania",
    "Mauritius", "Mexico", "Moldova", "Monaco", "Mongolia", "Montenegro",
    "Morocco", "Mozambique", "Myanmar", "Namibia", "Nepal", "Netherlands",
    "New Zealand", "Nicaragua", "Niger", "Nigeria", "North Macedonia",
    "Norway", "Oman", "Pakistan", "Palestine", "Panama", "Papua New Guinea",
    "Paraguay", "Peru", "Philippines", "Poland", "Portugal", "Puerto Rico",
    "Qatar", "Republic of the Congo", "Romania", "Russia", "Rwanda",
    "San Marino", "Saudi Arabia", "Senegal", "Serbia", "Seychelles",
    "Sierra Leone", "Singapore", "Slovakia", "Slovenia", "Somalia",
    "South Africa", "South Korea", "South Sudan", "Spain", "Sri Lanka",
    "Sudan", "Suriname", "Sweden", "Switzerland", "Syria", "Taiwan",
    "Tajikistan", "Tanzania", "Thailand", "Timor-Leste", "Togo",
    "Trinidad and Tobago", "Tunisia", "Turkey", "Turkmenistan", "Uganda",
    "Ukraine", "United Arab Emirates", "United Kingdom", "United States",
    "Uruguay", "Uzbekistan", "Vanuatu", "Venezuela", "Vietnam", "Yemen",
    "Zambia", "Zimbabwe",
}

# lowercase alias / ISO code → canonical
_ALIASES: dict[str, str] = {
    # United States
    "usa": "United States", "us": "United States", "u.s.": "United States",
    "u.s.a.": "United States", "united states of america": "United States",
    "america": "United States", "estados unidos": "United States",
    # United Kingdom
    "uk": "United Kingdom", "u.k.": "United Kingdom", "gb": "United Kingdom",
    "great britain": "United Kingdom", "england": "United Kingdom",
    "scotland": "United Kingdom", "wales": "United Kingdom",
    "northern ireland": "United Kingdom",
    # UAE
    "uae": "United Arab Emirates", "u.a.e.": "United Arab Emirates",
    "ae": "United Arab Emirates", "emirates": "United Arab Emirates",
    "dubai": "United Arab Emirates", "abu dhabi": "United Arab Emirates",
    # common alternates
    "holland": "Netherlands", "the netherlands": "Netherlands",
    "deutschland": "Germany", "españa": "Spain", "italia": "Italy",
    "brasil": "Brazil", "méxico": "Mexico", "türkiye": "Turkey",
    "korea": "South Korea", "republic of korea": "South Korea",
    "korea, republic of": "South Korea",
    "czechia": "Czech Republic", "viet nam": "Vietnam",
    "russian federation": "Russia", "ivory coast": "Ivory Coast",
    "côte d'ivoire": "Ivory Coast", "cote d'ivoire": "Ivory Coast",
    "burma": "Myanmar", "swaziland": "Eswatini", "macedonia": "North Macedonia",
    "hong kong sar": "Hong Kong", "hongkong": "Hong Kong",
    "taiwan, province of china": "Taiwan", "chinese taipei": "Taiwan",
    "peoples republic of china": "China", "prc": "China",
    "saudi": "Saudi Arabia", "ksa": "Saudi Arabia",
    # ISO alpha-2 (PredictHQ writes these) — major event markets
    "af": "Afghanistan", "ar": "Argentina", "at": "Austria", "au": "Australia",
    "bd": "Bangladesh", "be": "Belgium", "bg": "Bulgaria", "bh": "Bahrain",
    "br": "Brazil", "ca": "Canada", "ch": "Switzerland", "cl": "Chile",
    "cn": "China", "co": "Colombia", "cz": "Czech Republic", "de": "Germany",
    "dk": "Denmark", "eg": "Egypt", "es": "Spain", "fi": "Finland",
    "fr": "France", "gr": "Greece", "hk": "Hong Kong", "hr": "Croatia",
    "hu": "Hungary", "id": "Indonesia", "ie": "Ireland", "il": "Israel",
    "in": "India", "it": "Italy", "jp": "Japan", "ke": "Kenya",
    "kr": "South Korea", "kw": "Kuwait", "lk": "Sri Lanka", "lt": "Lithuania",
    "lu": "Luxembourg", "lv": "Latvia", "ma": "Morocco", "mx": "Mexico",
    "my": "Malaysia", "ng": "Nigeria", "nl": "Netherlands", "no": "Norway",
    "np": "Nepal", "nz": "New Zealand", "om": "Oman", "pe": "Peru",
    "ph": "Philippines", "pk": "Pakistan", "pl": "Poland", "pt": "Portugal",
    "qa": "Qatar", "ro": "Romania", "rs": "Serbia", "ru": "Russia",
    "sa": "Saudi Arabia", "se": "Sweden", "sg": "Singapore", "si": "Slovenia",
    "sk": "Slovakia", "th": "Thailand", "tn": "Tunisia", "tr": "Turkey",
    "tw": "Taiwan", "ua": "Ukraine", "uy": "Uruguay", "vn": "Vietnam",
    "za": "South Africa",
    # ISO alpha-3 — most common
    "gbr": "United Kingdom", "deu": "Germany", "fra": "France",
    "ind": "India", "chn": "China", "jpn": "Japan", "sgp": "Singapore",
    "are": "United Arab Emirates", "aus": "Australia", "can": "Canada",
    "nld": "Netherlands", "che": "Switzerland", "esp": "Spain",
    "ita": "Italy", "bra": "Brazil", "mex": "Mexico", "kor": "South Korea",
    "zaf": "South Africa",
}

_CANONICAL_LOWER = {c.lower(): c for c in CANONICAL_COUNTRIES}


def normalise_country(raw: Optional[str]) -> Optional[str]:
    """Map a raw country string to its canonical name, or None if it
    isn't recognisably a country (city, 'Online', venue junk, …)."""
    if not raw:
        return None
    v = re.sub(r"\s+", " ", str(raw)).strip().strip(".,;")
    if not v or len(v) > 60:
        return None
    low = v.lower()

    if low in _CANONICAL_LOWER:
        return _CANONICAL_LOWER[low]
    if low in _ALIASES:
        return _ALIASES[low]

    # "Berlin, Germany" / "New Delhi - India" → try the last segment
    for sep in (",", "-", "|", "/"):
        if sep in v:
            tail = v.rsplit(sep, 1)[-1].strip().lower()
            if tail in _CANONICAL_LOWER:
                return _CANONICAL_LOWER[tail]
            if tail in _ALIASES:
                return _ALIASES[tail]
    return None


def count_countries(values: Iterable[Optional[str]]) -> int:
    """Number of distinct real countries among raw DB values."""
    return len({c for c in (normalise_country(v) for v in values) if c})


# ── Source platform families ───────────────────────────────────────
# Raw source_platform labels are freeform per scraper run
# ("europe 2026 - eventseye", "10times_in", "CSV_UPLOAD"). Collapse
# them onto the connector family so "live data sources" is honest.
_SOURCE_FAMILIES: list[tuple[str, str]] = [
    ("eventseye",        "EventsEye"),
    ("10times",          "10times"),
    ("wikipedia",        "Wikipedia"),
    ("conferencealerts", "Conference Alerts"),
    ("allconferences",   "AllConferences"),
    ("confex",           "Confex"),
    ("techcrunch",       "TechCrunch"),
    ("saceos",           "SACEOS"),
    ("myceb",            "MyCEB"),
    ("mice",             "MICE Directories"),
    ("meetup",           "Meetup"),
    ("luma",             "Luma"),
    ("serpapi",          "SerpAPI"),
    ("google_events",    "SerpAPI"),
    ("ticketmaster",     "Ticketmaster"),
    ("eventbrite",       "Eventbrite"),
    ("predicthq",        "PredictHQ"),
    ("csv",              "CSV Upload"),
    ("seed",             "Curated Seed"),
]


def source_family(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    low = str(raw).lower()
    for needle, family in _SOURCE_FAMILIES:
        if needle in low:
            return family
    return "Other"


def count_source_families(values: Iterable[Optional[str]]) -> int:
    fams = {f for f in (source_family(v) for v in values) if f and f != "Other"}
    return len(fams)
