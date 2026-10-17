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
    assert json.loads(aliases) == ["deepseek v4.1 flash 1017", "deepseek-v4.1-flash-1017"]


def test_a_twin_already_in_memory_is_folded_into_one_term(tmp_path):
    conn = store.connect(tmp_path)
    for term in ("mirelo sfx", "mirelo sfx 2.0"):
        conn.execute("INSERT INTO terms (canonical, first_seen, last_seen, aliases)"
                     " VALUES (?,?,?,'[]')", (term, "2026-10-15", "2026-10-15"))
    conn.commit()

    store.record(conn, [_lead("mirelo sfx 2.0", ["x"])], DAY)

    assert conn.execute("SELECT count(*) FROM terms").fetchone()[0] == 1
    canonical, first, aliases = conn.execute("SELECT canonical, first_seen, aliases FROM terms").fetchone()
    assert (canonical, first) == ("mirelo sfx 2.0", "2026-10-15")   # docs/05 §4.2 example
    assert json.loads(aliases) == ["mirelo sfx", "mirelo sfx 2.0"]


def test_merging_terms_moves_signals_and_reviews_and_keeps_one_row_per_source(tmp_path):
    conn = store.connect(tmp_path)
    a = conn.execute("INSERT INTO terms (canonical, first_seen, last_seen) VALUES ('spark open','2026-10-15','2026-10-15')").lastrowid
    b = conn.execute("INSERT INTO terms (canonical, first_seen, last_seen) VALUES ('muse spark open','2026-10-16','2026-10-16')").lastrowid
    for term, source in ((a, "x"), (b, "x"), (b, "hf")):
        conn.execute("INSERT INTO term_signals (term_id, source, first_seen) VALUES (?,?,?)", (term, source, "2026-10-16"))
    conn.execute("INSERT INTO reviews (term_id, days, checked_at) VALUES (?,14,'2026-10-17')", (b,))
    conn.commit()

    store.merge_terms(conn, a, b)

    assert conn.execute("SELECT count(*) FROM terms").fetchone()[0] == 1
    assert [r[0] for r in conn.execute("SELECT source FROM term_signals ORDER BY source")] == ["hf", "x"]
    assert conn.execute("SELECT term_id FROM reviews").fetchone()[0] == a
    assert json.loads(conn.execute("SELECT aliases FROM terms").fetchone()[0]) == ["muse spark open", "spark open"]
    assert conn.execute("SELECT last_seen FROM terms").fetchone()[0] == "2026-10-16"


def test_a_url_echo_is_kept_but_never_scheduled_for_a_review(tmp_path):
    conn = store.connect(tmp_path)
    store.record(conn, [_lead("bitbucket", ["sitemap"]), _lead("figcraft", ["breakout"])], date(2026, 9, 25))

    assert conn.execute("SELECT status FROM terms WHERE canonical='bitbucket'").fetchone()[0] == "echo"
    assert [t for t, _, _ in store.due(conn, DAY, 14, 5)] == ["figcraft"]


def test_record_run_keeps_the_days_cost_and_stats(tmp_path):
    conn = store.connect(tmp_path)

    store.record_run(conn, "daily", "2026-10-17T20:53:08", "2026-10-17T20:59:29", 150000,
                     {"leads": 20, "terms": 19}, ["toolify: no URLs read"])

    command, started, finished, cost, stats, errors = conn.execute(
        "SELECT command, started_at, finished_at, cost_micros, stats, errors FROM runs").fetchone()
    assert (command, started, finished, cost) == ("daily", "2026-10-17T20:53:08", "2026-10-17T20:59:29", 150000)
    assert json.loads(stats) == {"leads": 20, "terms": 19}
    assert json.loads(errors) == ["toolify: no URLs read"]


def test_twins_are_found_with_the_earlier_row_kept(tmp_path):
    conn = store.connect(tmp_path)
    late = conn.execute("INSERT INTO terms (canonical, first_seen, last_seen) VALUES ('mirelo sfx 2.0','2026-10-17','2026-10-17')").lastrowid
    early = conn.execute("INSERT INTO terms (canonical, first_seen, last_seen) VALUES ('mirelo sfx','2026-10-15','2026-10-15')").lastrowid

    assert store.twins(conn) == [(early, late)]


def test_a_later_echo_does_not_demote_a_name_a_real_signal_found(tmp_path):
    conn = store.connect(tmp_path)
    store.record(conn, [_lead("mirelo sfx 2.0", ["x"], named=0.9)], date(2026, 10, 15))

    store.record(conn, [_lead("mirelo sfx 2.0", ["sitemap"])], date(2026, 10, 16))

    assert conn.execute("SELECT status FROM terms").fetchone()[0] == "new"
    assert [t for t, _, _ in store.due(conn, date(2026, 11, 1), 14, 5)] == ["mirelo sfx 2.0"]


def test_pending_does_not_count_echoes(tmp_path):
    conn = store.connect(tmp_path)
    store.record(conn, [_lead("bitbucket", ["sitemap"]), _lead("figcraft", ["breakout"])], DAY)

    assert store.summary(conn, DAY)["pending"] == 1


def test_a_term_with_no_signal_is_not_an_echo(tmp_path):
    conn = store.connect(tmp_path)
    store.record(conn, [{"term": "mystery", "kinds": [], "signals": []}], DAY)

    assert conn.execute("SELECT status FROM terms").fetchone()[0] == "new"


def test_merging_keeps_one_review_per_window_and_the_newer_one_wins(tmp_path):
    conn = store.connect(tmp_path)
    a = conn.execute("INSERT INTO terms (canonical, first_seen, last_seen) VALUES ('spark open','2026-10-15','2026-10-15')").lastrowid
    b = conn.execute("INSERT INTO terms (canonical, first_seen, last_seen) VALUES ('muse spark open','2026-10-16','2026-10-16')").lastrowid
    conn.execute("INSERT INTO reviews (term_id, days, checked_at, search_rise, lead_days, metrics)"
                 " VALUES (?,14,'2026-10-17',1,2,'{\"verdict\":\"hit\"}')", (a,))
    conn.execute("INSERT INTO reviews (term_id, days, checked_at, search_rise, lead_days, metrics)"
                 " VALUES (?,14,'2026-10-18',0,NULL,'{\"verdict\":\"miss\"}')", (b,))
    conn.commit()

    store.merge_terms(conn, a, b)

    rows = conn.execute("SELECT term_id, days, checked_at, search_rise, lead_days, metrics FROM reviews").fetchall()
    assert len(rows) == 1 and rows[0][0] == a
    assert rows[0][2:] == ("2026-10-18", 0, None, '{"verdict":"miss"}')   # newer row wins whole
