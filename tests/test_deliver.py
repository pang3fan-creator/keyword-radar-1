"""The delivery lane: what a word becomes a line, and what a failed gate says."""
from __future__ import annotations

import json
from datetime import date

import pytest

from radar import deliver, tiktok

DAY = date(2026, 11, 2)
CONF = {"deliver": {"per_source": 3, "max_serp": 5, "max_items": 10, "location_code": 2840,
                    "model": "m", "llm_micros": 3000}}
GOOD = json.dumps({"usage": "u", "page": "p", "money": "m", "timing": "t"})


def cand(term: str, source: str = "x", *, day: str = "2026-11-02", speed: dict | None = None) -> dict:
    return {"term": term, "source": source, "first_seen": day, "context": "text", "url": "https://e/x",
            "speed": speed, "detail": {"accounts": 2, "likes": 10}}


def gather_of(**rows):
    """A gather table where each source returns its own rows and nothing costs anything."""
    return {name: (lambda cfg, state, rows=rows.get(name, []): (rows, 0, []))
            for name in deliver.SOURCES}


def serp_of(kinds: list[str], cost: int = 130_000):
    return lambda keyword, location: ({"results": [{"kind": k} for k in kinds]}, cost)


# --- tiktok -----------------------------------------------------------------------------

def test_artist_keeps_the_short_name_and_drops_original_sound():
    assert tiktok.artist("Bulin 47 & Kevin Wai & Breyco En Producidera") == "bulin 47"
    assert tiktok.artist("Original Sound - Somebody") == ""
    assert tiktok.artist("Ramalama (Bang Bang)") == "ramalama (bang bang)"


def test_rising_keeps_the_biggest_move_per_sound():
    rows = [{"sound_id": "a", "chart_type": "popular", "rank": 3, "title": "T", "artist": "A",
             "usage_change": 10, "observation_date": "2026-11-02"},
            {"sound_id": "a", "chart_type": "viral", "rank": 9, "title": "T", "artist": "A",
             "usage_change": 50, "observation_date": "2026-11-02"},
            {"sound_id": "b", "chart_type": "viral", "rank": 2, "title": "S", "artist": "B",
             "usage_change": 7, "observation_date": "2026-11-02"}]
    got = tiktok.rising(rows, 5)
    assert [r["term"] for r in got] == ["a", "b"]
    assert got[0]["speed"]["usage_change"] == 50


# --- the words --------------------------------------------------------------------------

def test_tail_type_reads_what_people_ask_for():
    assert deliver.tail_type(["hotel lobby ai", "hotel lobby video"]) == "tool"
    assert deliver.tail_type(["bulin 47 lyrics", "bulin 47 meaning"]) == "info"
    assert deliver.tail_type([]) == ""


def test_pick_keyword_prefers_the_type_and_the_short_phrasing():
    assert deliver.pick_keyword(["hotel lobby ai", "hotel lobby video generator", "hotel lobby generator"],
                                "tool") == "hotel lobby generator"
    assert deliver.pick_keyword(["bulin 47 lyrics", "bulin 47 song"], "info") == "bulin 47 lyrics"


def test_window_reads_the_first_page():
    assert deliver.window({"tool": 5}) == "crowded"
    assert deliver.window({"tool": 1, "list": 3}) == "open"
    assert deliver.window({}) == "open"
    assert deliver.window({"tool": 2}) == "mixed"


# --- the run ----------------------------------------------------------------------------

def test_a_tiktok_sound_that_gained_videos_becomes_one_line(monkeypatch):
    monkeypatch.setattr(deliver, "tails_for", lambda term: ["bulin 47 lyrics", "bulin 47 meaning"])
    result = deliver.run(CONF, None, DAY, gather=gather_of(
        tiktok=[cand("bulin 47", "tiktok", speed={"usage_change": 16199, "rank": 21, "chart": "viral"})]),
        serp=serp_of(["list", "article"]), chat=lambda *a, **k: GOOD)
    assert [r["term"] for r in result["rows"]] == ["bulin 47"]
    row = result["rows"][0]
    assert row["kind"] == "info" and row["keyword"] == "bulin 47 lyrics"
    assert row["window"] == "open"
    assert result["dropped"] == []
    assert result["cost_micros"] == 130_000 + 3_000


def test_a_word_seen_before_today_without_speed_is_dropped(monkeypatch):
    monkeypatch.setattr(deliver, "tails_for", lambda term: ["foo ai"])
    result = deliver.run(CONF, None, DAY, gather=gather_of(x=[cand("foo", day="2026-10-30")]),
                         serp=serp_of([]), chat=lambda *a, **k: GOOD)
    assert result["rows"] == []
    assert result["dropped"] == [{"term": "foo", "reason": "moving"}]


def test_a_crowded_first_page_is_dropped_with_its_reason(monkeypatch):
    monkeypatch.setattr(deliver, "tails_for", lambda term: ["foo generator"])
    result = deliver.run(CONF, None, DAY, gather=gather_of(x=[cand("foo")]),
                         serp=serp_of(["tool"] * 5), chat=lambda *a, **k: GOOD)
    assert result["rows"] == []
    assert result["dropped"] == [{"term": "foo", "reason": "crowded"}]


def test_a_row_missing_a_field_is_not_written(monkeypatch):
    monkeypatch.setattr(deliver, "tails_for", lambda term: ["foo generator"])
    result = deliver.run(CONF, None, DAY, gather=gather_of(x=[cand("foo")]),
                         serp=serp_of(["tool"]), chat=lambda *a, **k: '{"usage": "u"}')
    assert result["rows"] == []
    assert result["dropped"] == [{"term": "foo", "reason": "fields"}]


def test_one_dead_source_does_not_kill_the_report(monkeypatch):
    monkeypatch.setattr(deliver, "tails_for", lambda term: ["foo generator"])

    def dead(cfg, state):
        raise RuntimeError("no APIFY_TOKEN")

    gather = gather_of(x=[cand("foo")])
    gather["tiktok"] = dead
    result = deliver.run(CONF, None, DAY, gather=gather, serp=serp_of(["tool"]),
                         chat=lambda *a, **k: GOOD)
    assert [r["term"] for r in result["rows"]] == ["foo"]
    assert result["sources"]["tiktok"]["error"].startswith("RuntimeError: no APIFY_TOKEN")
    assert any("no APIFY_TOKEN" in e for e in result["errors"])


def test_each_source_gives_at_most_three_lines(monkeypatch):
    monkeypatch.setattr(deliver, "tails_for", lambda term: [f"{term} generator"])
    rows = [cand(f"word {i}") for i in range(5)]
    result = deliver.run(CONF, None, DAY, gather=gather_of(x=rows), serp=serp_of(["tool"]),
                         chat=lambda *a, **k: GOOD)
    assert len(result["rows"]) == 3
    assert sum(1 for d in result["dropped"] if d["reason"] == "cap") == 2


# --- the report -------------------------------------------------------------------------

def test_the_report_keeps_every_source_even_when_empty(monkeypatch):
    monkeypatch.setattr(deliver, "tails_for", lambda term: ["foo generator"])
    result = deliver.run(CONF, None, DAY, gather=gather_of(x=[cand("foo")]),
                         serp=serp_of(["tool"]), chat=lambda *a, **k: GOOD)
    text = deliver.markdown(result)
    for title in ("## X", "## TikTok", "## Product Hunt", "## Reddit"):
        assert title in text
    assert "`foo generator`" in text
    assert "2026-11-02" in text


def test_a_dropped_word_is_named_with_its_reason(monkeypatch):
    monkeypatch.setattr(deliver, "tails_for", lambda term: ["foo generator"])
    result = deliver.run(CONF, None, DAY, gather=gather_of(x=[cand("foo")], ph=[cand("bar", "ph")]),
                         serp=serp_of(["tool"] * 5), chat=lambda *a, **k: GOOD)
    text = deliver.markdown(result)
    assert "d_dropped" not in text
    assert "`foo`" in text and "`bar`" in text


def test_a_later_source_with_speed_keeps_the_first_source(monkeypatch):
    """07 §6.1: the word belongs to whoever saw it first; speed is evidence, not ownership."""
    monkeypatch.setattr(deliver, "tails_for", lambda term: ["foo generator"])
    result = deliver.run(CONF, None, DAY, gather=gather_of(
        x=[cand("foo")],
        tiktok=[cand("foo", "tiktok", speed={"usage_change": 500, "rank": 4, "chart": "viral"})]),
        serp=serp_of(["tool"]), chat=lambda *a, **k: GOOD)
    row = result["rows"][0]
    assert row["source"] == "x" and row["also"] == ["tiktok"]
    assert row["speed"]["usage_change"] == 500


def test_a_word_delivered_in_the_last_days_does_not_take_a_slot_again(monkeypatch):
    monkeypatch.setattr(deliver, "tails_for", lambda term: ["foo generator"])
    result = deliver.run(CONF, None, DAY, gather=gather_of(x=[cand("foo")]),
                         serp=serp_of(["tool"]), chat=lambda *a, **k: GOOD, seen={"foo"})
    assert result["rows"] == []
    assert result["dropped"] == [{"term": "foo", "reason": "already"}]


def test_the_paid_checks_are_shared_across_sources(monkeypatch):
    """TikTok carries the speed, but the five Google checks must not all go to TikTok."""
    monkeypatch.setattr(deliver, "tails_for", lambda term: [f"{term} generator"])
    conf = {"deliver": {**CONF["deliver"], "max_serp": 2}}
    result = deliver.run(conf, None, DAY, gather=gather_of(
        tiktok=[cand("a", "tiktok", speed={"usage_change": 900, "rank": 1, "chart": "viral"}),
                cand("b", "tiktok", speed={"usage_change": 800, "rank": 2, "chart": "viral"})],
        ph=[cand("c", "ph")]), serp=serp_of(["tool"]), chat=lambda *a, **k: GOOD)
    assert [r["term"] for r in result["rows"]] == ["a", "c"]
    assert {"term": "b", "reason": "cap"} in result["dropped"]
