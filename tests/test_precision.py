"""The sitemap/new-site precision sample: ten echo candidates a month, labeled by demand.

An echo term has no Trends review (no hit rate), so its accuracy is sampled: a name that
already had a thousand searches a month was an existing product, one with none is plausibly
new. This is a proxy, and the raw volume is kept so the sample can be re-read by hand.
"""
import json
from datetime import date

from radar import __main__ as cli
from radar import aisa, precision, store


def _lead(term, kinds, **more):
    return {"term": term, "kinds": list(kinds), "signals": [f"note {term}"], **more}


def test_echo_candidates_are_labeled_by_their_monthly_searches(cfg, tmp_path, monkeypatch):
    conn = store.connect(tmp_path)
    store.record(conn, [_lead("bitbucket", ["sitemap"]), _lead("zotero", ["sitemap"]),
                        _lead("figcraft", ["breakout"])], date(2026, 9, 25))
    monkeypatch.setattr(precision.usecases, "volumes",
                        lambda phrases, loc: ({"bitbucket": {"volume": 2_400_000, "month": "2026-09"},
                                               "zotero": {"volume": 0, "month": "2026-09"}}, 1200))

    out = precision.run(cfg, conn, today=date(2026, 10, 18))

    assert [(r["term"], r["label"]) for r in out["sampled"]] == [("bitbucket", "searched"), ("zotero", "new")]
    assert out["cost_micros"] == 1200 and out["errors"] == []
    rows = conn.execute("SELECT t.canonical, x.source, x.volume, x.label FROM samples x"
                        " JOIN terms t ON t.id = x.term_id ORDER BY t.canonical").fetchall()
    assert rows == [("bitbucket", "sitemap", 2_400_000, "searched"), ("zotero", "sitemap", 0, "new")]
    assert precision.run(cfg, conn, today=date(2026, 10, 18))["sampled"] == []   # never twice


def test_a_missing_volume_is_unknown_not_new(cfg, tmp_path, monkeypatch):
    conn = store.connect(tmp_path)
    store.record(conn, [_lead("bitbucket", ["sitemap"]), _lead("zotero", ["sitemap"])], date(2026, 9, 25))
    monkeypatch.setattr(precision.usecases, "volumes",
                        lambda phrases, loc: ({"bitbucket": {"volume": 5000, "month": "2026-09"}}, 600))

    out = precision.run(cfg, conn, today=date(2026, 10, 18))

    assert {r["term"]: r["label"] for r in out["sampled"]} == {"bitbucket": "searched", "zotero": "unknown"}
    assert store.sample_summary(conn, date(2026, 9, 1)) == {
        "sitemap": {"sampled": 2, "new": 0, "searched": 1, "unknown": 1}}


def test_a_volume_failure_writes_no_sample_and_says_so(cfg, tmp_path, monkeypatch):
    conn = store.connect(tmp_path)
    store.record(conn, [_lead("bitbucket", ["sitemap"])], date(2026, 9, 25))

    def boom(phrases, loc):
        raise aisa.AisaError("HTTP 500")
    monkeypatch.setattr(precision.usecases, "volumes", boom)

    out = precision.run(cfg, conn, today=date(2026, 10, 18))

    assert out["sampled"] == [] and "HTTP 500" in out["errors"][0]
    assert conn.execute("SELECT count(*) FROM samples").fetchone()[0] == 0


def test_the_command_prints_the_sample_and_records_a_run(tmp_path, monkeypatch):
    monkeypatch.setattr(precision.usecases, "volumes",
                        lambda phrases, loc: ({p: {"volume": 10, "month": "2026-09"} for p in phrases}, 1200))
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"x_accounts": {"labs": []}}))
    state = tmp_path / "s"
    store.record(store.connect(state), [_lead("bitbucket", ["sitemap"])], date(2026, 9, 25))
    out = tmp_path / "sample.md"

    assert cli.main(["precision", "--config", str(cfg_path), "--state", str(state),
                     "--out", str(out), "--n", "5"]) == 0

    text = out.read_text()
    assert "bitbucket" in text and "new" in text and "$0.001" in text
    assert store.connect(state).execute("SELECT command, cost_micros FROM runs").fetchone() == ("precision", 1200)
