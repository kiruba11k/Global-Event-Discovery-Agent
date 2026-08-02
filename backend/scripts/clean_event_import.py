"""
scripts/clean_event_import.py

One-time cleanup for a merged events CSV before it's loaded into the
`events` table (EventORM). Fixes the concrete problems found in the
17,338-row merged export:

  1. Duplicate rows (same name + start_date) — dropped, first kept.
  2. est_attendees / exhibitor_count full of junk text ("Not publicly
     disclosed for this edition", "500+ industry leaders", ...) instead
     of a plain integer — extracts the first number found, else blank.
     A non-numeric value stored as-is would fail an Integer column insert
     (or silently become garbage), so this MUST run before import.
  3. Stray U+FFFD replacement characters (encoding damage that happened
     upstream, before this file existed — not recoverable, just noise)
     stripped from name/description.
  4. `category` derived from name/description via keyword rules — the
     source data has no category column at all, and scorer.py's Event
     Type dimension (10% weight) currently scores 0 for every row
     without one.
  5. `Relevant_Keywords` (only ~16% populated, and not an EventORM
     column) folded into `industry_tags` instead of dropped — it adds
     real signal for the rows that have it and costs nothing where
     empty, using an existing column the scorer/embedder already read
     rather than inventing a new schema field for a sparsely-populated
     column.
  6. `city` repaired from `event_cities` (format "City, ST (Country)"
     or "City (Country)") for rows (~14.6% of the catalog) where the
     raw `city` column was already corrupted upstream — truncated at a
     multi-byte UTF-8 boundary ("Angoulme (France)" -> city "me"), a
     bare US state abbreviation ("Chicago, IL (USA)" -> city "IL"), or
     a stray description fragment. This corruption predates this
     script; `event_cities` still carries the intact value in almost
     every case, so it's used to rebuild `city` rather than trying to
     repair the truncated string itself. Left untouched when
     `event_cities` is blank (nothing to rebuild from) or its parsed
     city is empty.

No existing EventORM columns are renamed or removed — every field in
the model (venue_name, ticket_price_usd, sponsors, etc.) is still
actively read by scoring, the API response builder, or the frontend
for OTHER ingestion sources (Ticketmaster/Eventbrite/PredictHQ, the
EventsEye scraper, seed data). This script only populates the columns
your CSV actually has data for; everything else stays at its normal
empty default, exactly like it already does for every other sparse
source EventORM ingests.

Usage:
    python scripts/clean_event_import.py input.csv output.csv
"""
from __future__ import annotations

import re
import sys

import pandas as pd

# Keyword -> category. Checked in order; first match wins. Matches
# against "name description" lowercased, so word choice matters more
# than position.
CATEGORY_RULES: list[tuple[str, str]] = [
    (r"\bconference\b", "conference"),
    (r"\bsummit\b", "summit"),
    (r"\bcongress\b", "conference"),
    (r"\bforum\b", "conference"),
    (r"\bsymposium\b", "conference"),
    (r"\bexpo\b", "trade show"),
    (r"\bexhibition\b", "trade show"),
    (r"\btrade show\b", "trade show"),
    (r"\bfair\b", "trade show"),
    (r"\bshow\b", "trade show"),
    (r"\bconvention\b", "trade show"),
    (r"\bfestival\b", "festival"),
    (r"\bworkshop\b", "workshop"),
]

# First integer-looking token in a free-text attendee/exhibitor value,
# e.g. "500+ industry leaders" -> 500, "3,000" -> 3000,
# "10,000 expected" -> 10000, "Not publicly disclosed..." -> None.
_NUMBER_RE = re.compile(r"([\d,]+)")


def extract_number(value: str) -> int | None:
    if not value or not isinstance(value, str):
        return None
    m = _NUMBER_RE.search(value)
    if not m:
        return None
    digits = m.group(1).replace(",", "")
    if not digits.isdigit():
        return None
    return int(digits)


def derive_category(name: str, description: str) -> str:
    text = f"{name or ''} {description or ''}".lower()
    for pattern, category in CATEGORY_RULES:
        if re.search(pattern, text):
            return category
    return ""


def strip_replacement_chars(value: str) -> str:
    if not isinstance(value, str):
        return value
    # U+FFFD noise from upstream lossy encoding, already unrecoverable —
    # just remove it rather than leave a visible "?" glyph in output.
    return value.replace("�", "").strip()


def derive_city(event_cities: str) -> str:
    """Pull the city out of an "City, ST (Country)" / "City (Country)"
    value. Used to rebuild `city` where it was corrupted upstream."""
    if not event_cities or not isinstance(event_cities, str):
        return ""
    city = event_cities.split("(")[0].split(",")[0].strip()
    return strip_replacement_chars(city)


def clean(input_path: str, output_path: str) -> None:
    df = pd.read_csv(input_path, dtype=str, keep_default_na=False)

    before = len(df)
    df["name"] = df["name"].map(strip_replacement_chars)
    df["description"] = df["description"].map(strip_replacement_chars)

    # Dedupe: same name + start_date is the same event listed twice.
    df = df.drop_duplicates(subset=["name", "start_date"], keep="first")
    deduped = before - len(df)

    fixed_city = df["event_cities"].map(derive_city)
    repaired = (fixed_city != "") & (fixed_city != df["city"])
    df.loc[repaired, "city"] = fixed_city[repaired]
    city_repairs = int(repaired.sum())

    df["est_attendees"] = df["est_attendees"].map(extract_number)
    df["exhibitor_count"] = df["exhibitor_count"].map(extract_number)
    numeric_attendees = df["est_attendees"].notna().sum()

    df["category"] = df.apply(
        lambda r: derive_category(r["name"], r["description"]), axis=1
    )
    categorized = (df["category"] != "").sum()

    if "Relevant_Keywords" in df.columns:
        kw = df["Relevant_Keywords"].fillna("")
        df["industry_tags"] = [
            " | ".join(p for p in (ind, k.replace(";", " |")) if p)
            for ind, k in zip(df["related_industries"], kw)
        ]
        df = df.drop(columns=["Relevant_Keywords"])
    else:
        df["industry_tags"] = df["related_industries"]

    df.to_csv(output_path, index=False)

    print(f"rows in:            {before}")
    print(f"duplicates dropped: {deduped}")
    print(f"rows out:           {len(df)}")
    print(f"city values repaired from event_cities: {city_repairs} ({city_repairs/len(df)*100:.1f}%)")
    print(f"real numeric est_attendees: {numeric_attendees} ({numeric_attendees/len(df)*100:.1f}%)")
    print(f"category derived for:      {categorized} ({categorized/len(df)*100:.1f}%)")
    print(f"written to: {output_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python scripts/clean_event_import.py input.csv output.csv")
        sys.exit(1)
    clean(sys.argv[1], sys.argv[2])
