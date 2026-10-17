"""Which names reach the keyword table.

M0 exposed the bug this fixes: every equal-looking lead was ordered X first, so the top 20
and the five names read each day were all from one signal while a 0.95 Hugging Face model and
a 2,295-star repo never got read (docs/05 §4.2b). The order is now a quota, not a ranking.
"""
import random

from radar import select


def _row(term, kinds, named=None, first="2026-10-17"):
    return {"term": term, "kinds": list(kinds), "named": named, "first_seen": first}


def test_hf_and_breakout_reach_the_first_five():
    rows = ([_row(f"x name {i}", ["x"], 0.99) for i in range(6)]
            + [_row("hy memory", ["hf"], 0.95), _row("figcraft", ["breakout"], 0.90),
               _row("serpapi", ["sitemap"], 0.80)])

    got = [r["term"] for r in select.order(rows, 5)]

    assert {"hy memory", "figcraft"} <= set(got)


def test_no_single_signal_owns_the_top_twenty():
    rows = ([_row(f"x name {i}", ["x"], 0.99) for i in range(40)]
            + [_row(f"hf name {i}", ["hf"], 0.90) for i in range(5)]
            + [_row(f"repo {i}", ["breakout"], 0.90) for i in range(5)])

    top = select.order(rows, 20)[:20]

    assert len([r for r in top if r["kinds"] == ["x"]]) <= 12


def test_a_slow_lane_phrase_never_takes_a_name_slot():
    rows = [_row("free word processor", ["usecase"], 0.99),
            _row("mirelo sfx", ["x"], 0.50)]

    got = [r["term"] for r in select.order(rows, 1)[:1]]

    assert got == ["mirelo sfx"]


def test_the_order_keeps_every_row_and_is_deterministic():
    rows = ([_row(f"x name {i}", ["x"], 0.99) for i in range(3)]
            + [_row("hy memory", ["hf"], 0.95), _row("figcraft", ["breakout"], 0.90)])
    once = [r["term"] for r in select.order(rows)]
    random.Random(7).shuffle(rows)

    assert [r["term"] for r in select.order(rows)] == once
    assert sorted(once) == sorted(r["term"] for r in rows)
