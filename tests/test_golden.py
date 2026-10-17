"""The 30-word golden set: what a keyword row must say, whatever the data does.

M0 showed the failure this guards: a phrase without Google Ads volume was dropped before it
reached the table, so a new word -- the thing this radar exists to find -- could never appear.
The rows below are canned (no network, no paid call); they pin the thresholds and the decision
rules, not the accuracy of any real volume. A day where every row comes out watch or skip still
passes: the output count is a reference, not a criterion.
"""
import json
from pathlib import Path

import pytest

from radar import usecases

GOLDEN = json.loads((Path(__file__).parent / "fixtures" / "golden_30.json").read_text(encoding="utf-8"))
MIN_VOLUME, MIN_DAILY = 50, 300


def test_the_golden_set_is_thirty_words():
    assert len(GOLDEN) == 30
    assert len({r["phrase"] for r in GOLDEN}) == 30


@pytest.mark.parametrize("row", GOLDEN, ids=[r["phrase"] for r in GOLDEN])
def test_each_word_keeps_its_volume_status_and_decision(row):
    assert usecases.volume_status(row["volume"], MIN_VOLUME) == row["volume_status"]
    state = {"now": row["now"], "no_data": row["no_data"]}
    assert usecases.decide(state, row["per_day"], MIN_DAILY) == row["decision"]
    assert usecases.size_status(row["per_day"], row["dailies"]) == row["size_status"]


def test_a_phrase_without_volume_is_kept_and_told_so():
    proposed = {"alpha": {"phrase": "alpha", "brand": False},
                "beta": {"phrase": "beta", "brand": False}}

    got = usecases.keep(proposed, {"alpha": {"volume": 0, "month": ""}}, {"min_volume": MIN_VOLUME})

    assert [r["phrase"] for r in got] == ["alpha", "beta"]
    assert [r["volume_status"] for r in got] == ["unknown", "unknown"]


def test_a_small_phrase_is_below_the_threshold_but_not_dropped():
    got = usecases.keep({"tiny": {"phrase": "tiny", "brand": False}},
                        {"tiny": {"volume": 12, "month": "2026-08"}}, {"min_volume": MIN_VOLUME})

    assert [(r["phrase"], r["volume_status"]) for r in got] == [("tiny", "below_threshold")]


def test_a_sized_phrase_is_known():
    got = usecases.keep({"big": {"phrase": "big", "brand": False}},
                        {"big": {"volume": 9000, "month": "2026-08"}}, {"min_volume": MIN_VOLUME})

    assert got[0]["volume_status"] == "known" and got[0]["volume"] == 9000
