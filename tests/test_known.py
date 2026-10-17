"""known_terms decide what the radar never reports, so they must match whole words.

Substring matching let a one-letter entry silence everything: `ai` hid `openai`, and the
example config ships `claude code`, which would have hidden `claude` (docs/05 §4.2 rule 5).
"""
from radar import config


def _cfg(*terms):
    return {"known_terms": list(terms)}


def test_a_short_entry_does_not_hide_a_longer_word():
    assert config.known(_cfg("ai"), "openai") == ""
    assert config.known(_cfg("code"), "codex") == ""


def test_a_known_entry_covers_a_longer_term():
    assert config.known(_cfg("ppt skills"), "best ppt skills") == "ppt skills"


def test_a_known_entry_hides_the_short_term_it_covers():
    assert config.known(_cfg("ppt skills"), "ppt") == "ppt skills"


def test_the_longest_matching_entry_wins():
    assert config.known(_cfg("ai", "ai video"), "ai video generator") == "ai video"


def test_nothing_matches():
    assert config.known(_cfg("remotion"), "figcraft") == ""


def test_separators_do_not_hide_a_match():
    assert config.known(_cfg("claude code"), "claude-code") == "claude code"
