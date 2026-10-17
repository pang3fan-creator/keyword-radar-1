"""The HN signal: a Show HN title names a thing; a story already read is not new."""
from datetime import datetime, timedelta, timezone

from radar import hn

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)


def test_a_show_hn_title_gives_the_name_after_the_prefix():
    assert hn.title_name("Show HN: Open Scrantic – Johnny Castaway in Rust") == "open scrantic"
    assert hn.title_name("Show HN: Qwen3.8 Flash — a local chat UI") == "qwen3.8 flash"
    assert hn.title_name("Show HN: Fable (a writing assistant for novels)") == "fable"


def test_a_title_that_names_nothing_is_dropped():
    assert hn.title_name("Show HN: I built a tiny tool that renames files") is None
    assert hn.title_name("Show HN: The tool I always wanted") is None
    assert hn.title_name("Ask HN: what editor do you use?") is None
    assert hn.title_name("Show HN: a lowercase name") is None
    assert hn.title_name("Show HN: Building an LLM from Scratch in TypeScript") is None


def test_a_story_read_before_is_not_a_new_name(tmp_path, cfg, monkeypatch):
    hits = [{"objectID": "1", "title": "Show HN: Fable – a writing app", "points": 120, "num_comments": 30,
             "created_at_i": int(NOW.timestamp()), "url": "https://example.com/fable"},
            {"objectID": "2", "title": "Show HN: Fable – again", "points": 60, "num_comments": 3,
             "created_at_i": int(NOW.timestamp()), "url": "https://example.com/fable2"},
            {"objectID": "3", "title": "Show HN: I built a thing", "points": 90, "num_comments": 5,
             "created_at_i": int(NOW.timestamp()), "url": ""}]
    monkeypatch.setattr(hn, "_get", lambda url: {"hits": hits})

    first = hn.hn(cfg, tmp_path, now=NOW)

    assert first["read"] == 3 and first["found"] == 1
    assert [r["term"] for r in first["terms"]] == ["fable"]
    assert first["terms"][0]["recent"] == 2
    assert "120 points" in first["terms"][0]["note"]

    second = hn.hn(cfg, tmp_path, now=NOW + timedelta(hours=1))

    assert second["found"] == 0 and second["terms"] == []


def test_a_story_below_the_point_floor_is_not_counted(cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(hn, "_get", lambda url: {"hits": [
        {"objectID": "9", "title": "Show HN: Fable – a writing app", "points": 3, "num_comments": 1,
         "created_at_i": int(NOW.timestamp()), "url": ""}]})

    got = hn.hn(cfg, tmp_path, now=NOW)

    assert got["read"] == 1 and got["found"] == 0
