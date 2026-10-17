"""The manual `keywords` path finds a stored term by any spelling it was stored under."""
from datetime import date

from radar import store


def _db(tmp_path):
    conn = store.connect(tmp_path)
    store.record(conn, [{"term": "muse spark open", "kinds": ["x", "hf"], "signals": ["n1", "n2"],
                         "named": 0.92, "variants": ["spark open"]},
                        {"term": "beam 1.0", "kinds": ["x"], "signals": ["n3"], "named": 0.8, "variants": []}],
                 today=date(2026, 10, 1))
    return conn


def test_a_known_name_is_found_by_its_canonical(tmp_path):
    assert store.signals_for(_db(tmp_path), "muse spark open") == {"kinds": ["hf", "x"], "named": 0.92}


def test_a_name_typed_as_one_of_its_aliases_finds_the_same_signals(tmp_path):
    assert store.signals_for(_db(tmp_path), "spark open") == {"kinds": ["hf", "x"], "named": 0.92}


def test_a_shorter_spelling_that_is_not_an_alias_finds_nothing(tmp_path):
    assert store.signals_for(_db(tmp_path), "beam") == {"kinds": [], "named": None}
