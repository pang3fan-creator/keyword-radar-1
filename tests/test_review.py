"""Review windows: free local checks at 1d/3d, one Trends series per lane for the later ones.

A fast term reaches 1d, 3d, 7d and 14d; a slow word 14d and 30d. Before this, one 14-day
verdict mixed "is the name real" with "did searches rise", and no slow word was ever checked.
"""
from datetime import date, timedelta

from radar import review, store

DAY = date(2026, 10, 17)
SEEN = date(2026, 9, 25)


def _lead(term, kinds, **more):
    return {"term": term, "kinds": list(kinds), "signals": [f"note {term} {k}" for k in kinds], **more}


def _answer(values, start=SEEN - timedelta(days=30)):
    """A Trends tool answer: one daily point per value, starting 30 days before first_seen."""
    points = [{"date_from": (start + timedelta(days=i)).isoformat(), "values": [v]} for i, v in enumerate(values)]
    return {"tasks": [{"result": [{"items": [{"data": points}]}]}]}


def _series(values):
    return [5] * 30 + values      # 30 settled days before first_seen, then the window


def test_free_windows_write_1d_and_3d_without_a_paid_call(cfg, tmp_path, monkeypatch):
    conn = store.connect(tmp_path)
    store.record(conn, [_lead("figcraft", ["breakout"], named=0.9)], date(2026, 9, 25))
    store.record(conn, [_lead("figcraft", ["breakout"], named=0.9)], date(2026, 9, 26))   # seen again
    store.record(conn, [_lead("weakcraft", ["breakout"], named=0.6)], date(2026, 9, 25))
    store.record(conn, [_lead("ai tattoo generator", ["autocomplete"])], date(2026, 9, 25))

    def no_paid(calls):
        raise AssertionError("the 1d/3d windows must not call a paid source")
    monkeypatch.setattr(review.aisa, "call_all", no_paid)

    out = review.review(cfg, conn, date(2026, 9, 28))      # 3 days later: the free windows, no paid one

    assert {(r["term"], r["days"]) for r in out["checked"]} == {
        ("figcraft", 1), ("figcraft", 3), ("weakcraft", 1), ("weakcraft", 3)}
    assert out["cost_micros"] == 0 and out["errors"] == []
    rows = conn.execute("SELECT t.canonical, r.days, r.name_real, r.persistence FROM reviews r"
                        " JOIN terms t ON t.id = r.term_id ORDER BY t.canonical, r.days").fetchall()
    assert rows == [("figcraft", 1, 1, 1), ("figcraft", 3, 1, 1),
                    ("weakcraft", 1, 0, 0), ("weakcraft", 3, 0, 0)]
    assert not conn.execute("SELECT 1 FROM reviews WHERE term_id ="
                            " (SELECT id FROM terms WHERE canonical = 'ai tattoo generator')").fetchone()


def test_one_series_fills_the_7d_and_14d_windows(cfg, tmp_path, monkeypatch):
    conn = store.connect(tmp_path)
    store.record(conn, [_lead("niko strata", ["breakout"], named=0.9)], SEEN)
    values = _series([5] * 10 + [40, 100] + [0] * 4)        # the rise starts 10 days after first_seen
    monkeypatch.setattr(review.aisa, "call_all",
                        lambda calls: ({c["call_id"]: _answer(values) for c in calls}, 3600))

    out = review.review(cfg, conn, date(2026, 10, 10))      # 15 days later: 14d is due

    rows = {r["days"]: r for r in out["checked"] if r["term"] == "niko strata" and r["days"] >= 7}
    assert set(rows) == {7, 14}
    assert rows[7]["search_rise"] == 0                     # day 10 is outside the first week
    assert rows[14]["search_rise"] == 1 and rows[14]["lead_days"] == 10
    assert rows[14]["name_real"] == 1 and rows[14]["persistence"] == 0
    assert out["cost_micros"] == 3600
    checked = conn.execute("SELECT days, checked_at, search_rise, lead_days FROM reviews WHERE days >= 7"
                           " ORDER BY days").fetchall()
    assert checked == [(7, "2026-10-10", 0, None), (14, "2026-10-10", 1, 10)]
    assert store.due(conn, date(2026, 10, 10), 14, 5) == []


def test_a_slow_word_gets_14_and_30_days_and_no_name_score(cfg, tmp_path, monkeypatch):
    conn = store.connect(tmp_path)
    store.record(conn, [_lead("ai tattoo generator", ["autocomplete"])], SEEN)
    values = _series([40] * 31)
    monkeypatch.setattr(review.aisa, "call_all",
                        lambda calls: ({c["call_id"]: _answer(values) for c in calls}, 3600))

    out = review.review(cfg, conn, date(2026, 10, 28))      # 33 days later: 30d is due

    rows = {r["days"]: r for r in out["checked"] if r["term"] == "ai tattoo generator"}
    assert set(rows) == {14, 30}
    assert rows[14]["search_rise"] == 1 and rows[30]["search_rise"] == 1
    assert rows[14]["name_real"] is None and rows[30]["name_real"] is None
    assert conn.execute("SELECT count(*) FROM reviews").fetchone()[0] == 2
    assert store.due(conn, date(2026, 10, 28), 30, 5, "slow") == []


def test_a_failed_trends_batch_is_reported_and_the_term_stays_due(cfg, tmp_path, monkeypatch):
    conn = store.connect(tmp_path)
    store.record(conn, [_lead("niko strata", ["breakout"], named=0.9)], SEEN)

    def boom(calls):
        raise review.aisa.AisaError("HTTP 500")
    monkeypatch.setattr(review.aisa, "call_all", boom)

    out = review.review(cfg, conn, date(2026, 10, 10))

    assert out["errors"] and "HTTP 500" in out["errors"][0]
    assert [t for t, _, _ in store.due(conn, date(2026, 10, 10), 14, 5)] == ["niko strata"]
    assert not conn.execute("SELECT 1 FROM reviews WHERE days = 14").fetchone()
    assert conn.execute("SELECT count(*) FROM reviews").fetchone()[0] == 2      # the free rows landed


def test_a_missing_trends_answer_keeps_only_that_term_due(cfg, tmp_path, monkeypatch):
    conn = store.connect(tmp_path)
    store.record(conn, [_lead("niko strata", ["breakout"], named=0.9)], SEEN)
    store.record(conn, [_lead("veo free", ["x"], named=0.9)], SEEN)
    values = _series([40, 100] + [0] * 13)

    def partial(calls):
        # r0 is niko strata (canonical order): its calls are left out, as aisa.call does on failure
        return ({c["call_id"]: _answer(values) for c in calls if not c["call_id"].startswith("r0")}, 1200)
    monkeypatch.setattr(review.aisa, "call_all", partial)

    out = review.review(cfg, conn, date(2026, 10, 10))

    assert any("niko strata" in e for e in out["errors"])
    assert [t for t, _, _ in store.due(conn, date(2026, 10, 10), 14, 5)] == ["niko strata"]
    assert conn.execute("SELECT count(*) FROM reviews WHERE days = 14").fetchone()[0] == 1


def test_plan_calls_ends_each_window_at_its_horizon():
    due = [("strata", date(2026, 9, 25), ["strata"])]

    calls, _ = review.plan_calls(due, date(2026, 11, 1), 7)

    body = calls[0]["arguments"]["body"][0]
    assert body["date_from"] == "2026-08-26" and body["date_to"] == "2026-10-02"


def test_next_paid_names_the_first_future_window(cfg, tmp_path, monkeypatch):
    conn = store.connect(tmp_path)
    store.record(conn, [_lead("young", ["x"], named=0.9)], date(2026, 10, 8))
    monkeypatch.setattr(review.aisa, "call_all", lambda calls: ({}, 0))

    out = review.review(cfg, conn, DAY)

    assert out["next_paid"] == {"fast": "2026-10-22", "slow": None}


def test_running_twice_keeps_one_row_per_window(cfg, tmp_path, monkeypatch):
    conn = store.connect(tmp_path)
    store.record(conn, [_lead("figcraft", ["breakout"], named=0.9)], date(2026, 9, 25))
    monkeypatch.setattr(review.aisa, "call_all", lambda calls: ({}, 0))

    review.review(cfg, conn, DAY)
    out = review.review(cfg, conn, DAY)

    assert out["checked"] == []
    assert conn.execute("SELECT count(*) FROM reviews").fetchone()[0] == 2


def test_the_report_marks_a_free_window_read_late(cfg):
    from radar import report
    summ = {"window_days": 60, "windows": {}, "pending_windows": {"fast": {"14": 1}, "slow": {"30": 0}},
            "due_windows": {"fast": {"14": 0}, "slow": {"30": 0}}, "samples": {}}
    rev = {"checked": [{"term": "niko strata", "days": 1, "lane": "fast", "first_seen": "2026-10-15",
                        "name_real": 1, "persistence": 0, "search_rise": None, "lead_days": None,
                        "age_days": 3},
                       {"term": "figcraft", "days": 1, "lane": "fast", "first_seen": "2026-10-17",
                        "name_real": 1, "persistence": 0, "search_rise": None, "lead_days": None,
                        "age_days": 1}],
           "cost_micros": 0, "errors": [], "next_paid": {"fast": "2026-10-29", "slow": None}}

    text = "\n".join(report._review_lines(cfg, rev, summ))

    assert "1d 2 (1-3d)" in text and "2026-10-29" in text      # late at 3 days, and the next check named
