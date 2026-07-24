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
