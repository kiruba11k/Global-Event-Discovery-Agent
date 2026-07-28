"""
relevance/geo_aliases.py — country name/abbreviation equivalence.

DB event.country values and ICP-form geo input use inconsistent forms of
the same country ("USA" vs "United States" vs "US"), so a literal
word-match on whatever spelling the form happened to send can miss events
stored under a different spelling of the exact same country. This showed
up as the ICP form reporting "United States: no matching events" right
after its own "switch to a nearby hub" suggestion offered "USA: 32" —
same country, two spellings, only one of which matched the DB.

Every geo-matching call site (search scoring in relevance/scorer.py,
geo-hint counts and neighbour suggestions in api/routes_events.py) should
expand a typed geo through this table before comparing it against DB
text, not just split it into words.
"""
from __future__ import annotations

_ALIAS_GROUPS: list[list[str]] = [
    ["united states", "usa", "us", "united states of america", "america"],
    ["united kingdom", "uk", "great britain", "britain"],
    ["united arab emirates", "uae"],
    ["south korea", "korea", "republic of korea"],
    ["north korea", "dprk"],
    ["russia", "russian federation"],
    ["czech republic", "czechia", "czech"],
    ["ivory coast", "cote d'ivoire", "côte d'ivoire"],
    ["vietnam", "viet nam"],
    ["saudi arabia", "ksa"],
    ["hong kong", "hong kong sar"],
    ["taiwan", "chinese taipei"],
    ["netherlands", "holland"],
    ["myanmar", "burma"],
    ["ireland", "republic of ireland", "eire"],
    ["new zealand", "nz"],
    ["south africa", "rsa"],
    ["dominican republic", "dominican rep"],
]

_ALIAS_LOOKUP: dict[str, list[str]] = {}
for _group in _ALIAS_GROUPS:
    for _term in _group:
        _ALIAS_LOOKUP[_term] = _group


def expand_geo(geo: str) -> list[str]:
    """Return [geo] plus any known alias spellings of the same place
    (lowercase, deduplicated, order-preserving). Unknown geos pass
    through unchanged as a single-item list."""
    g = (geo or "").strip().lower()
    if not g:
        return []
    group = _ALIAS_LOOKUP.get(g)
    if group:
        return list(dict.fromkeys([g, *group]))
    return [g]


def canonical_geo(geo: str) -> str:
    """Return the canonical (lowercase) grouping key for a geo string -
    the alias group's first/representative entry, so "usa", "america",
    and "united states of america" all collapse to the same key
    ("united states") for deduplication purposes (e.g. building a
    geography picklist from raw DB values without repeating every
    spelling of the same country).

    Handles compound DB values like "UK - United Kingdom" (checks each
    " - " separated part against the alias table; falls back to the
    last part - typically the fuller/official name - if none match).
    Unrecognised geos fall back to their own lowercased, trimmed text.
    """
    g = (geo or "").strip().lower()
    if not g:
        return ""
    if g in _ALIAS_LOOKUP:
        return _ALIAS_LOOKUP[g][0]
    parts = [p.strip() for p in g.split(" - ") if p.strip()]
    for part in parts:
        if part in _ALIAS_LOOKUP:
            return _ALIAS_LOOKUP[part][0]
    return parts[-1] if parts else g


def display_geo(geo: str) -> str:
    """Title-cased display label for a geo string's canonical form -
    "USA"/"America"/"United States of America" all display as "United
    States". Unrecognised geos are title-cased as-is."""
    return canonical_geo(geo).title()
