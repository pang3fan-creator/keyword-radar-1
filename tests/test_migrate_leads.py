"""The one-off migration from `leads` into terms / term_signals / reviews / runs.

The old table is the source of truth; the migration must copy every row once, keep the
dates and scores it was given, and be safe to re-run after a daily run added new leads.
"""
import json

from radar import migrate, store


def _db(tmp_path):
    return store.connect(tmp_path)


def _lead(conn, term, kinds, first, last=None, notes=(), named=None, variants=(),
          reviewed_at=None, verdict=None, lead_days=None, trends="{}"):
    conn.execute(
        "INSERT INTO leads (term, first_seen, last_seen, signals, notes, named, variants,"
        " reviewed_at, verdict, lead_days, trends) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (term, first, last or first, json.dumps(list(kinds)), json.dumps(list(notes)), named,
         json.dumps(list(variants)), reviewed_at, verdict, lead_days, trends))
    conn.commit()


def test_terms_keep_identity_and_dates(tmp_path):
    conn = _db(tmp_path)
    _lead(conn, "figcraft", ["breakout"], "2026-10-15", "2026-10-17", named=0.9,
          variants=["figcraft", "niko figcraft"])

    stats = migrate.migrate(conn)

    assert stats["terms"] == 1
    row = conn.execute("SELECT canonical, aliases, first_seen, last_seen, name_score, window, status"
                       " FROM terms").fetchone()
    assert row[0] == "figcraft"
    assert json.loads(row[1]) == ["figcraft", "niko figcraft"]
    assert row[2] == "2026-10-15" and row[3] == "2026-10-17"
    assert row[4] == 0.9
    assert row[5] == "fast"
    assert row[6] == "new"


def test_one_signal_row_per_kind_with_the_last_note_as_evidence(tmp_path):
    conn = _db(tmp_path)
    _lead(conn, "hy memory", ["hf", "x"], "2026-10-16",
          notes=["x: @a posted hy memory", "hf: hy/memory weights"])

    stats = migrate.migrate(conn)

    assert stats["signals"] == 2
    rows = conn.execute("SELECT source, first_seen, evidence FROM term_signals ORDER BY source").fetchall()
    assert [r[0] for r in rows] == ["hf", "x"]
    assert rows[0][1] == "2026-10-16"
    assert rows[0][2] == "hf: hy/memory weights"


def test_review_is_written_for_a_reviewed_lead_only(tmp_path):
    conn = _db(tmp_path)
    _lead(conn, "strata", ["x"], "2026-09-25", reviewed_at="2026-10-09", verdict="hit",
          lead_days=3, trends='{"shape": "rise"}')
    _lead(conn, "flop", ["sitemap"], "2026-10-01")

    stats = migrate.migrate(conn)

    assert stats["reviews"] == 1
    days, checked_at, search_rise, lead_days, metrics = conn.execute(
        "SELECT days, checked_at, search_rise, lead_days, metrics FROM reviews").fetchone()
    assert (days, checked_at, search_rise, lead_days) == (14, "2026-10-09", 1, 3)
    assert json.loads(metrics) == {"shape": "rise", "verdict": "hit"}


def test_slow_lane_signals_are_labelled_slow(tmp_path):
    conn = _db(tmp_path)
    _lead(conn, "ai headshot", ["usecase"], "2026-10-14")
    _lead(conn, "vibe coding", ["x", "usecase"], "2026-10-14")

    migrate.migrate(conn)

    windows = dict(conn.execute("SELECT canonical, window FROM terms").fetchall())
    assert windows == {"ai headshot": "slow", "vibe coding": "fast"}


def test_second_run_skips_rows_it_already_copied(tmp_path):
    conn = _db(tmp_path)
    _lead(conn, "figcraft", ["breakout"], "2026-10-15")

    migrate.migrate(conn)
    stats = migrate.migrate(conn)

    assert (stats["terms"], stats["skipped"]) == (0, 1)
    assert conn.execute("SELECT count(*) FROM terms").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM term_signals").fetchone()[0] == 1


def test_dry_run_reports_the_counts_and_writes_nothing(tmp_path):
    conn = _db(tmp_path)
    _lead(conn, "figcraft", ["breakout"], "2026-10-15", reviewed_at="2026-10-16", verdict="miss")

    stats = migrate.migrate(conn, dry_run=True)

    assert (stats["terms"], stats["signals"], stats["reviews"]) == (1, 1, 1)
    for table in ("terms", "term_signals", "reviews"):
        assert conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0


def test_reconcile_names_the_leads_that_did_not_arrive(tmp_path):
    conn = _db(tmp_path)
    _lead(conn, "figcraft", ["breakout"], "2026-10-15")
    _lead(conn, "hy memory", ["hf"], "2026-10-16")
    migrate.migrate(conn)
    conn.execute("DELETE FROM terms WHERE canonical = 'hy memory'")
    conn.commit()

    report = migrate.reconcile(conn)

    assert report["leads"] == 2 and report["terms"] == 1
    assert report["missing"] == ["hy memory"]


def test_reconcile_sees_a_value_that_changed(tmp_path):
    conn = _db(tmp_path)
    _lead(conn, "figcraft", ["breakout"], "2026-10-15", "2026-10-17", named=0.9, variants=["figcraft"])
    migrate.migrate(conn)
    conn.execute("UPDATE terms SET last_seen = '2026-10-18' WHERE canonical = 'figcraft'")
    conn.commit()

    report = migrate.reconcile(conn)

    assert report["missing"] == [] and report["drift"] == 1


def test_a_run_is_recorded_once(tmp_path):
    conn = _db(tmp_path)
    migrate.migrate(conn)
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"leads": [{}, {}], "keywords": [{}], "summary": {"pending": 2}}))

    stats = migrate.read_report(report)
    assert stats == {"leads": 2, "keywords": 1, "pending": 2}
    migrate.add_run(conn, "2026-10-17", "daily", 341000, stats)
    migrate.add_run(conn, "2026-10-17", "daily", 341000, stats)

    row = conn.execute("SELECT command, started_at, cost_micros, stats FROM runs").fetchone()
    assert conn.execute("SELECT count(*) FROM runs").fetchone()[0] == 1
    assert (row[0], row[1], row[2]) == ("daily", "2026-10-17", 341000)
    assert json.loads(row[3]) == {"leads": 2, "keywords": 1, "pending": 2}
