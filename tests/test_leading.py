"""The leading rule: what decides a name's priority when there is no size to compare."""
from radar import leading


def test_two_signals_and_a_clear_name_are_strong():
    assert leading.strong(["x", "hf"], 0.9)


def test_one_signal_is_not_strong_however_clear_the_name():
    assert not leading.strong(["x"], 1.0)


def test_two_signals_with_a_weak_name_are_not_strong():
    assert not leading.strong(["x", "hf"], 0.5)
    assert not leading.strong(["x", "hf"], None)


def test_the_same_signal_twice_is_one_signal():
    assert not leading.strong(["x", "x"], 0.9)


def test_the_label_shows_what_the_rule_used():
    assert leading.label(["x", "hf"], 0.9) == "2 signals · 0.90"
    assert leading.label(["x"], None) == "1 signal · —"


def test_an_unknown_size_falls_back_to_the_leading_rule():
    from radar import usecases

    rising = {"now": "rising"}
    assert usecases.decide(rising, None, 300, strong=True) == "prioritize"
    assert usecases.decide(rising, None, 300, strong=False) == "watch"
    assert usecases.decide({"now": "flat"}, None, 300, strong=True) == "watch"
    assert usecases.decide({"now": "fading"}, None, 300, strong=True) == "skip"
    assert usecases.decide(rising, 500, 300, strong=False) == "prioritize"    # a known size wins


def test_a_name_carries_its_leading_label_into_the_table():
    from radar import usecases

    rows = [{"term": "figcraft", "phrase": "figcraft", "kind": "name", "names": [], "brand": True,
             "evidence": "", "kinds": ["breakout", "x"], "named": 0.9}]

    usecases.measure(rows, {}, {}, 300, usecases.date.today(), {}, None)

    assert rows[0]["leading"] == "2 signals · 0.90" and rows[0]["leading_strong"] is True
