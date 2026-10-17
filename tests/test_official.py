"""The official-blog signal: a launch post names a thing; a customer story does not."""
from datetime import datetime, timedelta, timezone

from radar import official

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
RECENT = (NOW - timedelta(days=1)).strftime("%a, %d %b %Y %H:%M:%S +0000")
OLD = (NOW - timedelta(days=200)).strftime("%a, %d %b %Y %H:%M:%S +0000")

RSS = f"""<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
<item><title>Gemini 4 Argon: Built to solve your hardest problems</title><link>https://a.example/1</link>
<pubDate>{RECENT}</pubDate></item>
<item><title>How Itaú is building generative AI for its customers</title><link>https://a.example/2</link>
<pubDate>{RECENT}</pubDate></item>
<item><title>Introducing Claude 4.5 Sonnet</title><link>https://a.example/3</link>
<pubDate>{OLD}</pubDate></item>
</channel></rss>"""

ATOM = """<?xml version="1.0" encoding="utf-8"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>GPT-6 Astra is here</title><link href="https://b.example/1"/>
<updated>2026-10-16T10:00:00Z</updated></entry>
</feed>"""


def test_a_launch_title_gives_the_name_it_launches():
    assert official.launch_name("Gemini 4 Argon: Built to solve your hardest problems") == "gemini 4 argon"
    assert official.launch_name("Introducing Claude 4.5 Sonnet") == "claude 4.5 sonnet"
    assert official.launch_name("Introducing Fable, our new writing tool") == "fable"
    assert official.launch_name("Welcome Beam: a 501B open model you can own") == "beam"
    assert official.launch_name("Granite Switch 4.1: Chat, Decisions, and Speech") == "granite switch 4.1"
    assert official.launch_name("OpenAI o3 is now available") == "openai o3"
    assert official.launch_name("GPT-6 Astra is here") == "gpt-6 astra"


def test_a_customer_story_or_a_list_or_a_gerund_names_nothing():
    assert official.launch_name("How Itaú is building generative AI for its customers") is None
    assert official.launch_name("Stack Overflow for Agents triples signups with ChatGPT") is None
    assert official.launch_name("Benefit Street Partners answers questions faster with Codex") is None
    assert official.launch_name("Introducing our new pricing") is None
    assert official.launch_name("Announcing 7 new models") is None
    assert official.launch_name("Scaling Indic Pretraining: 2.8 Trillion Tokens") is None
    assert official.launch_name("A Gentle Introduction to 8-bit Matrix Multiplication") is None


def test_an_old_post_stays_in_the_archive(tmp_path, cfg, monkeypatch):
    cfg["official"]["feeds"] = {"a": "https://a.example/rss"}
    monkeypatch.setattr(official, "_get", lambda url: RSS.encode())

    got = official.official(cfg, tmp_path, now=NOW)

    assert got["read"] == 2 and got["found"] == 1
    assert [r["term"] for r in got["terms"]] == ["gemini 4 argon"]


def test_rss_and_atom_feeds_both_give_their_launch_titles(tmp_path, cfg, monkeypatch):
    cfg["official"]["feeds"] = {"a": "https://a.example/rss", "b": "https://b.example/atom"}
    monkeypatch.setattr(official, "_get", lambda url: (RSS if "a.example" in url else ATOM).encode())

    got = official.official(cfg, tmp_path, now=NOW)

    assert got["read"] == 3 and got["found"] == 2
    assert [r["term"] for r in got["terms"]] == ["gemini 4 argon", "gpt-6 astra"]
    assert got["terms"][1]["note"].startswith("b: ")


def test_a_link_read_before_is_not_reported_again(tmp_path, cfg, monkeypatch):
    cfg["official"]["feeds"] = {"a": "https://a.example/rss"}
    monkeypatch.setattr(official, "_get", lambda url: RSS.encode())

    official.official(cfg, tmp_path, now=NOW)
    second = official.official(cfg, tmp_path, now=NOW)

    assert second["read"] == 2 and second["found"] == 0 and second["terms"] == []


def test_a_dead_feed_does_not_hide_the_others(tmp_path, cfg, monkeypatch):
    cfg["official"]["feeds"] = {"a": "https://a.example/rss", "b": "https://b.example/atom"}

    def get(url):
        if "b.example" in url:
            raise OSError("404")
        return RSS.encode()
    monkeypatch.setattr(official, "_get", get)

    got = official.official(cfg, tmp_path, now=NOW)

    assert got["failed"] == ["b"] and got["found"] == 1
