"""Product Hunt: a launch is a product name on the day it ships, with a tagline to judge it."""
from datetime import datetime, timedelta, timezone

import pytest

from radar import ph

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)


def _edge(pid, name, votes, tagline="does a thing"):
    return {"node": {"id": pid, "name": name, "tagline": tagline, "votesCount": votes,
                     "url": f"https://producthunt.com/posts/{pid}"}}


def test_the_name_is_the_part_before_the_subtitle():
    assert ph.name("Notion: Context for your agents") == "notion context"
    assert ph.name("GPU Terminal by Context.dev") == "gpu terminal"
    assert ph.name("  Spiralens  ") == "spiralens"


def test_an_article_or_launch_verb_does_not_hide_the_feature():
    assert ph.name("Notion: The agents") == "notion agents"
    assert ph.name("Notion: for your agents") == "notion agents"
    assert ph.name("Notion: Introducing Agents") == "notion agents"
    assert ph.name("Acme: The AI browser") == "acme ai"


def test_a_sentence_after_the_colon_keeps_the_brand_alone():
    assert ph.name("Linear: How we built the issue tracker") == "linear"
    assert ph.name("Acme: for teams") == "acme teams"


def test_a_second_colon_and_a_by_suffix_stay_out_of_the_name():
    assert ph.name("Foo: Bar: Baz") == "foo bar"
    assert ph.name("GPU Terminal by Context.dev") == "gpu terminal"


def test_a_launch_below_the_vote_floor_is_not_reported(cfg, tmp_path, monkeypatch):
    monkeypatch.setenv("PH_API_KEY", "test")
    monkeypatch.setattr(ph, "_graphql", lambda query, variables: {"posts": {"edges": [
        _edge("1", "NitroStack", 182), _edge("2", "LooGo", 10)]}})

    got = ph.ph(cfg, tmp_path, now=NOW)

    assert got["read"] == 2 and got["found"] == 1
    assert [r["term"] for r in got["terms"]] == ["nitrostack"]


def test_a_product_is_reported_once(cfg, tmp_path, monkeypatch):
    monkeypatch.setenv("PH_API_KEY", "test")
    monkeypatch.setattr(ph, "_graphql", lambda query, variables: {"posts": {"edges": [
        _edge("1", "NitroStack", 182)]}})

    ph.ph(cfg, tmp_path, now=NOW)
    second = ph.ph(cfg, tmp_path, now=NOW)

    assert second["read"] == 1 and second["found"] == 0


def test_without_a_token_the_signal_is_off_and_says_which_key(cfg, tmp_path, monkeypatch):
    monkeypatch.delenv("PH_API_KEY", raising=False)

    got = ph.ph(cfg, tmp_path, now=NOW)

    assert got == {"skipped": True, "no_key": "PH_API_KEY"}


def test_a_maker_relaunch_is_not_a_new_name(cfg, tmp_path, monkeypatch):
    monkeypatch.setenv("PH_API_KEY", "test")
    monkeypatch.setattr(ph, "_graphql", lambda query, variables: {"posts": {"edges": [
        _edge("1", "OpenAI", 300), _edge("2", "OpenAI o3", 200)]}})

    got = ph.ph(cfg, tmp_path, now=NOW)

    assert [r["term"] for r in got["terms"]] == ["openai o3"]


def test_a_graphql_error_is_not_a_quiet_zero(cfg, tmp_path, monkeypatch):
    monkeypatch.setenv("PH_API_KEY", "test")

    def boom(query, variables):
        raise RuntimeError("HTTP 401")
    monkeypatch.setattr(ph, "_graphql", boom)

    with pytest.raises(RuntimeError):
        ph.ph(cfg, tmp_path, now=NOW)
