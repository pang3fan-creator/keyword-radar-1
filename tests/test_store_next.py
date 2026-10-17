"""The memory after the M1 cutover: terms, term_signals and reviews instead of leads.

The six functions keep their signatures, so review.py and the MCP server do not change; only
what they read and write moves. A term is stored once, its evidence once per signal, and a
verdict becomes a 14-day review.
"""
import json
from datetime import date

from radar import store

DAY = date(2026, 10, 17)


def _lead(term, kinds, **more):
    return {"term": term, "kinds": list(kinds), "signals": [f"note {term} {k}" for k in kinds], **more}


def test_record_writes_a_term_and_one_signal_row_per_kind(tmp_path):
    conn = store.connect(tmp_path)
    store.record(conn, [_lead("hy memory", ["hf", "x"], named=0.9, variants=["hy-memory-30b"])], DAY)

    canonical, first, last, score, window, aliases = conn.execute(
        "SELECT canonical, first_seen, last_seen, name_score, window, aliases FROM terms").fetchone()
    assert (canonical, first, last, score, window) == ("hy memory", "2026-10-17", "2026-10-17", 0.9, "fast")
    assert json.loads(aliases) == ["hy memory", "hy-memory-30b"]
    signals = conn.execute("SELECT source, evidence FROM term_signals ORDER BY source").fetchall()
    assert signals == [("hf", "note hy memory hf"), ("x", "note hy memory x")]


def test_a_second_run_keeps_first_seen_and_extends_the_aliases(tmp_path):
    conn = store.connect(tmp_path)
    store.record(conn, [_lead("figcraft", ["breakout"])], date(2026, 10, 15))
    store.record(conn, [_lead("figcraft", ["x"], named=0.95, variants=["figcraft-ai"])], DAY)

    first, last, score, aliases = conn.execute(
        "SELECT first_seen, last_seen, name_score, aliases FROM terms").fetchone()
    assert (first, last, score) == ("2026-10-15", "2026-10-17", 0.95)
    assert json.loads(aliases) == ["figcraft", "figcraft-ai"]
    assert conn.execute("SELECT count(*) FROM term_signals").fetchone()[0] == 2


def test_due_skips_terms_already_reviewed_or_too_young(tmp_path):
    conn = store.connect(tmp_path)
    store.record(conn, [_lead("old", ["x"])], date(2026, 9, 25))
    store.record(conn, [_lead("young", ["hf"])], date(2026, 10, 8))

    assert [(t, d.isoformat()) for t, d, _ in store.due(conn, DAY, 14, 5)] == [("old", "2026-09-25")]
    store.save_verdict(conn, "old", "hit", 2, {"k": 1}, DAY)
    assert store.due(conn, DAY, 14, 5) == []


def test_save_verdict_writes_a_14_day_review_and_keeps_the_verdict(tmp_path):
    conn = store.connect(tmp_path)
    store.record(conn, [_lead("strata", ["x"])], date(2026, 9, 25))
    conn.execute("UPDATE terms SET name_score = 0.8")

    store.save_verdict(conn, "strata", "hit", 3, {"k": 0.4}, date(2026, 10, 9))

    days, checked, rise, lead, metrics = conn.execute(
        "SELECT days, checked_at, search_rise, lead_days, metrics FROM reviews").fetchone()
    assert (days, checked, rise, lead) == (14, "2026-10-09", 1, 3)
    assert json.loads(metrics) == {"k": 0.4, "verdict": "hit"}
    assert conn.execute("SELECT status FROM terms").fetchone()[0] == "watching"


def test_summary_counts_each_signal_once_per_term(tmp_path):
    conn = store.connect(tmp_path)
    store.record(conn, [_lead("a", ["x", "hf"]), _lead("b", ["x"])], date(2026, 9, 25))
    store.save_verdict(conn, "a", "hit", 2, {}, date(2026, 10, 9))
    store.save_verdict(conn, "b", "miss", None, {}, date(2026, 10, 9))

    summ = store.summary(conn, DAY)

    assert summ["by_signal"]["x"] == {"checked": 2, "hit": 1, "median_lead": 2}
    assert summ["by_signal"]["hf"] == {"checked": 1, "hit": 1, "median_lead": 2}
    assert summ["pending"] == 0


def test_leads_reads_the_new_tables(tmp_path):
    conn = store.connect(tmp_path)
    store.record(conn, [_lead("hy memory", ["hf", "x"], named=0.9)], DAY)
    store.save_verdict(conn, "hy memory", "hit", 4, {}, DAY)

    got = store.leads(conn, days=7, today=DAY)

    assert got == [{"term": "hy memory", "first_seen": "2026-10-17", "last_seen": "2026-10-17",
                    "signals": ["hf", "x"], "note": "note hy memory x", "name_score": 0.9,
                    "variants": ["hy memory"], "verdict": "hit", "days_ahead": 4, "new": True}]


def test_recent_sources_are_only_x_and_hf(tmp_path):
    conn = store.connect(tmp_path)
    store.record(conn, [_lead("qwen3.9", ["x"], named=0.9), _lead("strata", ["breakout"])], DAY)

    assert [r["term"] for r in store.recent_sources(conn, DAY)] == ["qwen3.9"]


def test_a_new_spelling_updates_the_term_already_stored(tmp_path):
    conn = store.connect(tmp_path)
    conn.execute("INSERT INTO terms (canonical, first_seen, last_seen, aliases)"
                 " VALUES ('deepseek-v4.1-flash-1017', '2026-10-16', '2026-10-16', '[]')")
    conn.commit()

    store.record(conn, [_lead("deepseek v4.1 flash 1017", ["x"])], DAY)

    assert conn.execute("SELECT count(*) FROM terms").fetchone()[0] == 1
    first, last, aliases = conn.execute("SELECT first_seen, last_seen, aliases FROM terms").fetchone()
    assert (first, last) == ("2026-10-16", "2026-10-17")
    assert json.loads(aliases) == ["deepseek v4.1 flash 1017"]
