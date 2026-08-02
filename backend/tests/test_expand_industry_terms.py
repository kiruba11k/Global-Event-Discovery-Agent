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
