"""The slow lane: a weekly combo-word list, measured by the fast lane's own chain."""
from datetime import date, timedelta

import pytest

from radar import report, select, slow, store

TODAY = date(2026, 10, 17)


def _series(days=90, base=10, tail=100, tail_days=10, end=TODAY):
    start = end - timedelta(days=days - 1)
    values = [base] * (days - tail_days) + [tail] * tail_days
    return [(start + timedelta(days=i), v) for i, v in enumerate(values)]


def _sized(term, objects, decision="watch", per_day=100):
    return {"term": term, "phrase": term, "kind": "generic", "objects": objects, "decision": decision,
            "per_day": per_day}


def test_balance_caps_a_category():
    rows = [_sized(f"ai video thing {chr(97 + i)}", ["video"]) for i in range(4)]

    got = slow.balance(rows, per_category=2, synonyms=99)

    assert len(got) == 2


def test_balance_caps_near_copies():
    rows = [_sized(f"ai headshot generator {w}", ["headshot"]) for w in ("free", "online", "app", "cheap", "pro")]

    got = slow.balance(rows, per_category=99, synonyms=3)

    assert len(got) == 3


def test_balance_keeps_unrelated_rows():
    rows = [_sized("ai headshot generator", ["headshot"]), _sized("pdf to word converter", ["pdf"])]

    assert len(slow.balance(rows, per_category=8, synonyms=3)) == 2


def test_spread_deals_categories_in_turn_rather_than_alphabetically():
    rows = [{"term": f"ai {cat} {i}", "objects": [cat], "found_by": 1}
            for cat in ("avatar", "video", "watermark") for i in range(3)]

    got = slow.spread(rows, 6)

    assert [r["objects"][0] for r in got] == ["avatar", "video", "watermark"] * 2


def _fake_candidates(seeds, known, cfg):
    return ([{"term": "ai headshot generator", "objects": ["headshot"], "seeds": ["ai headshot generator"]},
             {"term": "ai headshot maker", "objects": ["headshot"], "seeds": ["ai headshot generator", "ai avatar generator"]},
             {"term": "pdf to word converter", "objects": ["pdf"], "seeds": ["ai pdf converter"]}], [])


@pytest.fixture
def slow_cfg(cfg):
    cfg["slow"]["budget"] = 1
    return cfg


def test_a_paid_run_sizes_and_decides_with_the_shared_chain(cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(slow.autocomplete, "candidates", _fake_candidates)
    monkeypatch.setattr(slow.usecases, "volumes", lambda phrases, loc: (
        {p: {"volume": 1200, "month": "2026-08"} for p in phrases}, 90000))
    monkeypatch.setattr(slow.usecases, "solo_series", lambda phrases, today: (
        {p: _series() for p in phrases}, 4800))
    monkeypatch.setattr(slow.competition, "assess", lambda rows, cfg, state: (0, []))

    got = slow.run(cfg, tmp_path, today=TODAY)

    assert got["paid"] is True and got["cost_micros"] == 94800
    assert got["spend"] == {"volumes": 90000, "trends": 4800, "page_one": 0}
    assert [r["term"] for r in got["rows"]] == ["ai headshot generator", "ai headshot maker", "pdf to word converter"]
    assert all(r["decision"] in {"prioritize", "watch", "skip"} for r in got["rows"])
    assert got["rows"][0]["fresh"] is True
    conn = store.connect(tmp_path)
    rows = conn.execute("SELECT canonical, window FROM terms ORDER BY canonical").fetchall()
    assert rows == [("ai headshot generator", "slow"), ("ai headshot maker", "slow"), ("pdf to word converter", "slow")]


def test_a_free_run_makes_no_paid_call(cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(slow.autocomplete, "candidates", _fake_candidates)

    def paid(*a, **k):
        raise AssertionError("a free run must not call a paid step")
    monkeypatch.setattr(slow.usecases, "volumes", paid)
    monkeypatch.setattr(slow.usecases, "solo_series", paid)
    monkeypatch.setattr(slow.competition, "assess", paid)

    got = slow.run(cfg, tmp_path, today=TODAY, paid=False)

    assert got["paid"] is False and got["cost_micros"] == 0
    assert len(got["rows"]) == 3 and all("decision" not in r for r in got["rows"])


def test_a_second_week_marks_the_old_rows_as_seen(cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(slow.autocomplete, "candidates", _fake_candidates)
    monkeypatch.setattr(slow.usecases, "volumes", lambda phrases, loc: ({}, 0))
    monkeypatch.setattr(slow.usecases, "solo_series", lambda phrases, today: ({}, 0))
    monkeypatch.setattr(slow.competition, "assess", lambda rows, cfg, state: (0, []))

    slow.run(cfg, tmp_path, today=TODAY)
    got = slow.run(cfg, tmp_path, today=TODAY + timedelta(days=7))

    assert got["rows"][0]["fresh"] is False and got["rows"][0]["first_seen"] == TODAY.isoformat()


def test_the_report_names_a_failed_seed_and_the_cost(cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(slow.autocomplete, "candidates", lambda seeds, known, cfg: (
        [{"term": "ai headshot generator", "objects": ["headshot"], "seeds": ["ai headshot generator"]}],
        ["ai logo generator: HTTP 429"]))
    monkeypatch.setattr(slow.usecases, "volumes", lambda phrases, loc: ({}, 0))
    monkeypatch.setattr(slow.usecases, "solo_series", lambda phrases, today: ({}, 0))
    monkeypatch.setattr(slow.competition, "assess", lambda rows, cfg, state: (0, []))

    text = report.slow(cfg, slow.run(cfg, tmp_path, today=TODAY))

    assert "ai logo generator: HTTP 429" in text and "$0.000" in text and "| **ai headshot generator**" in text


def test_a_slow_term_is_not_in_the_fast_review_pool(tmp_path):
    conn = store.connect(tmp_path)
    store.record(conn, [{"term": "ai headshot generator", "kinds": ["autocomplete"], "signals": ["x"],
                         "named": None, "variants": []}], today=TODAY - timedelta(days=30))
    store.record(conn, [{"term": "strata", "kinds": ["x"], "signals": ["y"], "named": 0.9, "variants": []}],
                 today=TODAY - timedelta(days=30))

    due = [t for t, _, _ in store.due(conn, TODAY, 14, 10)]

    assert due == ["strata"]


def test_a_slow_term_found_by_a_fast_signal_becomes_reviewable(tmp_path):
    conn = store.connect(tmp_path)
    old = TODAY - timedelta(days=30)
    store.record(conn, [{"term": "ai headshot generator", "kinds": ["autocomplete"], "signals": ["x"],
                         "named": None, "variants": []}], today=old)
    assert store.due(conn, TODAY, 14, 10) == []

    store.record(conn, [{"term": "ai headshot generator", "kinds": ["x"], "signals": ["y"], "named": 0.9,
                         "variants": []}], today=TODAY - timedelta(days=20))

    assert [t for t, _, _ in store.due(conn, TODAY, 14, 10)] == ["ai headshot generator"]


def test_the_slow_lane_never_takes_a_fast_name_slot():
    rows = [{"term": "ai headshot generator", "kinds": ["autocomplete"], "named": 1.0, "first_seen": TODAY.isoformat()},
            {"term": "strata", "kinds": ["x"], "named": 1.0, "first_seen": TODAY.isoformat()}]

    ordered = select.order(rows, 20)

    assert ordered[0]["term"] == "strata"
    assert select.lane(rows[0]["kinds"]) == "slow"
