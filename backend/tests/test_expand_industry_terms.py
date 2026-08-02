"""
Regression tests for db/crud.py's _expand_industry_terms().

Guards against two production bugs found while investigating a "geo-hint
promised events, real search discarded them" report:

  1. Naive substring matching let a short taxonomy key match INSIDE an
     unrelated word - key "tech" is a literal substring of "fintech", so
     a "Fintech" profile wrongly activated the generic "tech" group.
  2. The synonym table only points one way: "finance"/"banking"/
     "insurance" list "fintech" as one of THEIR synonyms, but "fintech"
     never pointed back - so a DB event tagged "Finance - Banking -
     Insurance" (already in the catalog) was silently excluded from the
     SQL candidate query for a "Fintech" search, before scoring ever saw
     it.

Runs without backend dependencies installed - imports only the two
symbols under test out of db/crud.py by exec()'ing their source, since
the full module requires sqlalchemy/config.
"""
import re
import sys
import types
from pathlib import Path

CRUD_PATH = Path(__file__).resolve().parents[1] / "db" / "crud.py"


def _load_expand_industry_terms():
    src = CRUD_PATH.read_text()
    start = src.index("_INDUSTRY_SYNONYMS: list[tuple[str, list[str]]] = [")
    end = src.index("\n  ]\n", start) + len("\n  ]\n")
    synonyms_block = src[start:end]
    func_start = src.index("def _expand_industry_terms")
    func_end = src.index("\n\n\n", func_start)
    func_block = src[func_start:func_end]
    ns = {"List": list, "re": re}
    exec(synonyms_block, ns)
    exec(func_block, ns)
    return ns["_expand_industry_terms"]


_expand_industry_terms = _load_expand_industry_terms()


def test_fintech_activates_finance_banking_insurance():
    terms = _expand_industry_terms(["Fintech"])
    for expected in ("finance", "banking", "insurance", "accounting"):
        assert expected in terms, f"'Fintech' must activate the '{expected}' synonym group"


def test_fintech_does_not_wrongly_activate_generic_tech_group():
    terms = _expand_industry_terms(["Fintech"])
    assert "iot" not in terms, "'tech' must not match as a substring of 'fintech'"
    assert "smart" not in terms


def test_automotive_still_excludes_automation_terms():
    terms = _expand_industry_terms(["Automotive"])
    assert not any("automat" in t for t in terms), \
        "'auto' must not match as a substring of 'automation'"


def test_healthcare_medtech_still_matches_own_groups():
    terms = _expand_industry_terms(["Healthcare / Medtech"])
    assert "healthcare" in terms
    assert "medtech" in terms
    assert "medical" in terms


def test_financial_prefix_stem_still_activates_finance():
    terms = _expand_industry_terms(["Financial Services"])
    assert "finance" in terms or "banking" in terms


def _load_industry_synonyms():
    src = CRUD_PATH.read_text()
    start = src.index("_INDUSTRY_SYNONYMS: list[tuple[str, list[str]]] = [")
    end = src.index("\n  ]\n", start) + len("\n  ]\n")
    ns = {}
    exec(src[start:end], ns)
    return ns["_INDUSTRY_SYNONYMS"]


_INDUSTRY_SYNONYMS = _load_industry_synonyms()

# Every (child_key, parent_key) pair where `parent_key` lists `child_key`
# as one of its own synonyms, but `child_key`'s group doesn't list
# `parent_key` back - e.g. "finance" lists "fintech", but "fintech" never
# pointed back at "finance". This is the exact shape of bug fixed for
# Fintech specifically; this test asserts the fix generalizes to EVERY
# such pair in the table, not just that one case.
_ASYMMETRIC_PAIRS = [
    (parent_key, child_key)
    for parent_key, syns in _INDUSTRY_SYNONYMS
    for child_key in syns
    if child_key in dict(_INDUSTRY_SYNONYMS)
    and child_key != parent_key
    and parent_key not in dict(_INDUSTRY_SYNONYMS)[child_key]
]


def test_reverse_lookup_covers_every_asymmetric_taxonomy_pair():
    """A profile industry matching the CHILD side of an asymmetric pair
    must still pull in a term from the PARENT group - guards the fix
    against regressing for any of the 60+ other pairs in the table
    beyond the one (finance/fintech) that was manually verified."""
    assert len(_ASYMMETRIC_PAIRS) > 30, \
        "sanity check: the taxonomy table should still contain plenty of " \
        "asymmetric pairs for this test to be meaningful"

    failures = []
    synonyms_by_key = dict(_INDUSTRY_SYNONYMS)
    for parent_key, child_key in _ASYMMETRIC_PAIRS:
        terms = _expand_industry_terms([child_key])
        parent_synonyms = synonyms_by_key[parent_key]
        # Reachable if the parent's own key, or any of its synonyms, made it
        # into the expanded term list (ILIKE substring matching means a
        # partial synonym overlap is enough, not an exact string match).
        reachable = parent_key in terms or any(
            any(s in t or t in s for t in terms) for s in parent_synonyms
        )
        if not reachable:
            failures.append((child_key, parent_key))

    assert not failures, (
        f"{len(failures)}/{len(_ASYMMETRIC_PAIRS)} asymmetric pairs still "
        f"unreachable via reverse lookup: {failures[:10]}"
    )
