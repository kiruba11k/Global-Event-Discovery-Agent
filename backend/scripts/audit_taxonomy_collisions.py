"""
scripts/audit_taxonomy_collisions.py — data-driven detector for the
"hospital"/"Hospitality" class of bug across the WHOLE industry taxonomy,
not just the one word a user happened to report.

Background: relevance/scorer.py and db/crud.py each keep a taxonomy of
(profile industry -> EventsEye synonym list). Synonyms longer than 4
chars are matched as a STEM anchored only at the start of a word
("manufactur" -> "manufacturing"), by design, so multi-word-form event
tags still match. The unavoidable cost: any synonym that happens to be a
complete English word AND a literal prefix of a different, unrelated
word ("hospital" / "Hospitality") silently matches every event tagged
with that unrelated word too.

There is no purely algorithmic fix for this (a generic stemmer collapses
"hospital"/"hospitality" to the same stem too - verified against
Snowball/Porter - and would also SEVER legitimate matches this taxonomy
depends on, like "pharma"/"pharmaceutical", which don't share a stem
under those algorithms). The dynamic, non-hardcoded part is THIS SCRIPT:
instead of a human eyeballing complaints one word at a time, it re-scans
the taxonomy against real catalog data on demand and flags every synonym
that's currently causing this exact failure mode, ranked by blast
radius, with a corroboration check to avoid flagging intentional/safe
stems.

Usage:
    python scripts/audit_taxonomy_collisions.py path/to/events_dump.sql
    python scripts/audit_taxonomy_collisions.py --live   # query configured DATABASE_URL

Output: a ranked list of (synonym, group, false-positive tag count) for
synonyms that should be added to relevance/scorer.py's _NO_STEM_SYNONYMS
and db/crud.py's _ILIKE_UNSAFE_TERMS. Re-run this whenever the catalog
grows or the taxonomy changes — a synonym that's safe today can start
colliding once a new event source/tag vocabulary is ingested.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _load_tag_phrases_from_sql_dump(path: str) -> set[str]:
    """Extract every distinct '|'-separated industry_tags fragment from a
    raw SQL INSERT dump, using an in-memory sqlite DB (same loader as the
    ORM would use, so we exercise the real columns) - no live DB needed."""
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker
    from models.event import Base, EventORM

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    conn = engine.raw_connection()
    cur = conn.cursor()
    cur.executescript(Path(path).read_text(encoding="utf-8"))
    conn.commit()
    conn.close()

    Session = sessionmaker(bind=engine)
    db = Session()
    phrases: set[str] = set()
    for (tags,) in db.execute(select(EventORM.industry_tags)).all():
        if not tags:
            continue
        for part in tags.split("|"):
            p = part.strip()
            if p:
                phrases.add(p)
    for (tags,) in db.execute(select(EventORM.related_industries)).all():
        if not tags:
            continue
        for part in tags.split("|"):
            p = part.strip()
            if p:
                phrases.add(p)
    return phrases


async def _load_tag_phrases_from_live_db() -> set[str]:
    from sqlalchemy import select
    from db.database import async_session
    from models.event import EventORM

    phrases: set[str] = set()
    async with async_session() as db:
        for col in (EventORM.industry_tags, EventORM.related_industries):
            for (tags,) in (await db.execute(select(col))).all():
                if not tags:
                    continue
                for part in tags.split("|"):
                    p = part.strip()
                    if p:
                        phrases.add(p)
    return phrases


def audit(tag_phrases: set[str]) -> list[tuple[str, str, int, list[str]]]:
    """Returns [(synonym, group_key, false_positive_count, example_phrases)],
    sorted by false_positive_count descending. Only synonyms >4 chars are
    checked - shorter ones already require a full word match everywhere."""
    from relevance.scorer import _PROFILE_TO_EVENTSEYE, _syn_in_text, _LIMITED_STEM_SYNONYMS

    results = []
    for group_key, synonyms in _PROFILE_TO_EVENTSEYE.items():
        group_syns = set(synonyms) | {group_key}
        for syn in synonyms:
            syn_l = syn.strip().lower()
            if len(syn_l) <= 4 or syn_l in _LIMITED_STEM_SYNONYMS:
                continue
            bad_phrases = []
            for phrase in tag_phrases:
                pl = phrase.lower()
                m = re.search(r"\b" + re.escape(syn_l), pl)
                if not m:
                    continue
                end = m.end()
                if end < len(pl) and pl[end].isalpha():
                    # Mid-word continuation - the risky case. Corroborated
                    # (safe) if ANOTHER synonym from the same group also
                    # appears as a genuine whole word in this same phrase -
                    # a real match for this industry wouldn't rely on the
                    # risky stem alone.
                    corroborated = any(
                        other != syn_l and _syn_in_text(other, phrase)
                        for other in group_syns
                    )
                    if not corroborated:
                        bad_phrases.append(phrase)
            if bad_phrases:
                results.append((syn_l, group_key, len(bad_phrases), bad_phrases[:3]))

    results.sort(key=lambda r: -r[2])
    return results


if __name__ == "__main__":
    import asyncio

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    if sys.argv[1] == "--live":
        phrases = asyncio.run(_load_tag_phrases_from_live_db())
    else:
        phrases = _load_tag_phrases_from_sql_dump(sys.argv[1])

    print(f"Scanning {len(phrases)} distinct tag phrases against the taxonomy...\n")
    print(
        "NOTE: this is a CANDIDATE list, not a ready-to-apply patch. The\n"
        "corroboration check catches the shape of the bug (a stem matching\n"
        "an unrelated word with no other support), but most of what's\n"
        "surfaced below is a legitimate, INTENTIONAL stem match (e.g.\n"
        "'technolog' -> 'Technologies' is correct, not a bug) that just\n"
        "happens to have only one relevant tag on that particular event.\n"
        "Distinguishing 'stem of the same word' from 'prefix of a different\n"
        "word' requires actual dictionary/semantic knowledge this script\n"
        "doesn't have - read the example phrases for each entry and use\n"
        "judgment before adding anything to _LIMITED_STEM_SYNONYMS. Look\n"
        "for entries whose examples are consistently about a DIFFERENT\n"
        "topic than the group name, not just a different word form of it.\n"
    )
    flagged = audit(phrases)
    if not flagged:
        print("No uncorroborated stem collisions found.")
    for syn, group, count, examples in flagged:
        print(f"{syn!r:20s} (group={group!r:15s}) -> {count:4d} candidate hits, e.g. {examples}")
